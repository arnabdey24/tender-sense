"""Shared pytest fixtures."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("SECRET_KEY", "test-secret-key-0123456789abcdef0123456789abcdef")
os.environ.setdefault("AI_PROVIDER", "fake")
os.environ.setdefault("LOG_JSON", "false")


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """HTTP client bound to the ASGI app without a live server."""
    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
