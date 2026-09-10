"""Replaying stored payloads through a fixed parser.

The workflow this exists for: a portal changes its markup overnight, notices
start arriving with empty descriptions or missing deadlines, someone fixes the
selectors, and then every notice already ingested with the broken parser has to
be corrected — without asking the portal for any of it again.

Two jobs, one for each half of that:

``reparse_source``   re-runs ``normalize`` over the bytes already stored.
``reprocess_tender`` re-runs extraction, embedding and matching for one notice.

Reparsing feeds the second automatically: a notice whose parse actually changed
is a changed notice, and changed notices go back through the pipeline.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.core.logging import get_logger
from app.db.session import session_scope
from app.ingestion.reprocess import NoStoredDocumentsError, reparse_tender
from app.jobs.tasks.matching import enqueue_processing, process_tender
from app.jobs.tracking import tracked_job
from app.modules.tenders.models import Tender, TenderSource

logger = get_logger(__name__)

#: A cap so an operator cannot accidentally replay a whole portal in one job.
DEFAULT_LIMIT = 500


@tracked_job
async def reparse_source(
    ctx: dict[str, Any],
    source_id: str,
    limit: int | None = None,
    reprocess_changed: bool = True,
) -> dict[str, Any]:
    """Re-parse every stored notice for one source.

    Each notice is its own transaction, because the point of a replay is
    usually that *some* notices parse differently now — and one that still
    fails must not roll back the ones that were repaired.
    """
    cap = limit or DEFAULT_LIMIT
    result: dict[str, Any] = {
        "source_id": source_id,
        "examined": 0,
        "changed": 0,
        "unchanged": 0,
        "failed": 0,
        "no_payload": 0,
    }

    async with session_scope() as session:
        source = await session.get(TenderSource, UUID(source_id))
        if source is None:
            return result | {"error": "source_not_found"}
        source_code = source.code
        tender_ids = list(
            (
                await session.scalars(
                    select(Tender.id)
                    .where(Tender.source_id == source.id)
                    .order_by(Tender.first_seen_at.desc())
                    .limit(cap)
                )
            ).all()
        )

    changed_ids: list[str] = []
    for tender_id in tender_ids:
        result["examined"] += 1
        try:
            async with session_scope() as session:
                tender = await session.get(Tender, tender_id)
                fresh_source = await session.get(TenderSource, UUID(source_id))
                if tender is None or fresh_source is None:
                    continue
                outcome = await reparse_tender(session, tender=tender, source=fresh_source)
            if outcome.changed:
                result["changed"] += 1
                changed_ids.append(str(tender_id))
            else:
                result["unchanged"] += 1
        except NoStoredDocumentsError:
            result["no_payload"] += 1
        except Exception as exc:
            result["failed"] += 1
            logger.warning("reparse_failed", tender_id=str(tender_id), error=str(exc)[:200])

    if reprocess_changed:
        for changed_id in changed_ids:
            await enqueue_processing(changed_id)
    result["queued"] = len(changed_ids) if reprocess_changed else 0

    logger.info("source_reparsed", source=source_code, **result)
    return result


@tracked_job
async def reprocess_tender(
    ctx: dict[str, Any], tender_id: str, reparse: bool = False
) -> dict[str, Any]:
    """Send one notice back through the pipeline.

    ``reparse`` first re-runs the adapter's parser over stored bytes, which is
    what fixes a notice ingested by a broken parser. Without it the stored text
    is taken as correct and only the AI and matching steps re-run — which is
    what a prompt change or a threshold re-fit needs.
    """
    result: dict[str, Any] = {"tender_id": tender_id, "reparsed": False}

    if reparse:
        try:
            async with session_scope() as session:
                tender = await session.get(Tender, UUID(tender_id))
                if tender is None:
                    return result | {"error": "tender_not_found"}
                source = await session.get(TenderSource, tender.source_id)
                if source is None:
                    return result | {"error": "source_not_found"}
                outcome = await reparse_tender(session, tender=tender, source=source)
            result["reparsed"] = True
            result["parse_outcome"] = outcome.outcome
        except NoStoredDocumentsError as exc:
            # Not an error worth failing the job over: the AI and matching
            # steps below can still run on the text already held.
            result["parse_outcome"] = "no_payload"
            logger.info("reparse_skipped", tender_id=tender_id, reason=str(exc))
        except Exception as exc:
            return result | {"error": str(exc)[:200]}

    result["pipeline"] = await process_tender(ctx, tender_id)
    return result
