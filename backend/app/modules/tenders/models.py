"""The shared tender pool.

Tenders are not tenant data: one notice scraped from a portal is scored against
every organization's profile. Only matches, decisions and notifications are
per-tenant. Keeping the pool shared means a portal is scraped once no matter how
many customers care about it.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Computed,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

EMBEDDING_DIMS = settings.embedding_dims


def _pg_enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    return Enum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda e: [member.value for member in e],
    )


class SourceHealth(enum.StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    DOWN = "down"


class TenderStatus(enum.StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    AWARDED = "awarded"
    UNKNOWN = "unknown"


class ProcurementCategory(enum.StrEnum):
    GOODS = "goods"
    WORKS = "works"
    SERVICES = "services"
    CONSULTING = "consulting"
    UNKNOWN = "unknown"


class DocumentKind(enum.StrEnum):
    LISTING_ROW = "listing_row"
    """The raw row from a search results page."""
    DETAIL_HTML = "detail_html"
    API_JSON = "api_json"
    ATTACHMENT = "attachment"


class ExtractionStatus(enum.StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class EmbeddingChunk(enum.StrEnum):
    TITLE_SUMMARY = "title_summary"
    """Title, buyer and description — available as soon as a notice is scraped."""
    SCOPE_REQUIREMENTS = "scope_requirements"
    """Scope and qualifications distilled by the extraction step."""


class TenderSource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A portal we ingest from, plus its scraping configuration and health."""

    __tablename__ = "tender_sources"

    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    #: Selects the adapter implementation; changing it swaps ingestion strategy
    #: (for example from the HTTP client to the Playwright fallback).
    adapter_key: Mapped[str] = mapped_column(String(50))
    base_url: Mapped[str] = mapped_column(String(500))
    country: Mapped[str | None] = mapped_column(String(2), default=None)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    schedule_cron: Mapped[str | None] = mapped_column(String(100), default=None)
    #: Selectors, page limits and endpoint parameters, so a portal change is a
    #: data fix rather than a deployment.
    config: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    cursor: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    last_run_at: Mapped[datetime | None] = mapped_column(default=None)
    last_success_at: Mapped[datetime | None] = mapped_column(default=None)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    health: Mapped[SourceHealth] = mapped_column(
        _pg_enum(SourceHealth, "source_health"),
        default=SourceHealth.OK,
        server_default=SourceHealth.OK.value,
    )


class Tender(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tenders"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id"),
        Index("ix_tenders_deadline_at", "deadline_at"),
        Index("ix_tenders_published_at", text("published_at DESC")),
        Index("ix_tenders_status_deadline_at", "status", "deadline_at"),
        Index("ix_tenders_country", "country"),
        Index("ix_tenders_search_tsv", "search_tsv", postgresql_using="gin"),
        Index(
            "ix_tenders_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
    )

    source_id: Mapped[UUID] = mapped_column(ForeignKey("tender_sources.id", ondelete="CASCADE"))
    #: The portal's own identifier; with source_id it makes ingestion idempotent.
    external_id: Mapped[str] = mapped_column(String(200))
    canonical_url: Mapped[str] = mapped_column(String(1000))
    title: Mapped[str] = mapped_column(String(1000))
    summary: Mapped[str | None] = mapped_column(Text, default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    procuring_entity: Mapped[str | None] = mapped_column(String(500), default=None)
    country: Mapped[str | None] = mapped_column(String(2), default=None)
    procurement_method: Mapped[str | None] = mapped_column(String(100), default=None)
    procurement_category: Mapped[ProcurementCategory] = mapped_column(
        _pg_enum(ProcurementCategory, "procurement_category"),
        default=ProcurementCategory.UNKNOWN,
        server_default=ProcurementCategory.UNKNOWN.value,
    )
    published_at: Mapped[datetime | None] = mapped_column(default=None)
    deadline_at: Mapped[datetime | None] = mapped_column(default=None)
    currency: Mapped[str | None] = mapped_column(String(3), default=None)
    estimated_value: Mapped[float | None] = mapped_column(Numeric(18, 2), default=None)
    status: Mapped[TenderStatus] = mapped_column(
        _pg_enum(TenderStatus, "tender_status"),
        default=TenderStatus.OPEN,
        server_default=TenderStatus.OPEN.value,
    )
    language: Mapped[str | None] = mapped_column(String(10), default=None)
    #: Digest of the normalised fields. A change means the portal edited the
    #: notice, which triggers re-extraction and re-matching.
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    portal_metadata: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    first_seen_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    last_seen_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    search_tsv: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('simple', "
            "coalesce(title, '') || ' ' || "
            "coalesce(summary, '') || ' ' || "
            "coalesce(procuring_entity, ''))",
            persisted=True,
        ),
        nullable=True,
    )


class TenderDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Raw bytes exactly as fetched, so normalisation can be re-run offline
    after a selector fix without hitting the portal again."""

    __tablename__ = "tender_documents"
    __table_args__ = (
        UniqueConstraint("tender_id", "sha256"),
        Index("ix_tender_documents_tender_id", "tender_id"),
    )

    tender_id: Mapped[UUID] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"))
    kind: Mapped[DocumentKind] = mapped_column(_pg_enum(DocumentKind, "document_kind"))
    url: Mapped[str | None] = mapped_column(String(1000), default=None)
    #: Path in the blob store; bodies are kept out of Postgres.
    storage_key: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str | None] = mapped_column(String(100), default=None)
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    fetched_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    extracted_text: Mapped[str | None] = mapped_column(Text, default=None)


class TenderExtraction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Structured requirements read out of a notice by the language model.

    Versioned and never overwritten: a match records which extraction it used,
    so a scoring decision stays explainable after the prompt changes.
    """

    __tablename__ = "tender_extractions"
    __table_args__ = (
        UniqueConstraint("tender_id", "version"),
        Index(
            "uq_tender_extractions_current",
            "tender_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
        Index("ix_tender_extractions_attributes", "attributes", postgresql_using="gin"),
    )

    tender_id: Mapped[UUID] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(50))
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    attributes: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    #: Per-field 0..1 confidence. Anything low is treated as unknown by the rule
    #: engine, which surfaces as "needs verification" rather than a false reject.
    field_confidence: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    #: Quote from the notice supporting each field, so a user can check it.
    evidence: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    input_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[ExtractionStatus] = mapped_column(
        _pg_enum(ExtractionStatus, "extraction_status"),
        default=ExtractionStatus.SUCCEEDED,
        server_default=ExtractionStatus.SUCCEEDED.value,
    )
    error: Mapped[str | None] = mapped_column(Text, default=None)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    tokens_out: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class TenderEmbedding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Vector for one chunk of a tender.

    ``model`` and ``dims`` are stored per row so switching embedding models is a
    background re-embed alongside the old vectors, not a schema migration.
    """

    __tablename__ = "tender_embeddings"
    __table_args__ = (
        UniqueConstraint("tender_id", "chunk_kind", "chunk_index", "model"),
        Index(
            "ix_tender_embeddings_vector",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    tender_id: Mapped[UUID] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"))
    chunk_kind: Mapped[EmbeddingChunk] = mapped_column(_pg_enum(EmbeddingChunk, "embedding_chunk"))
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    model: Mapped[str] = mapped_column(String(100))
    dims: Mapped[int] = mapped_column(Integer, default=EMBEDDING_DIMS)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMS))
    text_hash: Mapped[str] = mapped_column(String(64))
