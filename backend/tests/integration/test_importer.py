"""Importing notices through the shared upsert path."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.db.session import session_scope
from app.ingestion.importer import import_tenders
from app.modules.tenders.models import TenderSource


@pytest.fixture
async def source() -> AsyncIterator[TenderSource]:
    record = TenderSource(
        code=f"test-{uuid4().hex[:8]}",
        name="Test Portal",
        adapter_key="test",
        base_url="https://example.invalid",
    )
    async with session_scope() as session:
        session.add(record)
        await session.flush()
        await session.refresh(record)
    yield record
    async with session_scope() as session:
        await session.execute(delete(TenderSource).where(TenderSource.id == record.id))


def row(source_code: str, external_id: str, **overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "source_code": source_code,
        "external_id": external_id,
        "canonical_url": f"https://example.invalid/{external_id}",
        "title": "Supply and installation of network equipment",
    }
    data.update(overrides)
    return data


async def test_valid_rows_are_created(source: TenderSource) -> None:
    async with session_scope() as session:
        report = await import_tenders(session, [row(source.code, "a1"), row(source.code, "a2")])

    assert (report.created, report.failed) == (2, 0)


async def test_reimporting_the_same_rows_changes_nothing(source: TenderSource) -> None:
    rows = [row(source.code, "b1")]
    async with session_scope() as session:
        await import_tenders(session, rows)

    async with session_scope() as session:
        report = await import_tenders(session, rows)

    assert (report.created, report.unchanged) == (0, 1)


async def test_a_changed_row_is_an_update(source: TenderSource) -> None:
    async with session_scope() as session:
        await import_tenders(session, [row(source.code, "c1")])

    async with session_scope() as session:
        report = await import_tenders(
            session, [row(source.code, "c1", title="Amended: supply of switches")]
        )

    assert report.updated == 1


async def test_one_bad_row_does_not_discard_the_batch(source: TenderSource) -> None:
    """A single malformed line in a large import must not lose the good rows."""
    rows = [
        row(source.code, "d1"),
        {"source_code": source.code, "external_id": "d2"},  # no url or title
        row(source.code, "d3"),
    ]

    async with session_scope() as session:
        report = await import_tenders(session, rows)

    assert (report.created, report.failed) == (2, 1)
    assert report.errors[0]["row"] == 1


async def test_an_unknown_source_is_reported_per_row(source: TenderSource) -> None:
    async with session_scope() as session:
        report = await import_tenders(
            session, [row(source.code, "e1"), row("no-such-portal", "e2")]
        )

    assert (report.created, report.failed) == (1, 1)
    assert "no-such-portal" in report.errors[0]["error"]


async def test_a_missing_source_code_is_reported(source: TenderSource) -> None:
    payload = row(source.code, "f1")
    payload.pop("source_code")

    async with session_scope() as session:
        report = await import_tenders(session, [payload])

    assert report.failed == 1
    assert "source_code" in report.errors[0]["error"]


async def test_a_default_source_covers_rows_without_one(source: TenderSource) -> None:
    payload = row(source.code, "g1")
    payload.pop("source_code")

    async with session_scope() as session:
        report = await import_tenders(session, [payload], default_source=source)

    assert report.created == 1


async def test_the_error_list_is_capped(source: TenderSource) -> None:
    """A pasted spreadsheet of rubbish should not return a wall of text."""
    rows = [{"source_code": source.code, "external_id": str(index)} for index in range(80)]

    async with session_scope() as session:
        report = await import_tenders(session, rows)

    assert report.failed == 80
    assert len(report.as_dict()["errors"]) == 50
