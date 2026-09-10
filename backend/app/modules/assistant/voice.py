"""Authenticated audio relay. Media is transient; only transcripts are persisted."""

import asyncio
import base64
import contextlib
import json
import time
from typing import Any

import anyio
from fastapi import Request, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPAuthorizationCredentials
from google import genai
from google.genai import types

from app.ai.base import Usage
from app.core.config import settings
from app.core.deps import get_current_org, get_current_user
from app.core.exceptions import ConflictError, RateLimitedError
from app.core.ids import new_id
from app.core.logging import get_logger
from app.db.session import session_scope
from app.jobs.queue import get_queue
from app.modules.assistant import service
from app.modules.assistant.context import load_context
from app.modules.assistant.provider import (
    declaration,
    instruction,
    navigate_declaration,
    resolve_navigation,
)
from app.modules.assistant.router import router
from app.modules.assistant.schemas import AnalyzeInput, Event
from app.modules.assistant.tools import analyze
from app.modules.matching.ai_usage import record

logger = get_logger(__name__)


@router.websocket("/voice")
async def voice_socket(socket: WebSocket) -> None:
    if (
        not settings.assistant_enabled
        or not settings.assistant_voice_enabled
        or not settings.gemini_api_key
    ):
        await socket.close(code=1008)
        return
    allowed = {settings.app_url.rstrip("/"), *settings.backend_cors_origins}
    if socket.headers.get("origin") not in allowed:
        await socket.close(code=1008)
        return
    await socket.accept()
    lock: str | None = None
    reserved = 0
    started_at = 0.0
    conversation = None
    data: dict[str, Any] = {}
    current_id = new_id()
    texts = {"user": "", "assistant": ""}
    artifacts: list[dict[str, Any]] = []
    sent_lock = asyncio.Lock()
    sequence = 0
    usage_in = usage_out = 0

    async def emit(kind: str, payload: dict[str, Any] | None = None) -> None:
        async with sent_lock:
            await socket.send_json(
                Event(type=kind, turn_id=str(current_id), data=payload or {}).model_dump(
                    mode="json"
                )
            )

    async def persist(status: str) -> None:
        if conversation is None:
            return
        async with session_scope() as db:
            # Recheck ownership; a deleted/revoked conversation cannot be resurrected.
            await service.owned(db, conversation.id, conversation.org_id, conversation.user_id)
            for role, text in texts.items():
                if not text and (role != "assistant" or not artifacts):
                    continue
                message = service.new_message(conversation.id, current_id, role, text, status)
                message.payload = {
                    "context_version": data["version"],
                    "sources": data["sources"],
                    "artifacts": artifacts if role == "assistant" else [],
                    "context": data,
                }
                db.add(message)

    try:
        with anyio.fail_after(5):
            hello = await socket.receive_json()
        if not isinstance(hello, dict) or len(str(hello.get("ticket", ""))) > 100:
            raise ValueError("Invalid voice ticket")
        redis = await get_queue()
        raw = await redis.getdel(f"assistant:ticket:{hello.get('ticket', '')}")
        if not raw:
            raise ValueError("Expired voice ticket")
        ticket = json.loads(raw)
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=ticket["access_token"]
        )

        async def authenticate() -> None:
            async with session_scope() as db:
                user = await get_current_user(db, credentials)
                await get_current_org(Request({"type": "http"}), db, user, credentials)

        async with session_scope() as db:
            user = await get_current_user(db, credentials)
            ctx = await get_current_org(Request({"type": "http"}), db, user, credentials)
            from uuid import UUID

            conversation = await service.owned(
                db, UUID(ticket["conversation_id"]), ctx.org_id, user.id
            )
            data = await load_context(db, ctx.org_id, conversation.tender_id)
            past = await service.messages(db, conversation.id)
            history = [
                {"role": m.role, "content": m.content} for m in past[-24:] if m.status == "complete"
            ]
        duration = max(30, min(settings.assistant_voice_max_seconds, 600))
        lock = await service.acquire(conversation.id, duration + 15)
        await service.reserve(
            conversation.org_id, "voice seconds", duration, settings.assistant_daily_voice_seconds
        )
        reserved = duration
        started_at = time.monotonic()
        language = hello.get("language", "auto")
        if language not in {"auto", "en", "bn"}:
            raise ValueError("Unsupported language")
        # Picking a language narrows the recogniser to it; "auto" still only ever
        # offers the product's two, never the whole set it would guess across.
        language_codes = list(settings.assistant_voice_languages)
        if language != "auto":
            prefix = "bn" if language == "bn" else "en"
            language_codes = [c for c in language_codes if c.startswith(prefix)] or language_codes
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            # Without this the Live API picks its own default voice. No
            # language_code: the conversation is English, Bangla or a mix of
            # both, and pinning one makes the other side of that worse.
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=settings.assistant_voice_name
                    )
                )
            ),
            system_instruction=instruction(data, language)
            + "\nPrior conversation:\n"
            + json.dumps(history, ensure_ascii=False),
            tools=[types.Tool(function_declarations=[declaration(), navigate_declaration()])],
            # Unconstrained, Bangla speech comes back transcribed as Hindi in
            # Devanagari. This is the product's two languages and nothing else.
            input_audio_transcription=types.AudioTranscriptionConfig(language_codes=language_codes),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            context_window_compression=types.ContextWindowCompressionConfig(
                sliding_window=types.SlidingWindow()
            ),
            session_resumption=types.SessionResumptionConfig(),
        )
        # A bounded session is easy to resume from its persisted transcript. Provider
        # handles are held only in memory and never sent to the browser.
        async with genai.Client(api_key=settings.gemini_api_key.get_secret_value()).aio as client:
            with anyio.fail_after(duration):
                async with client.live.connect(
                    model=settings.assistant_voice_model, config=config
                ) as live:
                    await socket.send_json({"type": "ready"})
                    await emit(
                        "start", {"sources": data["sources"], "context_version": data["version"]}
                    )

                    async def incoming() -> None:
                        last_auth = time.monotonic()
                        window = time.monotonic()
                        byte_count = 0
                        while True:
                            packet = await socket.receive()
                            if packet["type"] == "websocket.disconnect":
                                return
                            if time.monotonic() - last_auth > 30:
                                await authenticate()
                                last_auth = time.monotonic()
                            if time.monotonic() - window > 1:
                                window = time.monotonic()
                                byte_count = 0
                            audio = packet.get("bytes")
                            if audio:
                                byte_count += len(audio)
                                if len(audio) > 64000 or len(audio) % 2 or byte_count > 96000:
                                    raise ValueError("Audio rate exceeded")
                                await live.send_realtime_input(
                                    audio=types.Blob(data=audio, mime_type="audio/pcm;rate=16000")
                                )
                            elif packet.get("text"):
                                if len(packet["text"]) > 9000:
                                    raise ValueError("Message too large")
                                command = json.loads(packet["text"])
                                if command.get("type") == "mute":
                                    await live.send_realtime_input(audio_stream_end=True)
                                elif command.get("type") == "text":
                                    text = str(command.get("text", ""))[:8000]
                                    texts["user"] += text
                                    await emit("transcript", {"role": "user", "text": text})
                                    await live.send_client_content(
                                        turns=types.Content(
                                            role="user", parts=[types.Part(text=text)]
                                        ),
                                        turn_complete=True,
                                    )

                    async def outgoing() -> None:
                        nonlocal current_id, sequence, usage_in, usage_out
                        while True:
                            async for response in live.receive():
                                if response.usage_metadata:
                                    usage_in = response.usage_metadata.prompt_token_count or 0
                                    usage_out += response.usage_metadata.response_token_count or 0
                                if response.go_away:
                                    await emit(
                                        "error",
                                        {
                                            "message": (
                                                "This voice session is ending. Start voice again "
                                                "to continue from your saved conversation."
                                            )
                                        },
                                    )
                                    return
                                content = response.server_content
                                if content:
                                    if content.interrupted:
                                        await emit("interrupted")
                                        await persist("interrupted")
                                        texts.update(user="", assistant="")
                                        artifacts.clear()
                                        current_id = new_id()
                                        await emit(
                                            "start",
                                            {
                                                "sources": data["sources"],
                                                "context_version": data["version"],
                                            },
                                        )
                                    for role, transcript in (
                                        ("user", content.input_transcription),
                                        ("assistant", content.output_transcription),
                                    ):
                                        if transcript and transcript.text:
                                            texts[role] += transcript.text
                                            await emit(
                                                "transcript",
                                                {"role": role, "text": transcript.text},
                                            )
                                    if content.model_turn:
                                        for part in content.model_turn.parts or []:
                                            if part.inline_data and part.inline_data.data:
                                                async with sent_lock:
                                                    await socket.send_json(
                                                        {
                                                            "type": "audio",
                                                            "audio": base64.b64encode(
                                                                part.inline_data.data
                                                            ).decode(),
                                                        }
                                                    )
                                    if content.turn_complete:
                                        await persist("complete")
                                        await emit("complete")
                                        texts.update(user="", assistant="")
                                        artifacts.clear()
                                        sequence += 1
                                        current_id = new_id()
                                        await emit(
                                            "start",
                                            {
                                                "sources": data["sources"],
                                                "context_version": data["version"],
                                            },
                                        )
                                if response.tool_call:
                                    answers = []
                                    for call in response.tool_call.function_calls or []:
                                        try:
                                            if call.name == "open_in_app":
                                                output = resolve_navigation(data, call.args or {})
                                                await emit("navigate", output)
                                                answers.append(
                                                    types.FunctionResponse(
                                                        name=call.name,
                                                        id=call.id,
                                                        response={"opened": output},
                                                    )
                                                )
                                                continue
                                            if call.name != "analyze_tender":
                                                raise ValueError("Unsupported tool")
                                            artifact = analyze(
                                                data,
                                                AnalyzeInput.model_validate(call.args or {}),
                                                version=len(past) // 2 + sequence + 1,
                                            )
                                            output = artifact.model_dump(mode="json")
                                            artifacts.append(output)
                                            await emit("artifact", output)
                                        except ValueError:
                                            output = {
                                                "error": (
                                                    "Invalid arguments. Ask the user to clarify."
                                                )
                                            }
                                        answers.append(
                                            types.FunctionResponse(
                                                name=call.name, id=call.id, response=output
                                            )
                                        )
                                    await live.send_tool_response(function_responses=answers)

                    tasks = [asyncio.create_task(incoming()), asyncio.create_task(outgoing())]
                    try:
                        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                        for task in done:
                            task.result()
                    finally:
                        for task in tasks:
                            task.cancel()
                        await asyncio.gather(*tasks, return_exceptions=True)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("assistant_voice_ended", error_type=type(exc).__name__)
        # A hit limit and a dropped connection are different problems with
        # different fixes, and "voice ended" sent the user looking for a fault
        # that was not there. Say which one it was.
        if isinstance(exc, RateLimitedError):
            message = (
                "Your organization has used today's live voice allowance. "
                "Typing still works, and voice is available again tomorrow."
            )
        elif isinstance(exc, ConflictError):
            message = (
                "This conversation already has a response or voice session "
                "running. Wait for it to finish, then start voice again."
            )
        else:
            message = (
                "Live voice ended. Your transcript is saved; "
                "you can continue by typing or start voice again."
            )
        with contextlib.suppress(Exception):
            await emit("error", {"message": message})
    finally:
        with anyio.CancelScope(shield=True):
            if conversation is not None and lock:
                with contextlib.suppress(Exception):
                    await persist("interrupted")
                    if usage_in or usage_out:
                        async with session_scope() as db:
                            await record(
                                db,
                                Usage(
                                    model=settings.assistant_voice_model,
                                    tokens_in=usage_in,
                                    tokens_out=usage_out,
                                ),
                                purpose="assistant_voice",
                                org_id=conversation.org_id,
                            )
                if reserved:
                    spent = int(time.monotonic() - started_at)
                    with contextlib.suppress(Exception):
                        await service.refund(
                            conversation.org_id,
                            "voice seconds",
                            max(0, reserved - spent),
                        )
                await service.release(conversation.id, lock)
            with contextlib.suppress(Exception):
                await socket.close()
