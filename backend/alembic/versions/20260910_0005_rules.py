"""Stored bidding criteria, their immutable versions, overrides and FX rates.

Revision ID: 0005_rules
Revises: 0004_profiles_matching
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_rules"
down_revision: str | None = "0004_profiles_matching"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fx_rates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("base", sa.String(length=3), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("rate", sa.Float(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fx_rates")),
        sa.UniqueConstraint(
            "base", "currency", "as_of", name=op.f("uq_fx_rates_base_currency_as_of")
        ),
    )
    op.create_table(
        "rule_overrides",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("tender_id", sa.Uuid(), nullable=False),
        sa.Column("rule_id", sa.String(length=64), nullable=False),
        sa.Column("verdict", sa.Enum("pass", "fail", name="override_verdict"), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
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
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_rule_overrides_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_rule_overrides_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tender_id"],
            ["tenders.id"],
            name=op.f("fk_rule_overrides_tender_id_tenders"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rule_overrides")),
        sa.UniqueConstraint(
            "org_id",
            "tender_id",
            "rule_id",
            name=op.f("uq_rule_overrides_org_id_tender_id_rule_id"),
        ),
    )
    op.create_index(
        "ix_rule_overrides_org_id_tender_id",
        "rule_overrides",
        ["org_id", "tender_id"],
        unique=False,
    )
    op.create_table(
        "rule_sets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("current_version_id", sa.Uuid(), nullable=True),
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
            name=op.f("fk_rule_sets_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rule_sets")),
    )
    op.create_index("ix_rule_sets_org_id", "rule_sets", ["org_id"], unique=False)
    op.create_index(
        "uq_rule_sets_active_per_org",
        "rule_sets",
        ["org_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )
    op.create_table(
        "rule_set_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("rule_set_id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column(
            "definition",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
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
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_rule_set_versions_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_rule_set_versions_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["rule_set_id"],
            ["rule_sets.id"],
            name=op.f("fk_rule_set_versions_rule_set_id_rule_sets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rule_set_versions")),
        sa.UniqueConstraint(
            "rule_set_id",
            "version_number",
            name=op.f("uq_rule_set_versions_rule_set_id_version_number"),
        ),
    )
    op.create_index(
        "ix_rule_set_versions_rule_set_id", "rule_set_versions", ["rule_set_id"], unique=False
    )


#: Alembic creates these implicitly with the tables and never drops them, which
#: would make a downgrade followed by an upgrade fail with DuplicateObjectError.
ENUM_TYPES = ("override_verdict",)


def downgrade() -> None:
    op.drop_index("ix_rule_set_versions_rule_set_id", table_name="rule_set_versions")
    op.drop_table("rule_set_versions")
    op.drop_index(
        "uq_rule_sets_active_per_org", table_name="rule_sets", postgresql_where=sa.text("is_active")
    )
    op.drop_index("ix_rule_sets_org_id", table_name="rule_sets")
    op.drop_table("rule_sets")
    op.drop_index("ix_rule_overrides_org_id_tender_id", table_name="rule_overrides")
    op.drop_table("rule_overrides")
    op.drop_table("fx_rates")
    for enum_name in ENUM_TYPES:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
