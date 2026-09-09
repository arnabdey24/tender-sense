"""Building the texts that get embedded, and deciding what needs re-embedding.

Two rules shape this module:

* **Profiles are embedded per facet, tenders per chunk.** A facet is one thing
  the company does; a chunk is one view of the notice. Scoring compares every
  facet against every chunk, so both sides stay small and specific rather than
  being flattened into one averaged vector that means nothing in particular.
* **Nothing is re-embedded unless its own text changed.** Each vector stores the
  hash of the text that produced it, so editing one service line costs one
  embedding call, not a whole profile.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import UUID

from app.ai.base import AIClient
from app.modules.profiles.models import (
    CompanyProfile,
    ProfileFacet,
    ProfilePastProject,
    ProfileService,
)
from app.modules.tenders.models import EmbeddingChunk, Tender

#: Keeps one enormous notice from dominating a batch and from being truncated
#: mid-sentence by the model. Generous enough that nothing real is lost.
MAX_EMBED_CHARS = 8000


def text_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode()).hexdigest()


def _clip(text: str) -> str:
    return text.strip()[:MAX_EMBED_CHARS]


def _join(*parts: str | None) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip())


@dataclass(frozen=True, slots=True)
class FacetText:
    """One embeddable piece of a profile."""

    facet_kind: ProfileFacet
    #: The row this came from; null for facets derived from the profile itself.
    source_id: UUID | None
    label: str
    text: str

    @property
    def hash(self) -> str:
        return text_hash(self.text)


@dataclass(frozen=True, slots=True)
class ChunkText:
    """One embeddable view of a tender."""

    chunk_kind: EmbeddingChunk
    text: str
    title: str

    @property
    def hash(self) -> str:
        return text_hash(self.text)


def profile_facets(
    profile: CompanyProfile,
    *,
    services: list[ProfileService],
    projects: list[ProfilePastProject],
) -> list[FacetText]:
    """Every facet worth embedding, skipping ones with nothing to say.

    An empty facet would still produce a vector, and that vector would still
    score against every tender — usually badly, dragging the mean down for no
    reason. Better to have no facet than a meaningless one.
    """
    facets: list[FacetText] = []

    overview = _join(profile.overview)
    if overview:
        facets.append(
            FacetText(
                facet_kind=ProfileFacet.OVERVIEW,
                source_id=None,
                label="Company overview",
                text=_clip(overview),
            )
        )

    # Sectors and geographies are short labels, not prose. Embedded together as
    # one facet so "IT work in Bangladesh" is a single comparable statement.
    sector_geo = _join(
        ", ".join(profile.sectors) if profile.sectors else None,
        ("operating in " + ", ".join(profile.geographies)) if profile.geographies else None,
        ", ".join(profile.keywords) if profile.keywords else None,
    )
    if sector_geo:
        facets.append(
            FacetText(
                facet_kind=ProfileFacet.SECTOR_GEO,
                source_id=None,
                label="Sectors and geographies",
                text=_clip(sector_geo),
            )
        )

    for service in services:
        text = _join(service.name, service.description, service.sector)
        if text:
            facets.append(
                FacetText(
                    facet_kind=ProfileFacet.SERVICE,
                    source_id=service.id,
                    label=service.name,
                    text=_clip(text),
                )
            )

    for project in projects:
        text = _join(
            project.title, project.description, project.client, project.sector, project.country
        )
        if text:
            facets.append(
                FacetText(
                    facet_kind=ProfileFacet.PAST_PROJECT,
                    source_id=project.id,
                    label=project.title,
                    text=_clip(text),
                )
            )

    return facets


def tender_chunks(
    tender: Tender, *, attributes: dict[str, object] | None = None
) -> list[ChunkText]:
    """The two views of a notice worth comparing against.

    Chunk A is available the moment a notice is scraped. Chunk B needs the
    extraction, so a tender is matchable before extraction has run and simply
    gets sharper once it has.
    """
    chunks: list[ChunkText] = []

    headline = _join(
        tender.title,
        tender.procuring_entity,
        tender.procurement_category.value,
        tender.procurement_method,
        tender.summary,
        tender.description,
    )
    if headline:
        chunks.append(
            ChunkText(
                chunk_kind=EmbeddingChunk.TITLE_SUMMARY,
                text=_clip(headline),
                title=tender.title,
            )
        )

    if attributes:
        scope = _join(
            _as_text(attributes.get("scope_summary")),
            _as_text(attributes.get("key_deliverables")),
            _as_text(attributes.get("required_qualifications_text")),
            _as_text(attributes.get("sectors")),
        )
        if scope:
            chunks.append(
                ChunkText(
                    chunk_kind=EmbeddingChunk.SCOPE_REQUIREMENTS,
                    text=_clip(scope),
                    title=tender.title,
                )
            )

    return chunks


def _as_text(value: object) -> str | None:
    """Flatten whatever the extraction put in a field into embeddable text."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if item)
    return str(value)


@dataclass(frozen=True, slots=True)
class EmbeddingPlan[T]:
    """What actually has to be sent to the model, and what can be reused."""

    to_embed: list[T]
    unchanged: list[T]

    @property
    def call_count(self) -> int:
        return len(self.to_embed)


def plan_embeddings[T](
    items: list[T], *, existing: dict[str, str], key: object = None
) -> EmbeddingPlan[T]:
    """Split items into "changed, must embed" and "unchanged, reuse".

    ``existing`` maps a stable identity to the text hash already stored for it.
    Anything whose hash still matches is skipped, which is what keeps a profile
    edit from re-embedding every service the company offers.
    """
    identify = key if callable(key) else _default_identity
    to_embed: list[T] = []
    unchanged: list[T] = []
    for item in items:
        identity, item_hash = identify(item)
        if existing.get(identity) == item_hash:
            unchanged.append(item)
        else:
            to_embed.append(item)
    return EmbeddingPlan(to_embed=to_embed, unchanged=unchanged)


def _default_identity(item: object) -> tuple[str, str]:
    """Identity and hash for a :class:`FacetText` or :class:`ChunkText`."""
    if isinstance(item, FacetText):
        return f"{item.facet_kind.value}:{item.source_id or ''}", item.hash
    if isinstance(item, ChunkText):
        return item.chunk_kind.value, item.hash
    raise TypeError(f"No identity rule for {type(item).__name__}; pass `key=`.")


async def embed_facets(facets: list[FacetText], *, client: AIClient) -> list[list[float]]:
    """Embed profile facets on the *query* side of the comparison.

    A profile is what we are searching *with*; a tender is what we are searching
    *over*. Using the query prefix for one and the document prefix for the other
    is the asymmetry the embedding model expects, and getting it backwards
    quietly costs accuracy without ever failing.
    """
    if not facets:
        return []
    result = await client.embed_queries([facet.text for facet in facets])
    return result.vectors


async def embed_chunks(chunks: list[ChunkText], *, client: AIClient) -> list[list[float]]:
    """Embed tender chunks on the document side."""
    if not chunks:
        return []
    result = await client.embed_documents(
        [chunk.text for chunk in chunks], titles=[chunk.title for chunk in chunks]
    )
    return result.vectors
