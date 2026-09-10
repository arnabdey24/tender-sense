"""Writing down what every background task did.

A job that silently stops running looks exactly like a job with nothing to do.
The only thing that tells them apart is a record of the runs, which is why this
wraps tasks rather than leaving the accounting to whoever remembers.

The wrapper is deliberately unable to break the task it wraps: if recording the
run fails — Postgres restarting, say — the task still runs and its result is
still returned. An observability layer that can take down the work it observes
is worse than no observability at all.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Coroutine
from datetime import datetime
from typing import Any
from uuid import UUID

from app.core.logging import get_logger
from app.core.observability import job_duration
from app.core.time import utcnow
from app.db.session import session_scope
from app.jobs.runs import JobRun, RunStatus

logger = get_logger(__name__)

#: Results are stored as JSON. Anything larger is a log line, not a run record.
MAX_RESULT_KEYS = 40
MAX_ERROR_LENGTH = 2000


async def _open_run(name: str, started_at: datetime) -> UUID | None:
    try:
        async with session_scope() as session:
            run = JobRun(name=name, status=RunStatus.RUNNING, started_at=started_at)
            session.add(run)
            await session.flush()
            return run.id
    except Exception as exc:  # pragma: no cover - the task must still run
        logger.warning("job_run_not_opened", job=name, error=str(exc)[:200])
        return None


async def _close_run(
    run_id: UUID | None,
    *,
    name: str,
    started_at: datetime,
    status: RunStatus,
    result: Any,
    error: str | None,
) -> None:
    finished = utcnow()
    duration_ms = int((finished - started_at).total_seconds() * 1000)
    payload = result if isinstance(result, dict) else {"result": result}
    if len(payload) > MAX_RESULT_KEYS:
        payload = {"truncated": True, "keys": len(payload)}

    job_duration.labels(job=name, status=status.value).observe(duration_ms / 1000)
    logger.info(
        "job_finished",
        job=name,
        status=status.value,
        duration_ms=duration_ms,
        **({"error": error} if error else {}),
    )
    if run_id is None:
        return
    try:
        async with session_scope() as session:
            run = await session.get(JobRun, run_id)
            if run is None:
                return
            run.status = status
            run.finished_at = finished
            run.duration_ms = duration_ms
            run.result = _jsonable(payload)
            run.error = error[:MAX_ERROR_LENGTH] if error else None
    except Exception as exc:  # pragma: no cover - the result is already returned
        logger.warning("job_run_not_closed", job=name, error=str(exc)[:200])


def _jsonable(payload: dict[str, Any]) -> dict[str, Any]:
    """Coerce values Postgres' JSON encoder would refuse (UUIDs, datetimes)."""
    safe: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, str | int | float | bool | type(None) | list | dict):
            safe[str(key)] = value
        else:
            safe[str(key)] = str(value)
    return safe


def tracked_job[**P, R](
    task: Callable[P, Coroutine[Any, Any, R]],
) -> Callable[P, Coroutine[Any, Any, R]]:
    """Record one ``job_runs`` row per execution of an ARQ task.

    ``functools.wraps`` matters more than it looks: arq registers a task under
    ``func.__name__`` and enqueues it by that string, so a wrapper that renamed
    the function would make every existing ``enqueue_job`` call miss. The
    return type is ``Coroutine`` rather than ``Awaitable`` for a related
    reason: arq's ``WorkerCoroutine`` protocol is declared with ``async def``,
    and a merely awaitable wrapper cannot be passed to ``cron()``.

    A task that returns a dict carrying a truthy ``error`` key is recorded as
    failed. Tasks here degrade rather than raise — a scrape that lost a page
    still returns counts — so treating "returned normally" as success would
    record the failures that matter most as clean runs.
    """
    job_name = task.__name__

    @functools.wraps(task)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        started_at = utcnow()
        run_id = await _open_run(job_name, started_at)
        try:
            result = await task(*args, **kwargs)
        except Exception as exc:
            await _close_run(
                run_id,
                name=job_name,
                started_at=started_at,
                status=RunStatus.FAILED,
                result={},
                error=f"{type(exc).__name__}: {exc}",
            )
            raise

        reported_error = result.get("error") if isinstance(result, dict) else None
        status = RunStatus.FAILED if reported_error else RunStatus.SUCCEEDED
        if isinstance(result, dict) and not reported_error and result.get("failed"):
            status = RunStatus.PARTIAL
        await _close_run(
            run_id,
            name=job_name,
            started_at=started_at,
            status=status,
            result=result,
            error=str(reported_error) if reported_error else None,
        )
        return result

    return wrapper
