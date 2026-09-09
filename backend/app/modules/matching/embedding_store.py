"""Keeping stored vectors in step with the text they came from.

Both sync functions follow the same shape: work out what the current text
should be, compare hashes with what is already stored, embed only the
difference, and delete vectors whose source text no longer exists. That last
step matters more than it looks — a vector for a service the company deleted
would go on scoring against every tender forever, quietly inflating matches
against work they no longer do.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import AIClient, AIError
from app.ai.embeddings import (
    FacetText,
    embed_chunks,
    embed_facets,
    plan_embeddings,
    profile_facets,
    tender_chunks,
)
from app.core.logging import get_logger
from app.modules.profiles.models import (
    CompanyProfile,
    ProfileEmbedding,
    ProfilePastProject,
    ProfileService,
)
from app.modules.tenders.models import Tender, TenderEmbedding

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SyncReport:
    embedded: int = 0
    reused: int = 0
    deleted: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.embedded or self.deleted)


def _facet_identity(facet: FacetText) -> str:
    return f"{facet.facet_kind.value}:{facet.source_id or ''}"


async def sync_profile_embeddings(
    session: AsyncSession, profile: CompanyProfile, *, client: AIClient
) -> SyncReport:
    """Re-embed only the facets whose own text changed."""
    services = list(
        (
            await session.scalars(
                select(ProfileService)
                .where(ProfileService.profile_id == profile.id)
                .order_by(ProfileService.position, ProfileService.created_at)
            )
        ).all()
    )
    projects = list(
        (
            await session.scalars(
                select(ProfilePastProject).where(ProfilePastProject.profile_id == profile.id)
            )
        ).all()
    )

    facets = profile_facets(profile, services=services, projects=projects)
    stored = list(
        (
            await session.scalars(
                select(ProfileEmbedding).where(ProfileEmbedding.profile_id == profile.id)
            )
        ).all()
    )
    by_identity = {
        f"{row.facet_kind.value}:{row.source_id or ''}": row
        for row in stored
        if row.model == client.embedding_model
    }

    plan = plan_embeddings(
        facets, existing={identity: row.text_hash for identity, row in by_identity.items()}
    )

    embedded = 0
    if plan.to_embed:
        vectors = await embed_facets(plan.to_embed, client=client)
        for facet, vector in zip(plan.to_embed, vectors, strict=True):
            identity = _facet_identity(facet)
            row = by_identity.get(identity)
            if row is None:
                session.add(
                    ProfileEmbedding(
                        profile_id=profile.id,
                        facet_kind=facet.facet_kind,
                        source_id=facet.source_id,
                        label=facet.label,
                        model=client.embedding_model,
                        dims=client.dims,
                        embedding=vector,
                        text_hash=facet.hash,
                    )
                )
            else:
                row.embedding = vector
                row.text_hash = facet.hash
                row.label = facet.label
                row.dims = client.dims
            embedded += 1

    # Anything stored that the profile no longer produces — a deleted service,
    # a cleared overview — must go, or it keeps scoring.
    live = {_facet_identity(facet) for facet in facets}
    orphans = [row.id for identity, row in by_identity.items() if identity not in live]
    stale_model = [row.id for row in stored if row.model != client.embedding_model]
    removable = orphans + stale_model
    if removable:
        await session.execute(delete(ProfileEmbedding).where(ProfileEmbedding.id.in_(removable)))

    await session.flush()
    report = SyncReport(embedded=embedded, reused=len(plan.unchanged), deleted=len(removable))
    logger.info(
        "profile_embeddings_synced",
        profile_id=str(profile.id),
        embedded=report.embedded,
        reused=report.reused,
        deleted=report.deleted,
    )
    return report


async def sync_tender_embeddings(
    session: AsyncSession,
    tender: Tender,
    *,
    attributes: dict[str, object] | None,
    client: AIClient,
) -> SyncReport:
    """Embed the notice, and its extracted scope once extraction has run."""
    chunks = tender_chunks(tender, attributes=attributes)
    stored = list(
        (
            await session.scalars(
                select(TenderEmbedding).where(TenderEmbedding.tender_id == tender.id)
            )
        ).all()
    )
    by_kind = {row.chunk_kind.value: row for row in stored if row.model == client.embedding_model}

    plan = plan_embeddings(chunks, existing={kind: row.text_hash for kind, row in by_kind.items()})

    embedded = 0
    if plan.to_embed:
        vectors = await embed_chunks(plan.to_embed, client=client)
        for chunk, vector in zip(plan.to_embed, vectors, strict=True):
            row = by_kind.get(chunk.chunk_kind.value)
            if row is None:
                session.add(
                    TenderEmbedding(
                        tender_id=tender.id,
                        chunk_kind=chunk.chunk_kind,
                        chunk_index=0,
                        model=client.embedding_model,
                        dims=client.dims,
                        embedding=vector,
                        text_hash=chunk.hash,
                    )
                )
            else:
                row.embedding = vector
                row.text_hash = chunk.hash
                row.dims = client.dims
            embedded += 1

    stale_model = [row.id for row in stored if row.model != client.embedding_model]
    if stale_model:
        await session.execute(delete(TenderEmbedding).where(TenderEmbedding.id.in_(stale_model)))

    await session.flush()
    return SyncReport(embedded=embedded, reused=len(plan.unchanged), deleted=len(stale_model))


async def load_profile_vectors(
    session: AsyncSession, profile_id: UUID, *, model: str
) -> list[tuple[str, str, list[float]]]:
    """`(facet_kind, label, vector)` for scoring."""
    rows = await session.scalars(
        select(ProfileEmbedding).where(
            ProfileEmbedding.profile_id == profile_id, ProfileEmbedding.model == model
        )
    )
    return [(row.facet_kind.value, row.label, list(row.embedding)) for row in rows.all()]


async def load_tender_vectors(
    session: AsyncSession, tender_id: UUID, *, model: str
) -> list[tuple[str, list[float]]]:
    """`(chunk_kind, vector)` for scoring."""
    rows = await session.scalars(
        select(TenderEmbedding).where(
            TenderEmbedding.tender_id == tender_id, TenderEmbedding.model == model
        )
    )
    return [(row.chunk_kind.value, list(row.embedding)) for row in rows.all()]


async def safe_sync_tender_embeddings(
    session: AsyncSession,
    tender: Tender,
    *,
    attributes: dict[str, object] | None,
    client: AIClient,
) -> SyncReport | None:
    """Embed a tender, returning ``None`` rather than raising on failure.

    An embedding outage should stall one tender, not the whole ingest run.
    """
    try:
        return await sync_tender_embeddings(session, tender, attributes=attributes, client=client)
    except AIError as exc:
        logger.warning("tender_embedding_failed", tender_id=str(tender.id), error=str(exc))
        return None
