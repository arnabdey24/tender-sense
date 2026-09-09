"""Import notices from JSON or CSV.

Used by the seed script, the admin import endpoint and anyone pasting a notice
in by hand. Everything funnels through the same upsert path as the scrapers, so
imported rows are indistinguishable downstream.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.ingestion.adapters.base import TenderIn
from app.ingestion.service import UpsertOutcome, get_source_by_code, upsert_tender
from app.modules.tenders.models import TenderSource

logger = get_logger(__name__)

MANUAL_SOURCE_CODE = "manual"


@dataclass(slots=True)
class ImportReport:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    failed: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.created + self.updated + self.unchanged + self.failed

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "failed": self.failed,
            # Enough to fix the input without returning a wall of text.
            "errors": self.errors[:50],
        }


def parse_payload(raw: str | bytes, *, content_type: str | None = None) -> list[dict[str, Any]]:
    """Parse a JSON array or a CSV document into rows."""
    text = raw.decode() if isinstance(raw, bytes) else raw
    stripped = text.lstrip()

    looks_like_json = stripped.startswith(("[", "{"))
    if content_type and "csv" in content_type and not looks_like_json:
        looks_like_json = False

    if looks_like_json:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"Could not parse JSON: {exc}", code="invalid_json") from exc
        if isinstance(parsed, dict):
            parsed = parsed.get("tenders", [parsed])
        if not isinstance(parsed, list):
            raise ValidationError("Expected a JSON array of tenders.", code="invalid_json")
        return [dict(row) for row in parsed]

    reader = csv.DictReader(io.StringIO(text))
    rows = [{key: value for key, value in row.items() if value not in ("", None)} for row in reader]
    if not rows:
        raise ValidationError("No rows found in the uploaded file.", code="empty_import")
    return rows


async def import_tenders(
    session: AsyncSession,
    rows: list[dict[str, Any]],
    *,
    default_source: TenderSource | None = None,
) -> ImportReport:
    """Upsert parsed rows.

    A malformed row is recorded and skipped rather than failing the batch: a
    single bad line in a 2,000-row import should not discard the rest.
    """
    report = ImportReport()
    sources: dict[str, TenderSource] = {}
    if default_source is not None:
        sources[default_source.code] = default_source

    for index, row in enumerate(rows):
        payload = dict(row)
        source_code = str(payload.pop("source_code", "") or "") or (
            default_source.code if default_source else ""
        )
        if not source_code:
            report.failed += 1
            report.errors.append({"row": index, "error": "Missing source_code."})
            continue

        source = sources.get(source_code)
        if source is None:
            found = await get_source_by_code(session, source_code)
            if found is None:
                report.failed += 1
                report.errors.append({"row": index, "error": f"Unknown source {source_code!r}."})
                continue
            sources[source_code] = source = found

        try:
            data = TenderIn.model_validate(payload)
        except PydanticValidationError as exc:
            report.failed += 1
            first = exc.errors()[0]
            report.errors.append(
                {
                    "row": index,
                    "external_id": payload.get("external_id"),
                    "error": f"{'.'.join(str(part) for part in first['loc'])}: {first['msg']}",
                }
            )
            continue

        result = await upsert_tender(session, source=source, data=data)
        if result.outcome is UpsertOutcome.CREATED:
            report.created += 1
        elif result.outcome is UpsertOutcome.UPDATED:
            report.updated += 1
        else:
            report.unchanged += 1

    logger.info("import_finished", **report.as_dict() | {"errors": len(report.errors)})
    return report
