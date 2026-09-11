"""Operator-tunable limits, so a rate limit is not a redeploy.

Rate limits were environment variables, which makes every adjustment a
deployment — and the moments that call for one are exactly the moments nobody
wants to deploy: a portal being hammered during a demo, one tenant consuming the
model budget, a sign-in throttle that turns out to be tighter than a real office
sharing one address.

One row, holding the whole set. An absent row means the deployment's own
configuration applies, so this table starts empty and nothing changes until
somebody decides it should.

Revision ID: 0013_platform_settings
Revises: 0012_default_sources
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_platform_settings"
down_revision: str | None = "0012_default_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_settings",
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column(
            "value", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("platform_settings")
