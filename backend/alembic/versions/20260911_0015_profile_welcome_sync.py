"""One portal pull when a profile first becomes worth matching against.

Filling in a capability profile is the moment someone expects the product to
do something. Until then the pool holds whatever the last scheduled pass left,
which on a quiet deployment can be nothing at all. So the save that carries a
profile over the matching threshold pulls the portals once.

Once, ever. The stamp is what separates a courtesy from asking a portal again
on every edit, and portals that have been running since 2011 are the reason
this product is careful about that.

Profiles already above the threshold are backfilled to `now()`: they have been
matching for as long as they have existed, and firing a welcome pull for all
of them on their next edit would be a thundering herd dressed as a courtesy.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0015_profile_welcome_sync"
down_revision: str | None = "0014_tender_analysed_at"
branch_labels: str | None = None
depends_on: str | None = None

#: Matches WELCOME_SYNC_COMPLETENESS in app/modules/profiles/service.py and
#: PROFILE_SYNC_THRESHOLD in the frontend's use-portal-sync.ts.
THRESHOLD = 50


def upgrade() -> None:
    op.add_column(
        "company_profiles", sa.Column("welcome_sync_at", sa.DateTime(), nullable=True)
    )
    op.execute(
        f"UPDATE company_profiles SET welcome_sync_at = now() WHERE completeness >= {THRESHOLD}"
    )


def downgrade() -> None:
    op.drop_column("company_profiles", "welcome_sync_at")
