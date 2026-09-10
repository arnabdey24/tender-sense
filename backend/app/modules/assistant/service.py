"""Persistence and bounded, idempotent conversation turns."""

import json
import secrets
from collections.abc import AsyncIterator, Awaitable
from datetime import timedelta
from typing import Any, cast
from uuid import UUID

import anyio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import Usage
from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError, RateLimitedError
from app.core.ids import new_id
from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.session import session_scope
from app.jobs.queue import get_queue
from app.modules.assistant.models import AssistantMessage, Conversation
from app.modules.assistant.provider import generate
from app.modules.assistant.schemas import Event, MessageRead, TurnInput
from app.modules.matching.ai_usage import record

logger = get_logger(__name__)


async def owned(
    db: AsyncSession, conversation_id: UUID, org_id: UUID, user_id: UUID
) -> Conversation:
    conversation = await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.org_id == org_id,
            Conversation.user_id == user_id,
            Conversation.updated_at >= utcnow() - timedelta(days=settings.assistant_retention_days),
        )
    )
    if conversation is None:
        raise NotFoundError("Conversation not found.")
    return conversation


async def messages(db: AsyncSession, conversation_id: UUID) -> list[AssistantMessage]:
    return list(
        await db.scalars(
            select(AssistantMessage)
            .where(AssistantMessage.conversation_id == conversation_id)
            .order_by(AssistantMessage.created_at, AssistantMessage.id)
        )
    )


def message_read(message: AssistantMessage) -> MessageRead:
    return MessageRead(
        id=message.id,
        request_id=message.request_id,
        role=message.role,
        content=message.content,
        status=message.status,
        created_at=message.created_at,
        sources=message.payload.get("sources", []),
        artifacts=message.payload.get("artifacts", []),
        context_version=message.payload.get("context_version", ""),
    )


async def reserve(org_id: UUID, kind: str, amount: int, limit: int) -> None:
    """Fail closed for new paid work if Redis is unavailable."""
    redis = await get_queue()
    key = f"assistant:budget:{org_id}:{utcnow().date()}:{kind}"
    used = await redis.incrby(key, amount)
    await redis.expire(key, 172800)
    if used > limit:
        await redis.decrby(key, amount)
        raise RateLimitedError(f"Your organization's daily {kind} limit has been reached.")


async def refund(org_id: UUID, kind: str, amount: int) -> None:
    """Give back budget that was reserved up front but never spent.

    ``reserve`` has to claim the whole session length before the session starts,
    because there is no way to know in advance how long someone will talk. Left
    unrefunded, a ten-second call costs the same as a ten-minute one and a day's
    allowance disappears in six taps of the microphone.
    """
    if amount <= 0:
        return
    redis = await get_queue()
    key = f"assistant:budget:{org_id}:{utcnow().date()}:{kind}"
    remaining = await redis.decrby(key, amount)
    # A refund can outlive the counter it belongs to — the key expires daily, and
    # an operator can reset it mid-session. Landing below zero would hand the
    # organization free allowance tomorrow, so the floor is zero.
    if remaining < 0:
        await redis.set(key, 0, keepttl=True)


async def acquire(conversation_id: UUID, seconds: int) -> str:
    redis = await get_queue()
    token = secrets.token_urlsafe(24)
    if not await redis.set(f"assistant:active:{conversation_id}", token, ex=seconds, nx=True):
        raise ConflictError("A response or voice session is already active in this conversation.")
    return token


async def release(conversation_id: UUID, token: str) -> None:
    redis = await get_queue()
    await cast(
        Awaitable[Any],
        redis.eval(
            "if redis.call('get', KEYS[1]) == ARGV[1] then return "
            "redis.call('del', KEYS[1]) end return 0",
            1,
            f"assistant:active:{conversation_id}",
            token,
        ),
    )


async def save_message(
    message_id: UUID, content: str, status: str, payload: dict[str, Any]
) -> None:
    async with session_scope() as db:
        await db.execute(
            update(AssistantMessage)
            .where(AssistantMessage.id == message_id)
            .values(content=content, status=status, payload=payload)
        )


def encode(event: Event, sequence: int) -> str:
    return f"id: {sequence}\ndata: {event.model_dump_json()}\n\n"


async def stream_turn(
    conversation: Conversation,
    assistant_id: UUID,
    turn: TurnInput,
    context: dict[str, Any],
    history: list[dict[str, str]],
    version: int,
    lock: str,
) -> AsyncIterator[str]:
    content = ""
    artifacts: list[dict[str, Any]] = []
    sequence = 0
    status = "interrupted"
    usage = {"input": 0, "output": 0}
    last_saved = utcnow()
    payload: dict[str, Any] = {
        "context_version": context["version"],
        "context": context,
        "sources": context["sources"],
        "artifacts": artifacts,
    }
    try:
        yield encode(
            Event(
                type="start",
                turn_id=str(turn.request_id),
                data={
                    "message_id": str(assistant_id),
                    "sources": context["sources"],
                    "context_version": context["version"],
                },
            ),
            sequence,
        )
        with anyio.fail_after(settings.assistant_turn_timeout_seconds):
            async for event in generate(context, history, turn, version):
                if event.type == "usage":
                    usage = event.data
                    continue
                if event.type == "text":
                    content += event.data["text"]
                if event.type == "artifact":
                    artifacts.append(event.data)
                event.turn_id = str(turn.request_id)
                sequence += 1
                yield encode(event, sequence)
                if (utcnow() - last_saved).total_seconds() > 2:
                    await save_message(assistant_id, content, "streaming", payload)
                    last_saved = utcnow()
        status = "complete"
        await save_message(assistant_id, content, status, payload)
        sequence += 1
        yield encode(Event(type="complete", turn_id=str(turn.request_id)), sequence)
    except Exception as exc:
        status = "error"
        logger.warning("assistant_turn_failed", error_type=type(exc).__name__)
        sequence += 1
        yield encode(
            Event(
                type="error",
                turn_id=str(turn.request_id),
                data={
                    "message": (
                        "The assistant could not finish. Your conversation has "
                        "been saved; please try again."
                    )
                },
            ),
            sequence,
        )
    finally:
        with anyio.CancelScope(shield=True):
            await save_message(assistant_id, content, status, payload)
            if usage["input"] or usage["output"]:
                async with session_scope() as db:
                    await record(
                        db,
                        Usage(
                            model=settings.assistant_model,
                            tokens_in=usage["input"],
                            tokens_out=usage["output"],
                        ),
                        purpose="assistant_text",
                        org_id=conversation.org_id,
                    )
            await release(conversation.id, lock)


async def replay(message: AssistantMessage) -> AsyncIterator[str]:
    yield encode(
        Event(
            type="start",
            turn_id=str(message.request_id),
            data={
                "message_id": str(message.id),
                "sources": message.payload.get("sources", []),
                "context_version": message.payload.get("context_version", ""),
            },
        ),
        0,
    )
    yield encode(
        Event(type="text", turn_id=str(message.request_id), data={"text": message.content}), 1
    )
    for i, artifact in enumerate(message.payload.get("artifacts", []), start=2):
        yield encode(Event(type="artifact", turn_id=str(message.request_id), data=artifact), i)
    yield encode(
        Event(
            type="complete" if message.status == "complete" else "error",
            turn_id=str(message.request_id),
            data={"message": "This response was interrupted. Send a new message to continue."},
        ),
        9999,
    )


async def ticket(conversation_id: UUID, access_token: str) -> str:
    value = secrets.token_urlsafe(32)
    redis = await get_queue()
    await redis.set(
        f"assistant:ticket:{value}",
        json.dumps({"conversation_id": str(conversation_id), "access_token": access_token}),
        ex=30,
    )
    return value


def new_message(
    conversation_id: UUID, request_id: UUID, role: str, content: str = "", status: str = "complete"
) -> AssistantMessage:
    return AssistantMessage(
        id=new_id(),
        conversation_id=conversation_id,
        request_id=request_id,
        role=role,
        content=content,
        status=status,
        payload={},
    )
