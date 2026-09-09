"""End-to-end checks against real Postgres and Redis."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.db.session import dispose_engine, session_scope
from app.jobs.queue import close_queue, get_queue
from app.jobs.tasks.maintenance import ping


@pytest.fixture(autouse=True)
async def _cleanup_connections() -> AsyncIterator[None]:
    yield
    await close_queue()
    await dispose_engine()


async def test_required_extensions_are_installed() -> None:
    async with session_scope() as session:
        rows = await session.execute(
            text("SELECT extname FROM pg_extension WHERE extname = ANY(:names)"),
            {"names": ["vector", "citext", "pg_trgm"]},
        )
        installed = {row[0] for row in rows}

    assert installed == {"vector", "citext", "pg_trgm"}


async def test_migrations_have_been_applied() -> None:
    async with session_scope() as session:
        version = (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar()

    assert version is not None


async def test_readiness_reports_both_dependencies(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": True, "redis": True}


async def test_ping_task_reaches_the_database() -> None:
    result = await ping({"job_id": "test-job"})

    assert result["pong"] is True
    assert result["database"] is True


async def test_jobs_can_be_enqueued() -> None:
    queue = await get_queue()

    job = await queue.enqueue_job("ping")

    assert job is not None
    assert await job.status() is not None
