"""Business rules for organizations, membership management and invitations.

The guards worth knowing about:

* An organization always keeps at least one active admin. Demoting, disabling
  or removing the last one is refused rather than leaving a tenant nobody can
  administer.
* Admins cannot change their own role, which makes accidental self-lockout a
  two-person operation.
* Invitation tokens are opaque secrets. Only the SHA-256 digest is stored, so
  the raw token exists exactly once — in the email we send.
"""

from __future__ import annotations

import re
import secrets
import unicodedata
from datetime import timedelta
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from app.core.logging import get_logger
from app.core.pagination import Page, PageParams
from app.core.security import generate_token, hash_token
from app.core.time import DEFAULT_TIMEZONE, to_timezone, utcnow
from app.modules.notifications.email.outbox import enqueue
from app.modules.orgs import repository as repo
from app.modules.orgs.models import (
    Invitation,
    Membership,
    MembershipStatus,
    Organization,
    OrgRole,
)
from app.modules.orgs.schemas import (
    InvitationCreate,
    InvitationPreview,
    InvitationRead,
    MemberRead,
    MemberUpdate,
    OrganizationCreate,
    OrganizationUpdate,
)
from app.modules.users.models import User

logger = get_logger(__name__)

SLUG_MAX_LENGTH = 50
SLUG_FALLBACK = "org"
_NON_SLUG_CHARS = re.compile(r"[^a-z0-9]+")


# --------------------------------------------------------------------------
# slugs
# --------------------------------------------------------------------------
def slugify(name: str) -> str:
    """Turn an organization name into a short, URL-safe identifier.

    Accents are folded to ASCII ("Café" -> "cafe") and every run of other
    characters collapses to a single hyphen. Names that contain nothing usable
    fall back to ``org`` so the caller always gets a valid slug.
    """
    ascii_name = (
        unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii").lower()
    )
    slug = _NON_SLUG_CHARS.sub("-", ascii_name).strip("-")
    slug = slug[:SLUG_MAX_LENGTH].strip("-")
    return slug or SLUG_FALLBACK


async def generate_unique_slug(session: AsyncSession, name: str) -> str:
    """``slugify`` plus ``-2``, ``-3``, ... until the slug is free."""
    base = slugify(name)
    if not await repo.slug_exists(session, base):
        return base

    for suffix in range(2, 100):
        candidate = _with_suffix(base, str(suffix))
        if not await repo.slug_exists(session, candidate):
            return candidate

    # Pathological collision; a random suffix ends the search in one step.
    while True:
        candidate = _with_suffix(base, secrets.token_hex(4))
        if not await repo.slug_exists(session, candidate):
            return candidate


def _with_suffix(base: str, suffix: str) -> str:
    trimmed = base[: SLUG_MAX_LENGTH - len(suffix) - 1].strip("-") or SLUG_FALLBACK
    return f"{trimmed}-{suffix}"


# --------------------------------------------------------------------------
# organizations
# --------------------------------------------------------------------------
async def create_organization(
    session: AsyncSession, *, user: User, data: OrganizationCreate
) -> tuple[Organization, Membership]:
    """Create an organization and make its creator an active admin.

    A user may belong to several organizations, so an existing membership is
    not a reason to refuse.
    """
    org = Organization(
        name=data.name.strip(),
        slug=await generate_unique_slug(session, data.name),
        country=data.country,
        website=data.website,
        description=data.description,
        timezone=data.timezone or DEFAULT_TIMEZONE,
        created_by_id=user.id,
    )
    await repo.create_org(session, org)

    membership = Membership(
        org_id=org.id,
        user_id=user.id,
        role=OrgRole.ADMIN,
        status=MembershipStatus.ACTIVE,
        joined_at=utcnow(),
    )
    session.add(membership)
    await session.flush()

    logger.info("organization_created", org_id=str(org.id), slug=org.slug, user_id=str(user.id))
    return org, membership


async def update_organization(
    session: AsyncSession, org: Organization, data: OrganizationUpdate
) -> Organization:
    """Apply the supplied fields. The slug is deliberately immutable."""
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(org, field, value)
    await session.flush()
    return org


# --------------------------------------------------------------------------
# members
# --------------------------------------------------------------------------
async def list_members(session: AsyncSession, org_id: UUID, params: PageParams) -> Page[MemberRead]:
    rows, total = await repo.list_members(session, org_id, params)
    items = [MemberRead.from_row(membership, user) for membership, user in rows]
    return Page.build(items, params, total)


async def update_member(
    session: AsyncSession,
    *,
    org: Organization,
    actor: User,
    target_user_id: UUID,
    data: MemberUpdate,
) -> tuple[Membership, User]:
    membership = await _require_membership(session, org.id, target_user_id)

    if data.role is not None and target_user_id == actor.id and data.role != membership.role:
        raise ValidationError(
            "You cannot change your own role. Ask another admin to do it.",
            code="cannot_change_own_role",
        )

    demoting = data.role is not None and data.role is not OrgRole.ADMIN
    disabling = data.status is not None and data.status is not MembershipStatus.ACTIVE
    if demoting or disabling:
        await _guard_last_admin(session, org.id, membership)

    if data.role is not None:
        membership.role = data.role
    if data.status is not None:
        membership.status = data.status
    await session.flush()

    user = await session.get(User, target_user_id)
    if user is None:  # pragma: no cover - the FK makes this unreachable
        raise NotFoundError("Member not found.", code="member_not_found")
    logger.info(
        "membership_updated",
        org_id=str(org.id),
        user_id=str(target_user_id),
        role=membership.role.value,
        status=membership.status.value,
    )
    return membership, user


async def remove_member(
    session: AsyncSession, *, org: Organization, actor: User, target_user_id: UUID
) -> None:
    """Remove a member. Removing yourself is fine unless you are the last admin."""
    membership = await _require_membership(session, org.id, target_user_id)
    await _guard_last_admin(session, org.id, membership)

    await session.execute(delete(Membership).where(Membership.id == membership.id))
    await session.flush()
    logger.info(
        "membership_removed",
        org_id=str(org.id),
        user_id=str(target_user_id),
        actor_id=str(actor.id),
    )


async def _require_membership(session: AsyncSession, org_id: UUID, user_id: UUID) -> Membership:
    membership = await repo.get_membership(session, org_id, user_id)
    if membership is None:
        raise NotFoundError(
            "That user is not a member of this organization.", code="member_not_found"
        )
    return membership


async def _guard_last_admin(session: AsyncSession, org_id: UUID, membership: Membership) -> None:
    """Refuse a change that would leave the organization without an admin."""
    if membership.role is not OrgRole.ADMIN or membership.status is not MembershipStatus.ACTIVE:
        return
    if await repo.count_admins(session, org_id) <= 1:
        raise ConflictError(
            "This is the organization's last admin. Promote someone else first.",
            code="last_admin",
        )


# --------------------------------------------------------------------------
# invitations
# --------------------------------------------------------------------------
async def invite_member(
    session: AsyncSession, *, org: Organization, inviter: User, data: InvitationCreate
) -> tuple[Invitation, str]:
    """Invite an address to the organization.

    Returns the invitation and the **raw** token; only its digest is stored.
    A live invitation for the same address is revoked and replaced, so the
    newest link always wins and re-inviting never fails.
    """
    email = data.email.strip().lower()

    existing = await repo.get_membership_by_email(session, org.id, email)
    if existing is not None and existing[0].status is MembershipStatus.ACTIVE:
        raise ConflictError(
            f"{email} is already a member of this organization.", code="already_member"
        )

    pending = await repo.get_pending_invitation(session, org.id, email)
    if pending is not None:
        pending.revoked_at = utcnow()
        await session.flush()

    raw_token = generate_token()
    invitation = Invitation(
        org_id=org.id,
        email=email,
        role=data.role,
        token_hash=hash_token(raw_token),
        invited_by_id=inviter.id,
        expires_at=utcnow() + timedelta(days=settings.invitation_ttl_days),
    )
    session.add(invitation)
    await session.flush()

    await _send_invitation_email(
        session,
        org=org,
        invitation=invitation,
        inviter=inviter,
        raw_token=raw_token,
        dedupe_key=f"invitation:{invitation.id}",
    )
    logger.info(
        "invitation_created",
        org_id=str(org.id),
        invitation_id=str(invitation.id),
        role=invitation.role.value,
    )
    return invitation, raw_token


async def resend_invitation(
    session: AsyncSession, *, org: Organization, inviter: User, invitation_id: UUID
) -> tuple[Invitation, str]:
    """Issue a fresh token and email for a still-pending invitation.

    The previous link stops working, which is what you want if it leaked into
    the wrong inbox.
    """
    invitation = await _require_pending_invitation(session, org.id, invitation_id)

    raw_token = generate_token()
    invitation.token_hash = hash_token(raw_token)
    invitation.expires_at = utcnow() + timedelta(days=settings.invitation_ttl_days)
    invitation.invited_by_id = inviter.id
    await session.flush()

    await _send_invitation_email(
        session,
        org=org,
        invitation=invitation,
        inviter=inviter,
        raw_token=raw_token,
        # A resend must not be deduplicated against the original message.
        dedupe_key=f"invitation:{invitation.id}:{int(utcnow().timestamp())}",
    )
    logger.info("invitation_resent", org_id=str(org.id), invitation_id=str(invitation.id))
    return invitation, raw_token


async def revoke_invitation(
    session: AsyncSession, *, org: Organization, invitation_id: UUID
) -> Invitation:
    invitation = await _require_pending_invitation(session, org.id, invitation_id)
    invitation.revoked_at = utcnow()
    await session.flush()
    logger.info("invitation_revoked", org_id=str(org.id), invitation_id=str(invitation.id))
    return invitation


async def list_invitations(session: AsyncSession, org_id: UUID) -> list[InvitationRead]:
    invitations = await repo.list_invitations(session, org_id)
    inviter_ids = [inv.invited_by_id for inv in invitations if inv.invited_by_id is not None]
    inviters = await repo.get_users_by_ids(session, inviter_ids)
    now = utcnow()

    def inviter_name(invitation: Invitation) -> str | None:
        if invitation.invited_by_id is None:
            return None
        return _inviter_name(inviters.get(invitation.invited_by_id))

    return [
        InvitationRead.from_invitation(
            invitation, invited_by_name=inviter_name(invitation), now=now
        )
        for invitation in invitations
    ]


async def read_invitation(session: AsyncSession, invitation: Invitation) -> InvitationRead:
    """Serialize one invitation, resolving the inviter's display name."""
    inviter = (
        await session.get(User, invitation.invited_by_id)
        if invitation.invited_by_id is not None
        else None
    )
    return InvitationRead.from_invitation(invitation, invited_by_name=_inviter_name(inviter))


async def preview_invitation(session: AsyncSession, token: str) -> InvitationPreview:
    """Public view of an invitation, resolved from its raw token.

    Returns only what the accept screen needs; nothing else about the
    organization is exposed to an unauthenticated caller.
    """
    invitation = await _resolve_usable_invitation(session, token)

    org = await repo.get_org_by_id(session, invitation.org_id)
    if org is None:  # pragma: no cover - the FK cascade makes this unreachable
        raise NotFoundError("Invitation not found.", code="invitation_not_found")

    inviter = (
        await session.get(User, invitation.invited_by_id)
        if invitation.invited_by_id is not None
        else None
    )
    invitee = await repo.get_user_by_email(session, invitation.email)
    return InvitationPreview(
        org_name=org.name,
        inviter_name=_inviter_name(inviter),
        role=invitation.role,
        email=invitation.email,
        expires_at=invitation.expires_at,
        requires_signup=invitee is None,
    )


async def accept_invitation(
    session: AsyncSession, *, token: str, user: User
) -> tuple[Membership, User]:
    """Join the inviting organization. Safe to call twice with the same token.

    The signed-in user's address must match the invited one, so a leaked link
    cannot be redeemed by whoever happens to receive it. Replaying a token that
    was already redeemed by the same person returns the existing membership,
    which keeps a double-clicked accept button harmless.
    """
    invitation = await repo.get_invitation_by_token_hash(session, hash_token(token))
    if invitation is None or invitation.revoked_at is not None:
        raise NotFoundError("This invitation link is not valid.", code="invitation_not_found")

    same_person = invitation.email.strip().lower() == user.email.strip().lower()
    if invitation.accepted_at is not None:
        # Only the person who redeemed it may replay it; to anyone else an
        # already-used token is indistinguishable from an unknown one.
        if not same_person:
            raise NotFoundError("This invitation link is not valid.", code="invitation_not_found")
    elif not invitation.is_usable():
        raise ValidationError(
            "This invitation has expired. Ask an admin to send a new one.",
            code="invitation_expired",
        )

    if not same_person:
        raise PermissionDeniedError(
            f"This invitation was sent to {invitation.email}. "
            "Sign in with that address to accept it.",
            code="invitation_email_mismatch",
        )

    membership = await repo.get_membership(session, invitation.org_id, user.id)
    if membership is None:
        membership = Membership(
            org_id=invitation.org_id,
            user_id=user.id,
            role=invitation.role,
            status=MembershipStatus.ACTIVE,
            joined_at=utcnow(),
        )
        session.add(membership)
    elif membership.status is not MembershipStatus.ACTIVE:
        # Accepting a fresh invitation reinstates a disabled member.
        membership.status = MembershipStatus.ACTIVE
        membership.role = invitation.role

    invitation.accepted_at = invitation.accepted_at or utcnow()
    invitation.accepted_user_id = user.id
    await session.flush()

    logger.info(
        "invitation_accepted",
        org_id=str(invitation.org_id),
        invitation_id=str(invitation.id),
        user_id=str(user.id),
    )
    return membership, user


async def _require_pending_invitation(
    session: AsyncSession, org_id: UUID, invitation_id: UUID
) -> Invitation:
    invitation = await repo.get_invitation_by_id(session, org_id, invitation_id)
    if invitation is None or not invitation.is_pending:
        raise NotFoundError("No pending invitation with that id.", code="invitation_not_found")
    return invitation


async def _resolve_usable_invitation(session: AsyncSession, token: str) -> Invitation:
    """Look up an invitation by raw token, rejecting dead or expired ones.

    Unknown, revoked and already-accepted tokens all look the same from the
    outside, so a token guess reveals nothing.
    """
    invitation = await repo.get_invitation_by_token_hash(session, hash_token(token))
    if invitation is None or not invitation.is_pending:
        raise NotFoundError("This invitation link is not valid.", code="invitation_not_found")
    if not invitation.is_usable():
        raise ValidationError(
            "This invitation has expired. Ask an admin to send a new one.",
            code="invitation_expired",
        )
    return invitation


def _inviter_name(user: User | None) -> str | None:
    return user.full_name if user is not None else None


# --------------------------------------------------------------------------
# email
# --------------------------------------------------------------------------
async def _send_invitation_email(
    session: AsyncSession,
    *,
    org: Organization,
    invitation: Invitation,
    inviter: User,
    raw_token: str,
    dedupe_key: str,
) -> None:
    """Queue the invitation email.

    Kept behind this indirection so tests can monkeypatch it in one place.
    """
    invitee = await repo.get_user_by_email(session, invitation.email)
    await enqueue(
        session,
        template_key="invitation",
        to_email=invitation.email,
        to_name=invitee.full_name if invitee is not None else None,
        org_id=org.id,
        dedupe_key=dedupe_key,
        context={
            "inviter_name": inviter.full_name,
            "org_name": org.name,
            "role": invitation.role.value,
            "accept_url": f"{settings.app_url}/invite/accept?token={raw_token}",
            "expires_at": _format_expiry(invitation, org.timezone),
            "invitee_has_account": invitee is not None,
        },
    )


def _format_expiry(invitation: Invitation, tz_name: str) -> str:
    """Human-readable expiry in the organization's own time zone."""
    try:
        local = to_timezone(invitation.expires_at, tz_name)
    except Exception:  # pragma: no cover - a bad stored zone must not block email
        local = to_timezone(invitation.expires_at, DEFAULT_TIMEZONE)
    return local.strftime("%d %b %Y, %H:%M %Z")
