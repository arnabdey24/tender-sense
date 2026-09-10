"""The notification centre, delivery settings and the recipient list.

Two audiences share this module. Members read and clear their own notifications;
admins decide what the organization is told and which addresses it is told at.
The verify and unsubscribe endpoints belong to neither — they answer links in
an email, so they take no session at all.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Path, Query, status

from app.core.deps import CurrentOrg, DbSession, RequireOrgAdmin
from app.core.rate_limit import enforce_rate_limit
from app.modules.notifications import repository as repo
from app.modules.notifications import service
from app.modules.notifications.email import outbox
from app.modules.notifications.schemas import (
    NotificationRead,
    NotificationSettingsRead,
    NotificationSettingsUpdate,
    PublicActionResponse,
    RecipientCreate,
    RecipientRead,
    RecipientUpdate,
    TestEmailRequest,
    TestEmailResponse,
    UnreadCount,
)
from app.modules.orgs.models import Organization

router = APIRouter(tags=["notifications"])

RecipientId = Annotated[UUID, Path(description="Recipient identifier")]
NotificationId = Annotated[UUID, Path(description="Notification identifier")]


# --- the in-app centre ---------------------------------------------------


@router.get("/notifications", response_model=list[NotificationRead], summary="Notification centre")
async def list_notifications(
    ctx: CurrentOrg,
    db: DbSession,
    unread_only: Annotated[bool, Query(description="Only what this user has not read")] = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[NotificationRead]:
    """Recent notifications for the organization, newest first.

    Read state is per user: one person clearing their badge does not hide a new
    match from their colleagues.
    """
    rows = await repo.list_notifications(
        db,
        ctx.org_id,
        ctx.user.id,
        unread_only=unread_only,
        limit=limit,
        offset=offset,
    )
    return [
        NotificationRead.model_validate(notification).model_copy(update={"read": is_read})
        for notification, is_read in rows
    ]


@router.get(
    "/notifications/unread-count",
    response_model=UnreadCount,
    summary="Badge count",
)
async def unread_count(ctx: CurrentOrg, db: DbSession) -> UnreadCount:
    return UnreadCount(unread=await repo.unread_count(db, ctx.org_id, ctx.user.id))


@router.post(
    "/notifications/read-all",
    response_model=UnreadCount,
    summary="Mark everything read",
)
async def read_all(ctx: CurrentOrg, db: DbSession) -> UnreadCount:
    await service.mark_all_read(db, org_id=ctx.org_id, user_id=ctx.user.id)
    return UnreadCount(unread=0)


@router.post(
    "/notifications/{notification_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark one read",
)
async def read_one(notification_id: NotificationId, ctx: CurrentOrg, db: DbSession) -> None:
    await service.mark_read(
        db, org_id=ctx.org_id, user_id=ctx.user.id, notification_id=notification_id
    )


# --- settings ------------------------------------------------------------


@router.get(
    "/notification-settings",
    response_model=NotificationSettingsRead,
    summary="Delivery preferences",
)
async def get_settings(ctx: CurrentOrg, db: DbSession) -> NotificationSettingsRead:
    """Created with sensible defaults on first read, in the org's own timezone."""
    record = await service.settings_for(db, ctx.org)
    return NotificationSettingsRead.model_validate(record)


@router.put(
    "/notification-settings",
    response_model=NotificationSettingsRead,
    summary="Update delivery preferences",
)
async def update_settings(
    data: NotificationSettingsUpdate, ctx: RequireOrgAdmin, db: DbSession
) -> NotificationSettingsRead:
    record = await service.update_settings(db, ctx.org, data)
    return NotificationSettingsRead.model_validate(record)


@router.post(
    "/notification-settings/test-email",
    response_model=TestEmailResponse,
    summary="Send a test message",
)
async def send_test_email(
    ctx: RequireOrgAdmin,
    db: DbSession,
    data: Annotated[TestEmailRequest, Body()] = TestEmailRequest(),
) -> TestEmailResponse:
    """Prove delivery works before the first real alert depends on it.

    Rate limited per organization: this endpoint takes an arbitrary address and
    sends mail to it, which is a spam cannon if left uncapped.
    """
    await enforce_rate_limit(
        f"test-email:{ctx.org_id}",
        limit=5,
        window_seconds=3600,
        message="Too many test messages. Try again in an hour.",
    )
    to_email = str(data.email) if data.email else ctx.user.email
    await outbox.enqueue(
        db,
        template_key="test_email",
        to_email=to_email,
        to_name=ctx.user.full_name,
        org_id=ctx.org_id,
        context={
            "organization_name": ctx.org.name,
            "triggered_by": ctx.user.full_name or ctx.user.email,
        },
    )
    return TestEmailResponse(queued=True, to_email=to_email)


# --- recipients ----------------------------------------------------------


@router.get(
    "/notification-recipients",
    response_model=list[RecipientRead],
    summary="Who receives this organization's mail",
)
async def list_recipients(ctx: CurrentOrg, db: DbSession) -> list[RecipientRead]:
    return [
        RecipientRead.model_validate(recipient)
        for recipient in await repo.list_recipients(db, ctx.org_id)
    ]


@router.post(
    "/notification-recipients",
    response_model=RecipientRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a recipient",
)
async def add_recipient(
    data: RecipientCreate, ctx: RequireOrgAdmin, db: DbSession
) -> RecipientRead:
    """Register an address and email it a confirmation link.

    Nothing is sent to it until someone holding it confirms — otherwise this
    form would let one admin route a tender shortlist anywhere they liked.
    """
    await enforce_rate_limit(
        f"recipient-add:{ctx.org_id}",
        limit=20,
        window_seconds=3600,
        message="Too many recipients added. Try again in an hour.",
    )
    created = await service.add_recipient(db, org=ctx.org, data=data, added_by_id=ctx.user.id)
    return RecipientRead.model_validate(created.recipient)


@router.patch(
    "/notification-recipients/{recipient_id}",
    response_model=RecipientRead,
    summary="Change what a recipient receives",
)
async def update_recipient(
    recipient_id: RecipientId,
    data: RecipientUpdate,
    ctx: RequireOrgAdmin,
    db: DbSession,
) -> RecipientRead:
    recipient = await service.update_recipient(
        db, org_id=ctx.org_id, recipient_id=recipient_id, data=data
    )
    return RecipientRead.model_validate(recipient)


@router.delete(
    "/notification-recipients/{recipient_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a recipient",
)
async def remove_recipient(recipient_id: RecipientId, ctx: RequireOrgAdmin, db: DbSession) -> None:
    await service.remove_recipient(db, org_id=ctx.org_id, recipient_id=recipient_id)


@router.post(
    "/notification-recipients/{recipient_id}/resend",
    response_model=RecipientRead,
    summary="Resend the confirmation link",
)
async def resend_verification(
    recipient_id: RecipientId, ctx: RequireOrgAdmin, db: DbSession
) -> RecipientRead:
    """Issues a fresh token, so an old link sitting in an inbox stops working."""
    await enforce_rate_limit(
        f"recipient-resend:{ctx.org_id}",
        limit=10,
        window_seconds=3600,
        message="Too many confirmation emails. Try again in an hour.",
    )
    recipient = await service.resend_verification(db, org=ctx.org, recipient_id=recipient_id)
    return RecipientRead.model_validate(recipient)


# --- links in emails, which carry no session -----------------------------


@router.post(
    "/notifications/verify-recipient",
    response_model=PublicActionResponse,
    summary="Confirm an address from an emailed link",
)
async def verify_recipient(
    db: DbSession, token: Annotated[str, Body(embed=True, min_length=10, max_length=200)]
) -> PublicActionResponse:
    """Unauthenticated on purpose: the person confirming may have no account."""
    recipient = await service.verify_recipient(db, token)
    org = await db.get(Organization, recipient.org_id)
    return PublicActionResponse(
        status="verified",
        email=recipient.email,
        organization=org.name if org else None,
    )


@router.post(
    "/notifications/unsubscribe",
    response_model=PublicActionResponse,
    summary="Stop mail to an address",
)
async def unsubscribe(
    db: DbSession, token: Annotated[str, Body(embed=True, min_length=10, max_length=200)]
) -> PublicActionResponse:
    """Honoured immediately and permanently, with nothing asked in return.

    The link keeps working after the first click, because someone re-clicking
    an old message and being told "invalid link" concludes it failed — and
    reports the next message as spam instead.
    """
    recipient = await service.unsubscribe_recipient(db, token)
    return PublicActionResponse(status="unsubscribed", email=recipient.email)
