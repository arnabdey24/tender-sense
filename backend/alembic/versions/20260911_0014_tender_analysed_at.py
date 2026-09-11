"""Mark when a notice was matched for every tenant, not just for one.

A manual sync scores only for the organization that pressed it. Without a
marker, the notices it stores are neither new nor amended on the next
scheduled pass, so nothing would ever enqueue them for the other tenants and
they would stay ungraded permanently. Null means no tenant-wide pass has
reached the row yet; the six-hourly sweep looks for exactly that.

Existing rows are backfilled to `now()`: everything already in the pool was
stored by a pass that matched every tenant, so treating them as unanalysed
would re-run the whole pipeline — and the AI spend that goes with it — on the
first sweep after deploying.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0014_tender_analysed_at"
down_revision: str | None = "0013_platform_settings"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("tenders", sa.Column("analysed_at", sa.DateTime(), nullable=True))
    op.execute("UPDATE tenders SET analysed_at = now()")
    op.create_index("ix_tenders_analysed_at", "tenders", ["analysed_at"])


def downgrade() -> None:
    op.drop_index("ix_tenders_analysed_at", table_name="tenders")
    op.drop_column("tenders", "analysed_at")
