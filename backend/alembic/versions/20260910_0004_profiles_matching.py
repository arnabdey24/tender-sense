"""Company profiles, their facet embeddings, and per-tenant matches.

Revision ID: 0004_profiles_matching
Revises: 0003_tender_pool
"""

from __future__ import annotations

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_profiles_matching"
down_revision: str | None = "0003_tender_pool"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "matching_config",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("thresholds_version", sa.Integer(), nullable=False),
        sa.Column("grade_s_threshold", sa.Float(), nullable=False),
        sa.Column("grade_a_threshold", sa.Float(), nullable=False),
        sa.Column("grade_b_threshold", sa.Float(), nullable=False),
        sa.Column("max_facet_weight", sa.Float(), nullable=False),
        sa.Column("mean_facet_weight", sa.Float(), nullable=False),
        sa.Column("top_facets", sa.Integer(), nullable=False),
        sa.Column("keyword_weight", sa.Float(), nullable=False),
        sa.Column("embedding_model", sa.String(length=100), nullable=False),
        sa.Column("generation_model", sa.String(length=100), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_matching_config")),
    )
    op.create_index(
        op.f("ix_matching_config_is_active"), "matching_config", ["is_active"], unique=False
    )
    op.create_table(
        "company_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("overview", sa.Text(), nullable=True),
        sa.Column(
            "sectors", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
        ),
        sa.Column(
            "geographies",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "keywords", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
        ),
        sa.Column("annual_turnover", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("turnover_currency", sa.String(length=3), nullable=True),
        sa.Column("turnover_year", sa.Integer(), nullable=True),
        sa.Column("years_in_business", sa.Integer(), nullable=True),
        sa.Column("employee_count", sa.Integer(), nullable=True),
        sa.Column("accepts_jv", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("completeness", sa.Integer(), server_default="0", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
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
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_company_profiles_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_company_profiles")),
        sa.UniqueConstraint("org_id", name=op.f("uq_company_profiles_org_id")),
    )
    op.create_table(
        "tender_matches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("tender_id", sa.Uuid(), nullable=False),
        sa.Column("similarity", sa.Float(), nullable=False),
        sa.Column(
            "score_breakdown",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("grade", sa.Enum("S", "A", "B", "C", name="match_grade"), nullable=False),
        sa.Column(
            "eligibility_status",
            sa.Enum("eligible", "needs_verification", "ineligible", name="eligibility_status"),
            nullable=False,
        ),
        sa.Column(
            "rule_results",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "recommendation", sa.Enum("bid", "hold", "skip", name="recommendation"), nullable=False
        ),
        sa.Column(
            "urgency",
            sa.Enum("expired", "critical", "high", "normal", "low", "unknown", name="urgency"),
            nullable=False,
        ),
        sa.Column(
            "explanation_kind", sa.Enum("templated", "llm", name="explanation_kind"), nullable=False
        ),
        sa.Column("explanation_text", sa.Text(), nullable=True),
        sa.Column(
            "explanation",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("inputs_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("rule_set_version_id", sa.Uuid(), nullable=True),
        sa.Column("extraction_id", sa.Uuid(), nullable=True),
        sa.Column("embedding_model", sa.String(length=100), nullable=False),
        sa.Column("thresholds_version", sa.Integer(), nullable=False),
        sa.Column("instant_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_matched_at", sa.DateTime(timezone=True), nullable=True),
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
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_tender_matches_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tender_id"],
            ["tenders.id"],
            name=op.f("fk_tender_matches_tender_id_tenders"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tender_matches")),
        sa.UniqueConstraint("org_id", "tender_id", name=op.f("uq_tender_matches_org_id_tender_id")),
    )
    op.create_index(
        op.f("ix_tender_matches_inputs_fingerprint"),
        "tender_matches",
        ["inputs_fingerprint"],
        unique=False,
    )
    op.create_index(
        "ix_tender_matches_org_id_created_at",
        "tender_matches",
        ["org_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_tender_matches_org_id_grade", "tender_matches", ["org_id", "grade"], unique=False
    )
    op.create_index(
        "ix_tender_matches_org_id_similarity",
        "tender_matches",
        ["org_id", "similarity"],
        unique=False,
    )
    op.create_index("ix_tender_matches_tender_id", "tender_matches", ["tender_id"], unique=False)
    op.create_table(
        "profile_certifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("issuer", sa.String(length=200), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
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
            ["profile_id"],
            ["company_profiles.id"],
            name=op.f("fk_profile_certifications_profile_id_company_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_profile_certifications")),
        sa.UniqueConstraint(
            "profile_id", "code", name=op.f("uq_profile_certifications_profile_id_code")
        ),
    )
    op.create_index(
        "ix_profile_certifications_profile_id",
        "profile_certifications",
        ["profile_id"],
        unique=False,
    )
    op.create_table(
        "profile_embeddings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column(
            "facet_kind",
            sa.Enum("overview", "service", "past_project", "sector_geo", name="profile_facet"),
            nullable=False,
        ),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("label", sa.String(length=300), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("dims", sa.Integer(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(768), nullable=False),
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
            ["profile_id"],
            ["company_profiles.id"],
            name=op.f("fk_profile_embeddings_profile_id_company_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_profile_embeddings")),
        sa.UniqueConstraint(
            "profile_id",
            "facet_kind",
            "source_id",
            "model",
            name=op.f("uq_profile_embeddings_profile_id_facet_kind_source_id_model"),
        ),
    )
    op.create_index(
        "ix_profile_embeddings_profile_id", "profile_embeddings", ["profile_id"], unique=False
    )
    op.create_index(
        "ix_profile_embeddings_vector",
        "profile_embeddings",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_table(
        "profile_past_projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("client", sa.String(length=300), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sector", sa.String(length=50), nullable=True),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.Column("value", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("started_on", sa.Date(), nullable=True),
        sa.Column("completed_on", sa.Date(), nullable=True),
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
            ["profile_id"],
            ["company_profiles.id"],
            name=op.f("fk_profile_past_projects_profile_id_company_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_profile_past_projects")),
    )
    op.create_index(
        "ix_profile_past_projects_profile_id", "profile_past_projects", ["profile_id"], unique=False
    )
    op.create_table(
        "profile_services",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sector", sa.String(length=50), nullable=True),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
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
            ["profile_id"],
            ["company_profiles.id"],
            name=op.f("fk_profile_services_profile_id_company_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_profile_services")),
    )
    op.create_index(
        "ix_profile_services_profile_id", "profile_services", ["profile_id"], unique=False
    )
    op.create_table(
        "tender_match_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("match_id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("similarity", sa.Float(), nullable=False),
        sa.Column("grade", sa.Enum("S", "A", "B", "C", name="match_grade"), nullable=False),
        sa.Column(
            "eligibility_status",
            sa.Enum("eligible", "needs_verification", "ineligible", name="eligibility_status"),
            nullable=False,
        ),
        sa.Column(
            "recommendation", sa.Enum("bid", "hold", "skip", name="recommendation"), nullable=False
        ),
        sa.Column("reason", sa.String(length=100), nullable=False),
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
            ["match_id"],
            ["tender_matches.id"],
            name=op.f("fk_tender_match_history_match_id_tender_matches"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_tender_match_history_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tender_match_history")),
    )
    op.create_index(
        "ix_tender_match_history_match_id_created_at",
        "tender_match_history",
        ["match_id", "created_at"],
        unique=False,
    )


#: Alembic creates these implicitly with the tables and never drops them, which
#: would make a downgrade followed by an upgrade fail with DuplicateObjectError.
ENUM_TYPES = (
    "eligibility_status",
    "explanation_kind",
    "match_grade",
    "profile_facet",
    "recommendation",
    "urgency",
)


def downgrade() -> None:
    op.drop_index("ix_tender_match_history_match_id_created_at", table_name="tender_match_history")
    op.drop_table("tender_match_history")
    op.drop_index("ix_profile_services_profile_id", table_name="profile_services")
    op.drop_table("profile_services")
    op.drop_index("ix_profile_past_projects_profile_id", table_name="profile_past_projects")
    op.drop_table("profile_past_projects")
    op.drop_index(
        "ix_profile_embeddings_vector",
        table_name="profile_embeddings",
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.drop_index("ix_profile_embeddings_profile_id", table_name="profile_embeddings")
    op.drop_table("profile_embeddings")
    op.drop_index("ix_profile_certifications_profile_id", table_name="profile_certifications")
    op.drop_table("profile_certifications")
    op.drop_index("ix_tender_matches_tender_id", table_name="tender_matches")
    op.drop_index("ix_tender_matches_org_id_similarity", table_name="tender_matches")
    op.drop_index("ix_tender_matches_org_id_grade", table_name="tender_matches")
    op.drop_index("ix_tender_matches_org_id_created_at", table_name="tender_matches")
    op.drop_index(op.f("ix_tender_matches_inputs_fingerprint"), table_name="tender_matches")
    op.drop_table("tender_matches")
    op.drop_table("company_profiles")
    op.drop_index(op.f("ix_matching_config_is_active"), table_name="matching_config")
    op.drop_table("matching_config")
    for enum_name in ENUM_TYPES:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
