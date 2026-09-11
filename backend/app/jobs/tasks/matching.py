"""The pipeline: extract, embed, match.

``process_tender`` runs once per new or amended notice and fans out to every
tenant. ``rematch_org`` runs the other way round — one tenant against the open
pool — and is what a profile edit triggers.

Both are written to degrade rather than fail. Extraction failing leaves a notice
with no attributes, which still embeds and still matches; one organization
failing does not abandon the rest. A tender that silently disappears from a
customer's feed because of a transient error is worse than one scored on less
information.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import get_ai_client
from app.ai.base import AIClient
from app.ai.extraction import extract_attributes
from app.ai.schemas import EXTRACTION_PROMPT_VERSION, EXTRACTION_SCHEMA_VERSION
from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.session import session_scope
from app.jobs.tracking import tracked_job
from app.modules.matching.embedding_store import (
    safe_sync_tender_embeddings,
    sync_profile_embeddings,
)
from app.modules.matching.service import (
    active_thresholds,
    match_tender_for_org,
    orgs_with_profiles,
)
from app.modules.orgs.models import Organization
from app.modules.profiles.models import CompanyProfile
from app.modules.tenders.models import (
    ExtractionStatus,
    Tender,
    TenderEmbedding,
    TenderExtraction,
    TenderStatus,
)

logger = get_logger(__name__)

CLOSED_STATUSES = (TenderStatus.CLOSED, TenderStatus.CANCELLED, TenderStatus.AWARDED)


def _client(ctx: dict[str, Any]) -> AIClient:
    """``ctx["ai_client"]`` lets a test inject the fake without patching."""
    client: AIClient | None = ctx.get("ai_client")
    return client or get_ai_client()


async def _run_extraction(
    session: AsyncSession, tender: Tender, *, client: AIClient
) -> TenderExtraction | None:
    """Extract attributes and store them as a new current version.

    Existing versions are kept and merely un-flagged: a match records which
    extraction it used, so overwriting one would strand every score that cited
    it. A failed attempt is stored too, so a persistently unparseable notice is
    visible rather than looking like it was never tried.
    """
    outcome = await extract_attributes(tender, client=client)

    previous = list(
        (
            await session.scalars(
                select(TenderExtraction).where(TenderExtraction.tender_id == tender.id)
            )
        ).all()
    )
    current = next((row for row in previous if row.is_current), None)
    if current is not None and current.input_hash == outcome.input_hash and outcome.succeeded:
        return current

    for row in previous:
        row.is_current = False

    attributes = outcome.attributes
    extraction = TenderExtraction(
        tender_id=tender.id,
        version=max((row.version for row in previous), default=0) + 1,
        model=outcome.usage.model,
        prompt_version=EXTRACTION_PROMPT_VERSION,
        schema_version=EXTRACTION_SCHEMA_VERSION,
        attributes=attributes.model_dump(mode="json") if attributes else {},
        field_confidence=attributes.confidence_map() if attributes else {},
        evidence=attributes.evidence_map() if attributes else {},
        input_hash=outcome.input_hash,
        status=ExtractionStatus.SUCCEEDED if outcome.succeeded else ExtractionStatus.FAILED,
        error=outcome.error,
        tokens_in=outcome.usage.tokens_in,
        tokens_out=outcome.usage.tokens_out,
        latency_ms=outcome.usage.latency_ms,
        is_current=True,
    )
    session.add(extraction)
    await session.flush()
    return extraction


async def enqueue_processing(tender_id: str, *, only_org_id: str | None = None) -> str | None:
    """Queue extraction, embedding and matching for one notice.

    Deduplicated by tender, so a notice seen twice in one scrape — or replayed
    while a previous pass is still queued — costs one pipeline run, not two.

    A scoped run carries the organization in its job id. A manual sync and the
    tenant-wide sweep want different work out of the same notice, and sharing
    one id would let whichever arrived first silently cancel the other — the
    sweep being dropped is the expensive direction, because the notice would
    then never reach the other tenants.
    """
    from app.jobs.queue import get_queue

    job_id = f"process:{tender_id}" if only_org_id is None else f"process:{tender_id}:{only_org_id}"
    try:
        queue = await get_queue()
        job = await queue.enqueue_job("process_tender", tender_id, only_org_id, _job_id=job_id)
    except Exception as exc:  # pragma: no cover - Redis down must not lose the row
        logger.warning("process_enqueue_failed", tender_id=tender_id, error=str(exc))
        return None
    return job.job_id if job else None


async def process_tender(
    ctx: dict[str, Any], tender_id: str, only_org_id: str | None = None
) -> dict[str, Any]:
    """Extract, embed and match one notice.

    Across every tenant by default. ``only_org_id`` narrows the matching to
    one organization — what a hand-pressed sync asks for, so the person who
    pressed it gets their grades without making a portal's worth of notices
    re-score the whole deployment on demand.

    A scoped pass deliberately leaves ``analysed_at`` null. That is the flag
    the six-hourly sweep looks for: without it a notice stored by one
    organization's sync would be neither new nor amended on the next scheduled
    pass, and would stay ungraded for every other tenant forever.
    """
    client = _client(ctx)
    result: dict[str, Any] = {
        "tender_id": tender_id,
        "matched": 0,
        "skipped": 0,
        "not_scorable": 0,
        "failed": 0,
        "scoped_to_org": only_org_id,
    }

    async with session_scope() as session:
        tender = await session.get(Tender, UUID(tender_id))
        if tender is None:
            logger.warning("process_tender_missing", tender_id=tender_id)
            return result | {"error": "not_found"}

        extraction = await _run_extraction(session, tender, client=client)
        attributes = extraction.attributes if extraction else None
        result["extraction"] = extraction.status.value if extraction else "skipped"

        await safe_sync_tender_embeddings(session, tender, attributes=attributes, client=client)
        await session.commit()

        thresholds = await active_thresholds(session)
        tenants = await orgs_with_profiles(session, only_org_id=only_org_id)

    for org, profile in tenants:
        try:
            async with session_scope() as session:
                # Re-attached per tenant so one failure cannot roll back another's
                # match — each organization's verdict commits on its own.
                fresh_tender = await session.get(Tender, UUID(tender_id))
                fresh_org = await session.get(Organization, org.id)
                fresh_profile = await session.get(CompanyProfile, profile.id)
                if not (fresh_tender and fresh_org and fresh_profile):
                    continue

                # A profile edited since its last re-match — or never embedded
                # at all, which is every organization's first tender — has no
                # vectors to score against. Embedding here is cheap when
                # nothing changed, and skipping it would leave the tenant's
                # whole feed unscored until their debounced re-match fires.
                await sync_profile_embeddings(session, fresh_profile, client=client)

                outcome = await match_tender_for_org(
                    session,
                    tender=fresh_tender,
                    org=fresh_org,
                    profile=fresh_profile,
                    embedding_model=client.embedding_model,
                    thresholds=thresholds,
                    reason="tender_processed",
                )
            if outcome.not_scorable:
                result["not_scorable"] += 1
            elif outcome.skipped:
                result["skipped"] += 1
            else:
                result["matched"] += 1
        except Exception as exc:
            result["failed"] += 1
            logger.warning("match_failed", org_id=str(org.id), tender_id=tender_id, error=str(exc))

    # Explanations run last and only upgrade prose, so a failure here cannot
    # cost anyone their match.
    if result["matched"]:
        from app.jobs.tasks.explanations import generate_explanations

        result["explanations"] = await generate_explanations(ctx, tender_id)

        # Alerts come after explanations so the email can quote the prose
        # rather than a bare grade — and after matching, so an alert is never
        # sent for a verdict that was then rolled back.
        from app.jobs.tasks.notifications import notify_instant

        result["alerts"] = await notify_instant(ctx, tender_id)

    # Only a tenant-wide pass may claim the notice is analysed. A scoped one
    # deliberately leaves the mark off so the sweep still comes for it.
    if only_org_id is None:
        async with session_scope() as session:
            fresh = await session.get(Tender, UUID(tender_id))
            if fresh is not None:
                fresh.analysed_at = utcnow()

    logger.info(
        "tender_processed",
        **{k: v for k, v in result.items() if k not in ("explanations", "alerts")},
    )
    return result


#: A sweep that enqueued the whole backlog at once would put thousands of
#: extractions on the queue in one tick and spend a day's model budget before
#: lunch. It catches up over successive passes instead.
SWEEP_BATCH = 200


async def sweep_unanalysed_tenders(ctx: dict[str, Any]) -> dict[str, Any]:
    """Match, for every tenant, the notices only one tenant has seen.

    A manual sync scores for the organization that pressed it and no one else,
    which is what keeps a hand-pressed button from re-scoring the deployment.
    The cost of that is a notice sitting in the shared pool that is invisible
    to everybody else: on the next scheduled pass it is neither new nor
    amended, so nothing would queue it and it would stay ungraded forever.

    This is the other half of that bargain. Anything still carrying a null
    ``analysed_at`` gets a tenant-wide pass, oldest first so the backlog drains
    in the order it arrived.
    """
    async with session_scope() as session:
        rows = (
            await session.scalars(
                select(Tender.id)
                .where(Tender.analysed_at.is_(None))
                .order_by(Tender.first_seen_at)
                .limit(SWEEP_BATCH)
            )
        ).all()

    queued = 0
    for tender_id in rows:
        if await enqueue_processing(str(tender_id)):
            queued += 1

    result = {"found": len(rows), "queued": queued}
    logger.info("sweep_unanalysed", **result)
    return result


async def rematch_org(
    ctx: dict[str, Any], org_id: str, reason: str = "profile_changed", force: bool = False
) -> dict[str, Any]:
    """Re-score one tenant against the open pool.

    Only open tenders: re-scoring a notice that already closed cannot change
    what anyone does about it, and the pool grows without bound.

    ``force`` ignores the fingerprint guard. Normally a match whose inputs are
    unchanged is left alone, which is what keeps a daily scrape cheap — but it
    also makes a *wrong* match sticky, because a verdict written by a bug or a
    half-finished deploy has the same fingerprint as a correct one. This is the
    lever that repairs those; nothing else will.
    """
    client = _client(ctx)
    result: dict[str, Any] = {
        "org_id": org_id,
        "matched": 0,
        "skipped": 0,
        "not_scorable": 0,
        "failed": 0,
    }

    async with session_scope() as session:
        org = await session.get(Organization, UUID(org_id))
        profile = await session.scalar(
            select(CompanyProfile).where(CompanyProfile.org_id == UUID(org_id))
        )
        if org is None or profile is None:
            logger.info("rematch_org_skipped", org_id=org_id, reason="no_profile")
            return result | {"error": "no_profile"}

        await sync_profile_embeddings(session, profile, client=client)
        await session.commit()

        now = utcnow()
        # Only tenders that already have vectors for this model. One without
        # them has not been through `process_tender` yet, and scoring it would
        # store a 0.0-similarity C-grade match — a junk row in the customer's
        # feed that says "we looked and found nothing" when we never looked.
        # It gets matched properly when `process_tender` reaches it.
        tender_ids = list(
            (
                await session.scalars(
                    select(Tender.id)
                    .join(TenderEmbedding, TenderEmbedding.tender_id == Tender.id)
                    .where(
                        Tender.status.not_in(CLOSED_STATUSES),
                        (Tender.deadline_at.is_(None)) | (Tender.deadline_at > now),
                        TenderEmbedding.model == client.embedding_model,
                    )
                    .distinct()
                )
            ).all()
        )
        thresholds = await active_thresholds(session)

    for tender_id in tender_ids:
        try:
            async with session_scope() as session:
                tender = await session.get(Tender, tender_id)
                fresh_org = await session.get(Organization, UUID(org_id))
                fresh_profile = await session.get(CompanyProfile, profile.id)
                if not (tender and fresh_org and fresh_profile):
                    continue

                outcome = await match_tender_for_org(
                    session,
                    tender=tender,
                    org=fresh_org,
                    profile=fresh_profile,
                    embedding_model=client.embedding_model,
                    thresholds=thresholds,
                    reason=reason,
                    force=force,
                )
            if outcome.not_scorable:
                result["not_scorable"] += 1
            elif outcome.skipped:
                result["skipped"] += 1
            else:
                result["matched"] += 1
        except Exception as exc:
            result["failed"] += 1
            logger.warning(
                "rematch_failed", org_id=org_id, tender_id=str(tender_id), error=str(exc)
            )

    logger.info("org_rematched", **result)
    return result


@tracked_job
async def process_unprocessed_tenders(ctx: dict[str, Any], limit: int = 2000) -> dict[str, Any]:
    """Queue the pipeline for notices that are in the pool but never ran through it.

    The repair for a gap that should no longer open: a scrape used to queue its
    work only after the whole pass finished, so a run cancelled by the worker's
    job timeout left everything it had committed sitting in the pool with
    nothing scheduled to extract, embed or match it. On one deployment that was
    1,122 notices — a full tender list, no matches, an empty dashboard, and no
    failed job anywhere to explain it.

    Ingestion queues per notice now, so this should find nothing. It stays
    because "should find nothing" is exactly the claim worth having a control
    for, and because a pool that fell behind for any other reason — Redis down
    while a scrape ran, a queue flushed by hand — is repaired the same way.

    Idempotent: the pipeline is deduplicated per tender, so queuing one that is
    already queued costs nothing.
    """
    from app.modules.tenders.models import Tender, TenderExtraction

    async with session_scope() as session:
        rows = await session.scalars(
            select(Tender.id)
            .outerjoin(TenderExtraction, TenderExtraction.tender_id == Tender.id)
            .where(TenderExtraction.id.is_(None))
            .order_by(Tender.first_seen_at.desc())
            .limit(limit)
        )
        tender_ids = [str(tender_id) for tender_id in rows.all()]

    queued = 0
    for tender_id in tender_ids:
        if await enqueue_processing(tender_id):
            queued += 1

    logger.info("backfill_processing", found=len(tender_ids), queued=queued)
    return {"found": len(tender_ids), "queued": queued}
