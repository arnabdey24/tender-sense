"""tender pool

Revision ID: 0003_tender_pool
Revises: 0002_identity
Create Date: 2026-09-09 18:55:56.589104
"""

from __future__ import annotations

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_tender_pool"
down_revision: str | None = "0002_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tender_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("adapter_key", sa.String(length=50), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("schedule_cron", sa.String(length=100), nullable=True),
        sa.Column(
            "config", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column(
            "cursor", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "health",
            sa.Enum("ok", "degraded", "down", name="source_health"),
            server_default="ok",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tender_sources")),
    )
    op.create_index(op.f("ix_tender_sources_code"), "tender_sources", ["code"], unique=True)
    op.create_table(
        "tenders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(length=200), nullable=False),
        sa.Column("canonical_url", sa.String(length=1000), nullable=False),
        sa.Column("title", sa.String(length=1000), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("procuring_entity", sa.String(length=500), nullable=True),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.Column("procurement_method", sa.String(length=100), nullable=True),
        sa.Column(
            "procurement_category",
            sa.Enum(
                "goods", "works", "services", "consulting", "unknown", name="procurement_category"
            ),
            server_default="unknown",
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("estimated_value", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column(
            "status",
            sa.Enum("open", "closed", "cancelled", "awarded", "unknown", name="tender_status"),
            server_default="open",
            nullable=False,
        ),
        sa.Column("language", sa.String(length=10), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "portal_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "search_tsv",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('simple', "
                "coalesce(title, '') || ' ' || "
                "coalesce(summary, '') || ' ' || "
                "coalesce(procuring_entity, ''))",
                persisted=True,
            ),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["tender_sources.id"],
            name=op.f("fk_tenders_source_id_tender_sources"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenders")),
        sa.UniqueConstraint(
            "source_id", "external_id", name=op.f("uq_tenders_source_id_external_id")
        ),
    )
    op.create_index(op.f("ix_tenders_content_hash"), "tenders", ["content_hash"], unique=False)
    op.create_index("ix_tenders_country", "tenders", ["country"], unique=False)
    op.create_index("ix_tenders_deadline_at", "tenders", ["deadline_at"], unique=False)
    op.create_index(
        "ix_tenders_published_at", "tenders", [sa.literal_column("published_at DESC")], unique=False
    )
    op.create_index(
        "ix_tenders_search_tsv", "tenders", ["search_tsv"], unique=False, postgresql_using="gin"
    )
    op.create_index(
        "ix_tenders_status_deadline_at", "tenders", ["status", "deadline_at"], unique=False
    )
    op.create_index(
        "ix_tenders_title_trgm",
        "tenders",
        ["title"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
    )
    op.create_table(
        "tender_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tender_id", sa.Uuid(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("listing_row", "detail_html", "api_json", "attachment", name="document_kind"),
            nullable=False,
        ),
        sa.Column("url", sa.String(length=1000), nullable=True),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tender_id"],
            ["tenders.id"],
            name=op.f("fk_tender_documents_tender_id_tenders"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tender_documents")),
        sa.UniqueConstraint(
            "tender_id", "sha256", name=op.f("uq_tender_documents_tender_id_sha256")
        ),
    )
    op.create_index(
        "ix_tender_documents_tender_id", "tender_documents", ["tender_id"], unique=False
    )
    op.create_table(
        "tender_embeddings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tender_id", sa.Uuid(), nullable=False),
        sa.Column(
            "chunk_kind",
            sa.Enum("title_summary", "scope_requirements", name="embedding_chunk"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("dims", sa.Integer(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=768), nullable=False),
        sa.Column("text_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tender_id"],
            ["tenders.id"],
            name=op.f("fk_tender_embeddings_tender_id_tenders"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tender_embeddings")),
        sa.UniqueConstraint(
            "tender_id",
            "chunk_kind",
            "chunk_index",
            "model",
            name=op.f("uq_tender_embeddings_tender_id_chunk_kind_chunk_index_model"),
        ),
    )
    op.create_index(
        "ix_tender_embeddings_vector",
        "tender_embeddings",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_table(
        "tender_extractions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tender_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=50), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "field_confidence",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "evidence", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum("succeeded", "failed", name="extraction_status"),
            server_default="succeeded",
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("tokens_in", sa.Integer(), server_default="0", nullable=False),
        sa.Column("tokens_out", sa.Integer(), server_default="0", nullable=False),
        sa.Column("latency_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_current", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tender_id"],
            ["tenders.id"],
            name=op.f("fk_tender_extractions_tender_id_tenders"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tender_extractions")),
        sa.UniqueConstraint(
            "tender_id", "version", name=op.f("uq_tender_extractions_tender_id_version")
        ),
    )
    op.create_index(
        "ix_tender_extractions_attributes",
        "tender_extractions",
        ["attributes"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "uq_tender_extractions_current",
        "tender_extractions",
        ["tender_id"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )


#: Alembic creates these implicitly with the tables and never drops them, which
#: would make a downgrade followed by an upgrade fail with DuplicateObjectError.
ENUM_TYPES = (
    "document_kind",
    "embedding_chunk",
    "extraction_status",
    "procurement_category",
    "source_health",
    "tender_status",
)


def downgrade() -> None:
    op.drop_index(
        "uq_tender_extractions_current",
        table_name="tender_extractions",
        postgresql_where=sa.text("is_current"),
    )
    op.drop_index(
        "ix_tender_extractions_attributes", table_name="tender_extractions", postgresql_using="gin"
    )
    op.drop_table("tender_extractions")
    op.drop_index(
        "ix_tender_embeddings_vector",
        table_name="tender_embeddings",
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.drop_table("tender_embeddings")
    op.drop_index("ix_tender_documents_tender_id", table_name="tender_documents")
    op.drop_table("tender_documents")
    op.drop_index(
        "ix_tenders_title_trgm",
        table_name="tenders",
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
    )
    op.drop_index("ix_tenders_status_deadline_at", table_name="tenders")
    op.drop_index("ix_tenders_search_tsv", table_name="tenders", postgresql_using="gin")
    op.drop_index("ix_tenders_published_at", table_name="tenders")
    op.drop_index("ix_tenders_deadline_at", table_name="tenders")
    op.drop_index("ix_tenders_country", table_name="tenders")
    op.drop_index(op.f("ix_tenders_content_hash"), table_name="tenders")
    op.drop_table("tenders")
    op.drop_index(op.f("ix_tender_sources_code"), table_name="tender_sources")
    op.drop_table("tender_sources")
    for enum_name in ENUM_TYPES:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
