"""Parsing uploads before they reach the database."""

from __future__ import annotations

import json

import pytest

from app.core.exceptions import ValidationError
from app.ingestion.importer import parse_payload

ROW = {
    "source_code": "egp_bd",
    "external_id": "1331101",
    "canonical_url": "https://example.invalid/1331101",
    "title": "Supply of solar water pumps",
}


class TestJson:
    def test_reads_an_array_of_tenders(self) -> None:
        rows = parse_payload(json.dumps([ROW, ROW]))

        assert len(rows) == 2
        assert rows[0]["external_id"] == "1331101"

    def test_reads_an_object_wrapping_a_tenders_key(self) -> None:
        rows = parse_payload(json.dumps({"tenders": [ROW]}))

        assert len(rows) == 1

    def test_reads_a_single_object_as_one_row(self) -> None:
        assert len(parse_payload(json.dumps(ROW))) == 1

    def test_accepts_bytes(self) -> None:
        assert len(parse_payload(json.dumps([ROW]).encode())) == 1

    def test_reports_malformed_json_clearly(self) -> None:
        with pytest.raises(ValidationError) as exc:
            parse_payload('[{"external_id": ')

        assert exc.value.code == "invalid_json"

    def test_rejects_a_bare_json_scalar(self) -> None:
        with pytest.raises(ValidationError):
            parse_payload("42")


class TestCsv:
    def test_reads_a_header_and_rows(self) -> None:
        csv_text = (
            "source_code,external_id,canonical_url,title\n"
            "egp_bd,1331101,https://example.invalid/1,Supply of pumps\n"
            "egp_bd,1331102,https://example.invalid/2,Network equipment\n"
        )

        rows = parse_payload(csv_text)

        assert len(rows) == 2
        assert rows[1]["title"] == "Network equipment"

    def test_blank_cells_are_omitted_rather_than_sent_as_empty_strings(self) -> None:
        """An empty cell means "not provided", not "set this to an empty string"."""
        csv_text = (
            "source_code,external_id,canonical_url,title,summary\n"
            "egp_bd,1331101,https://example.invalid/1,Supply of pumps,\n"
        )

        rows = parse_payload(csv_text)

        assert "summary" not in rows[0]

    def test_an_empty_csv_is_reported(self) -> None:
        with pytest.raises(ValidationError) as exc:
            parse_payload("source_code,external_id\n")

        assert exc.value.code == "empty_import"
