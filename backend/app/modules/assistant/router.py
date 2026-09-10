"""Organization-authenticated assistant endpoints."""

from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.deps import BearerToken, CurrentOrg, DbSession
from app.core.exceptions import ConflictError, NotFoundError
from app.core.time import utcnow
from app.modules.assistant import service
from app.modules.assistant.context import load_context
from app.modules.assistant.models import AssistantMessage, Conversation
from app.modules.assistant.schemas import (
    Capabilities,
    ConversationCreate,
    ConversationDetail,
    ConversationRead,
    TurnInput,
    VoiceTicket,
)
from app.modules.tenders.service import get_tender_detail

router = APIRouter(prefix="/assistant", tags=["assistant"])


def enabled() -> None:
    if not settings.assistant_enabled:
        raise NotFoundError("Assistant is disabled.")


@router.get("/capabilities", response_model=Capabilities)
async def capabilities(_: CurrentOrg) -> Capabilities:
    configured = settings.ai_provider == "fake" or bool(settings.gemini_api_key)
    return Capabilities(
        enabled=settings.assistant_enabled,
        voice_enabled=settings.assistant_enabled
        and settings.assistant_voice_enabled
        and bool(settings.gemini_api_key)
        and settings.ai_provider == "gemini",
        mode="demo"
        if settings.ai_provider == "fake"
        else "gemini"
        if configured
        else "unavailable",
        voice_max_seconds=settings.assistant_voice_max_seconds,
    )


@router.get("/conversations", response_model=list[ConversationRead])
async def list_conversations(
    ctx: CurrentOrg, db: DbSession, tender_id: UUID | None = None
) -> list[Conversation]:
    enabled()
    cutoff = utcnow() - timedelta(days=settings.assistant_retention_days)
    await db.execute(
        delete(Conversation).where(
            Conversation.org_id == ctx.org_id,
            Conversation.user_id == ctx.user.id,
            Conversation.updated_at < cutoff,
        )
    )
    query = select(Conversation).where(
        Conversation.org_id == ctx.org_id, Conversation.user_id == ctx.user.id
    )
    if tender_id:
        query = query.where(Conversation.tender_id == tender_id)
    return list(await db.scalars(query.order_by(Conversation.updated_at.desc()).limit(50)))


@router.post("/conversations", response_model=ConversationRead, status_code=201)
async def create_conversation(
    data: ConversationCreate, ctx: CurrentOrg, db: DbSession
) -> Conversation:
    enabled()
    # No tender is a workspace conversation: the assistant answers from the
    # graded shortlist and can open a notice from it.
    if data.tender_id is None:
        title = "Workspace"
    else:
        tender = await get_tender_detail(db, data.tender_id)
        title = tender.title[:500]
    conversation = Conversation(
        org_id=ctx.org_id, user_id=ctx.user.id, tender_id=data.tender_id, title=title
    )
    db.add(conversation)
    await db.flush()
    return conversation


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: UUID, ctx: CurrentOrg, db: DbSession
) -> ConversationDetail:
    enabled()
    conversation = await service.owned(db, conversation_id, ctx.org_id, ctx.user.id)
    return ConversationDetail(
        **ConversationRead.model_validate(conversation).model_dump(),
        messages=[service.message_read(m) for m in await service.messages(db, conversation_id)],
    )


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: UUID, ctx: CurrentOrg, db: DbSession) -> None:
    enabled()
    conversation = await service.owned(db, conversation_id, ctx.org_id, ctx.user.id)
    lock = await service.acquire(conversation_id, 10)
    try:
        await db.delete(conversation)
        await db.commit()
    finally:
        await service.release(conversation_id, lock)


@router.post("/conversations/{conversation_id}/turns")
async def turn(
    conversation_id: UUID, data: TurnInput, ctx: CurrentOrg, db: DbSession
) -> StreamingResponse:
    enabled()
    conversation = await service.owned(db, conversation_id, ctx.org_id, ctx.user.id)
    previous = await db.scalar(
        select(AssistantMessage).where(
            AssistantMessage.conversation_id == conversation_id,
            AssistantMessage.request_id == data.request_id,
            AssistantMessage.role == "assistant",
        )
    )
    headers = {"Cache-Control": "no-store", "X-Accel-Buffering": "no"}
    if previous:
        if previous.status == "streaming" and previous.updated_at > utcnow() - timedelta(
            seconds=settings.assistant_turn_timeout_seconds + 15
        ):
            raise ConflictError(
                "This response is still running. Reopen the conversation to restore it."
            )
        return StreamingResponse(
            service.replay(previous), media_type="text/event-stream", headers=headers
        )
    lock = await service.acquire(conversation_id, settings.assistant_turn_timeout_seconds + 15)
    try:
        await service.reserve(ctx.org_id, "assistant turns", 1, settings.assistant_daily_turn_limit)
        context = await load_context(db, ctx.org_id, conversation.tender_id)
        past = await service.messages(db, conversation_id)
        history = [{"role": m.role, "content": m.content} for m in past if m.status == "complete"]
        user_message = service.new_message(conversation_id, data.request_id, "user", data.text)
        assistant = service.new_message(
            conversation_id, data.request_id, "assistant", status="streaming"
        )
        db.add_all([user_message, assistant])
        conversation.updated_at = utcnow()
        await db.commit()
    except Exception:
        await service.release(conversation_id, lock)
        raise
    return StreamingResponse(
        service.stream_turn(
            conversation, assistant.id, data, context, history, len(past) // 2 + 1, lock
        ),
        media_type="text/event-stream",
        headers=headers,
    )


@router.post("/conversations/{conversation_id}/voice-ticket", response_model=VoiceTicket)
async def voice_ticket(
    conversation_id: UUID, ctx: CurrentOrg, db: DbSession, credentials: BearerToken
) -> VoiceTicket:
    enabled()
    if (
        not settings.assistant_voice_enabled
        or settings.ai_provider != "gemini"
        or not settings.gemini_api_key
    ):
        raise ConflictError(
            "Live voice is not configured for this deployment. Text analysis is available."
        )
    await service.owned(db, conversation_id, ctx.org_id, ctx.user.id)
    assert credentials is not None
    return VoiceTicket(ticket=await service.ticket(conversation_id, credentials.credentials))
