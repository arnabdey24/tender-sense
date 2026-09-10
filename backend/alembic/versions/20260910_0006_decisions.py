"""Bid / hold / skip decisions, kept as an append-only trail.

Revision ID: 0006_decisions
Revises: 0005_rules
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_decisions"
down_revision: str | None = "0005_rules"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tender_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("tender_id", sa.Uuid(), nullable=False),
        sa.Column(
            "decision", sa.Enum("bid", "hold", "skip", name="tender_decision"), nullable=False
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("is_current", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("decided_by_id", sa.Uuid(), nullable=True),
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
            ["decided_by_id"],
            ["users.id"],
            name=op.f("fk_tender_decisions_decided_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_tender_decisions_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tender_id"],
            ["tenders.id"],
            name=op.f("fk_tender_decisions_tender_id_tenders"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tender_decisions")),
    )
    op.create_index(
        "ix_tender_decisions_org_id_decision",
        "tender_decisions",
        ["org_id", "decision"],
        unique=False,
    )
    op.create_index(
        "ix_tender_decisions_org_id_tender_id",
        "tender_decisions",
        ["org_id", "tender_id"],
        unique=False,
    )
    op.create_index(
        "uq_tender_decisions_current",
        "tender_decisions",
        ["org_id", "tender_id"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )


#: Alembic creates this implicitly with the table and never drops it, which
#: would make a downgrade followed by an upgrade fail with DuplicateObjectError.
ENUM_TYPES = ("tender_decision",)


def downgrade() -> None:
    op.drop_index(
        "uq_tender_decisions_current",
        table_name="tender_decisions",
        postgresql_where=sa.text("is_current"),
    )
    op.drop_index("ix_tender_decisions_org_id_tender_id", table_name="tender_decisions")
    op.drop_index("ix_tender_decisions_org_id_decision", table_name="tender_decisions")
    op.drop_table("tender_decisions")
    for enum_name in ENUM_TYPES:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
