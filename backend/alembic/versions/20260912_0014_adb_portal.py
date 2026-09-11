"""Register the ADB portal on deployments that already ran 0012.

``0012_default_sources`` reads the living ``DEFAULT_SOURCES`` list, so a fresh
database gets every portal this build ships with — including this one. A
deployment that has already run it does not re-run it, and would therefore never
see a portal added afterwards. So each new portal brings its own revision.

The statement is the same insert-only, ``code``-keyed upsert: a portal an
operator has retuned through ``PATCH /admin/sources/{id}`` is never overwritten,
and on a fresh database where 0012 just inserted it this is a no-op.

Revision ID: 0014_adb_portal
Revises: 0013_platform_settings
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.ids import new_id
from app.ingestion.portals import DEFAULT_SOURCES

revision: str = "0014_adb_portal"
down_revision: str | None = "0013_platform_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Named rather than "whatever the list holds now", so re-running this revision
#: years from now installs what it installed the day it was written.
CODES = ("adb",)


def upgrade() -> None:
    connection = op.get_bind()
    for spec in (s for s in DEFAULT_SOURCES if s["code"] in CODES):
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
    # Only while the portal holds nothing: once it has ingested notices it is
    # somebody's data, and dropping the row cascades away every tender under it.
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            DELETE FROM tender_sources s
            WHERE s.code = ANY(:codes)
              AND NOT EXISTS (SELECT 1 FROM tenders t WHERE t.source_id = s.id)
            """
        ),
        {"codes": list(CODES)},
    )
