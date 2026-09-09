"""Enable required Postgres extensions.

Revision ID: 0001_extensions
Revises:
Create Date: 2026-09-09
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001_extensions"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EXTENSIONS = ("vector", "citext", "pg_trgm")


def upgrade() -> None:
    for extension in EXTENSIONS:
        op.execute(f'CREATE EXTENSION IF NOT EXISTS "{extension}"')


def downgrade() -> None:
    for extension in reversed(EXTENSIONS):
        op.execute(f'DROP EXTENSION IF EXISTS "{extension}"')
