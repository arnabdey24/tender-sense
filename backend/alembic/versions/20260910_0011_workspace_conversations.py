"""Allow a conversation that is not pinned to a single tender.

The assistant could only be opened from a notice, so there was no way to ask it
anything before you had chosen one — including asking it to help you choose.
A null ``tender_id`` is a workspace conversation: scoped to the organization and
the owner exactly as before, but about the shortlist rather than one notice.

Revision ID: 0011_workspace_conversations
Revises: 0010_assistant
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_workspace_conversations"
down_revision: str | None = "0010_assistant"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "assistant_conversations",
        "tender_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )


def downgrade() -> None:
    # A workspace conversation has no tender to fall back to, so the rows that
    # only this revision made possible are removed rather than given a wrong one.
    op.execute("DELETE FROM assistant_conversations WHERE tender_id IS NULL")
    op.alter_column(
        "assistant_conversations",
        "tender_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
