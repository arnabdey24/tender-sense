"""Register the shipped portals, so a deployment ingests something.

``tender_sources`` was populated only by ``scripts.seed_demo`` — a development
fixture that also loads forty synthetic notices, and therefore one nobody runs
on a production VM. A real deployment consequently had no source rows at all,
the scrape dispatch had nothing to queue, and every user saw an empty pool with
no control anywhere that would have filled it. Registering the portals is not a
seeding convenience; it is what makes the product do its job, so it belongs in
the migration that every deploy already runs.

Insert-only, and keyed on ``code``: a portal an operator has retuned through
``PATCH /admin/sources/{id}`` is never overwritten by a later deploy.

Revision ID: 0012_default_sources
Revises: 0011_workspace_conversations
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.ids import new_id

# The living definition, so a selector or endpoint fix is made in one place
# rather than copied into whichever migration happened to install it.
from app.ingestion.portals import DEFAULT_SOURCES

revision: str = "0012_default_sources"
down_revision: str | None = "0011_workspace_conversations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    for spec in DEFAULT_SOURCES:
        connection.execute(
            sa.text(
                """
                INSERT INTO tender_sources
                    (id, code, name, adapter_key, base_url, country, enabled,
                     schedule_cron, config, cursor, consecutive_failures, health,
                     created_at, updated_at)
                VALUES
                    (:id, :code, :name, :adapter_key, :base_url, :country, :enabled,
                     :schedule_cron, CAST(:config AS jsonb), '{}'::jsonb, 0, 'ok',
                     NOW(), NOW())
                ON CONFLICT (code) DO NOTHING
                """
            ),
            {
                "id": new_id(),
                "code": spec["code"],
                "name": spec["name"],
                "adapter_key": spec["adapter_key"],
                "base_url": spec["base_url"],
                "country": spec.get("country"),
                "enabled": spec.get("enabled", True),
                "schedule_cron": spec.get("schedule_cron"),
                "config": json.dumps(spec.get("config", {})),
            },
        )


def downgrade() -> None:
    # Only rows this revision could have created, and only while they hold
    # nothing: a portal that has since ingested notices is somebody's data now,
    # and dropping it would cascade away every tender scraped from it.
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            DELETE FROM tender_sources s
            WHERE s.code = ANY(:codes)
              AND NOT EXISTS (SELECT 1 FROM tenders t WHERE t.source_id = s.id)
            """
        ),
        {"codes": [spec["code"] for spec in DEFAULT_SOURCES]},
    )
