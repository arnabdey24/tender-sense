"""Picking the AI backend.

``AI_PROVIDER=fake`` swaps in the deterministic client, which is what the test
suite and `make seed` use. It is also the automatic fallback when the provider
is Gemini but no API key is configured, so a fresh checkout runs end to end
before anyone has signed up for a key.
"""

from __future__ import annotations

from app.ai.base import AIClient
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_client: AIClient | None = None


def build_client() -> AIClient:
    """Construct the configured client. Prefer :func:`get_ai_client`."""
    from app.ai.fake_client import FakeAIClient

    if settings.ai_provider == "fake":
        return FakeAIClient(dims=settings.embedding_dims)

    key = settings.gemini_api_key.get_secret_value() if settings.gemini_api_key else None
    if not key:
        logger.warning(
            "ai_provider_falling_back_to_fake",
            reason="GEMINI_API_KEY is not set",
        )
        return FakeAIClient(dims=settings.embedding_dims)

    from app.ai.gemini_client import GeminiClient

    return GeminiClient(api_key=key)


def get_ai_client() -> AIClient:
    """Process-wide client. Safe to call per task; construction is cached."""
    global _client
    if _client is None:
        _client = build_client()
        logger.info(
            "ai_client_ready",
            provider=settings.ai_provider,
            embedding_model=_client.embedding_model,
            generation_model=_client.generation_model,
        )
    return _client


def set_ai_client(client: AIClient | None) -> None:
    """Override the cached client. Tests use this to inject the fake."""
    global _client
    _client = client


__all__ = ["AIClient", "build_client", "get_ai_client", "set_ai_client"]
