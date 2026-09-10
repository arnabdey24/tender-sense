"""Per-call model usage, so spend can be attributed and capped.

Revision ID: 0007_ai_usage
Revises: 0006_decisions
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_ai_usage"
down_revision: str | None = "0006_decisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_usage",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=True),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("purpose", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=False),
        sa.Column("tokens_out", sa.Integer(), nullable=False),
        sa.Column("calls", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
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
            name=op.f("fk_ai_usage_org_id_organizations"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_usage")),
    )
    op.create_index("ix_ai_usage_day_purpose", "ai_usage", ["day", "purpose"], unique=False)
    op.create_index("ix_ai_usage_org_id_day", "ai_usage", ["org_id", "day"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ai_usage_org_id_day", table_name="ai_usage")
    op.drop_index("ix_ai_usage_day_purpose", table_name="ai_usage")
    op.drop_table("ai_usage")
