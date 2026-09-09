"""Organization, member and invitation endpoints.

Everything under ``/orgs/current`` resolves the active organization from the
access token, so the client never passes an org id and cannot address a tenant
it is not a member of.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, status

from app.core.deps import CurrentOrg, DbSession, RequireOrgAdmin, VerifiedUser
from app.core.pagination import Page, PageParams, page_params
from app.modules.orgs import service
from app.modules.orgs.schemas import (
    InvitationCreate,
    InvitationPreview,
    InvitationRead,
    MemberRead,
    MemberUpdate,
    OrganizationCreate,
    OrganizationRead,
    OrganizationUpdate,
)

router = APIRouter(tags=["organizations"])

PageParamsDep = Annotated[PageParams, Depends(page_params)]
UserIdPath = Annotated[UUID, Path(description="Id of the member's user account.")]
InvitationIdPath = Annotated[UUID, Path(description="Id of the invitation.")]


@router.post(
    "/orgs",
    response_model=OrganizationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an organization",
)
async def create_organization(
    data: OrganizationCreate, user: VerifiedUser, db: DbSession
) -> OrganizationRead:
    """Create an organization; the caller becomes its first active admin.

    The current access token does not carry the new organization. Refresh it
    before calling any `/orgs/current` endpoint, otherwise those requests are
    rejected as having no active organization.
    """
    org, _membership = await service.create_organization(db, user=user, data=data)
    return OrganizationRead.model_validate(org)


@router.get("/orgs/current", response_model=OrganizationRead, summary="Read the current org")
async def read_current_organization(ctx: CurrentOrg) -> OrganizationRead:
    """Return the profile of the caller's active organization."""
    return OrganizationRead.model_validate(ctx.org)


@router.patch("/orgs/current", response_model=OrganizationRead, summary="Update the current org")
async def update_current_organization(
    data: OrganizationUpdate, ctx: RequireOrgAdmin, db: DbSession
) -> OrganizationRead:
    """Update the organization profile. Admin only; the slug never changes."""
    org = await service.update_organization(db, ctx.org, data)
    return OrganizationRead.model_validate(org)


@router.get(
    "/orgs/current/members",
    response_model=Page[MemberRead],
    summary="List members",
)
async def list_members(ctx: CurrentOrg, db: DbSession, params: PageParamsDep) -> Page[MemberRead]:
    """List the organization's members, oldest first."""
    return await service.list_members(db, ctx.org.id, params)


@router.patch(
    "/orgs/current/members/{user_id}",
    response_model=MemberRead,
    summary="Change a member's role or status",
)
async def update_member(
    user_id: UserIdPath, data: MemberUpdate, ctx: RequireOrgAdmin, db: DbSession
) -> MemberRead:
    """Change a member's role or status.

    You cannot change your own role, and the last active admin can be neither
    demoted nor disabled.
    """
    membership, user = await service.update_member(
        db, org=ctx.org, actor=ctx.user, target_user_id=user_id, data=data
    )
    return MemberRead.from_row(membership, user)


@router.delete(
    "/orgs/current/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a member",
)
async def remove_member(user_id: UserIdPath, ctx: RequireOrgAdmin, db: DbSession) -> None:
    """Remove a member. You may remove yourself unless you are the last admin."""
    await service.remove_member(db, org=ctx.org, actor=ctx.user, target_user_id=user_id)


@router.get(
    "/orgs/current/invitations",
    response_model=list[InvitationRead],
    summary="List invitations",
)
async def list_invitations(ctx: RequireOrgAdmin, db: DbSession) -> list[InvitationRead]:
    """List every invitation ever sent for this organization, newest first."""
    return await service.list_invitations(db, ctx.org.id)


@router.post(
    "/orgs/current/invitations",
    response_model=InvitationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Invite someone",
)
async def create_invitation(
    data: InvitationCreate, ctx: RequireOrgAdmin, db: DbSession
) -> InvitationRead:
    """Email an invitation link.

    Any live invitation for the same address is revoked and replaced, so
    re-inviting is always safe. Inviting an existing member is a conflict.
    """
    invitation, _token = await service.invite_member(db, org=ctx.org, inviter=ctx.user, data=data)
    return await service.read_invitation(db, invitation)


@router.post(
    "/orgs/current/invitations/{invitation_id}/resend",
    response_model=InvitationRead,
    summary="Resend an invitation",
)
async def resend_invitation(
    invitation_id: InvitationIdPath, ctx: RequireOrgAdmin, db: DbSession
) -> InvitationRead:
    """Send a fresh link and extend the expiry. The previous link stops working."""
    invitation, _token = await service.resend_invitation(
        db, org=ctx.org, inviter=ctx.user, invitation_id=invitation_id
    )
    return await service.read_invitation(db, invitation)


@router.delete(
    "/orgs/current/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke an invitation",
)
async def revoke_invitation(
    invitation_id: InvitationIdPath, ctx: RequireOrgAdmin, db: DbSession
) -> None:
    """Revoke a pending invitation, invalidating its link immediately."""
    await service.revoke_invitation(db, org=ctx.org, invitation_id=invitation_id)


@router.get(
    "/invitations/{token}",
    response_model=InvitationPreview,
    summary="Preview an invitation",
)
async def preview_invitation(token: str, db: DbSession) -> InvitationPreview:
    """Public: describe an invitation so the accept screen can be rendered.

    Requires no authentication — the token is the credential. Returns only the
    organization's name, the inviter, the role and whether the invitee still
    needs to sign up.
    """
    return await service.preview_invitation(db, token)


@router.post(
    "/invitations/{token}/accept",
    response_model=MemberRead,
    summary="Accept an invitation",
)
async def accept_invitation(token: str, user: VerifiedUser, db: DbSession) -> MemberRead:
    """Join the inviting organization as the signed-in user.

    The signed-in address must match the invited one. Accepting twice is
    harmless and returns the existing membership. Obtain a new access token
    afterwards to make the new organization active.
    """
    membership, member = await service.accept_invitation(db, token=token, user=user)
    return MemberRead.from_row(membership, member)
