"""Raw payload storage."""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from app.core.exceptions import NotFoundError
from app.ingestion.blobstore import (
    LocalFileBlobStore,
    build_key,
    content_digest,
    tender_document_key,
)

HTML = b"<html><body><table id='tenders'>notice 12345</table></body></html>"


@pytest.fixture
def store(tmp_path: Path) -> LocalFileBlobStore:
    return LocalFileBlobStore(tmp_path)


class TestRoundTrip:
    async def test_stored_payloads_come_back_unchanged(self, store: LocalFileBlobStore) -> None:
        await store.put("portal/notice.gz", HTML)

        assert await store.get("portal/notice.gz") == HTML

    async def test_payloads_are_compressed_on_disk(
        self, store: LocalFileBlobStore, tmp_path: Path
    ) -> None:
        """Scraped HTML is bulky and highly repetitive across notices."""
        body = HTML * 200

        await store.put("portal/big.gz", body)

        written = (tmp_path / "portal/big.gz").read_bytes()
        assert len(written) < len(body) / 5
        assert gzip.decompress(written) == body

    async def test_nested_directories_are_created(self, store: LocalFileBlobStore) -> None:
        await store.put("a/b/c/d/notice.gz", HTML)

        assert await store.exists("a/b/c/d/notice.gz")

    async def test_reading_a_missing_key_raises_not_found(self, store: LocalFileBlobStore) -> None:
        with pytest.raises(NotFoundError):
            await store.get("never/written.gz")

    async def test_exists_and_delete_report_accurately(self, store: LocalFileBlobStore) -> None:
        await store.put("portal/notice.gz", HTML)

        assert await store.exists("portal/notice.gz") is True
        assert await store.delete("portal/notice.gz") is True
        assert await store.exists("portal/notice.gz") is False
        assert await store.delete("portal/notice.gz") is False


class TestKeySafety:
    @pytest.mark.parametrize(
        "key",
        ["../escaped.gz", "portal/../../etc/passwd", "/etc/passwd"],
    )
    async def test_keys_cannot_escape_the_storage_root(
        self, store: LocalFileBlobStore, key: str
    ) -> None:
        """Keys are partly derived from portal-supplied identifiers."""
        with pytest.raises(ValueError, match="escapes"):
            await store.put(key, HTML)


class TestKeyGeneration:
    def test_the_digest_identifies_the_content(self) -> None:
        assert content_digest(HTML) == content_digest(HTML)
        assert content_digest(HTML) != content_digest(HTML + b"!")
        assert len(content_digest(HTML)) == 64

    def test_keys_are_grouped_by_source_and_day(self) -> None:
        key = build_key(
            source_code="egp_bd", tender_external_id="1331101", kind="detail_html", digest="a" * 64
        )

        assert key.startswith("egp_bd/")
        assert "/1331101/" in key
        assert key.endswith(".gz")

    def test_awkward_identifiers_are_made_path_safe(self) -> None:
        """Portal identifiers reach us unsanitised."""
        key = build_key(
            source_code="wb", tender_external_id="../../OP 12/34", kind="api_json", digest="b" * 64
        )

        assert ".." not in key
        assert " " not in key

    def test_the_same_payload_yields_the_same_key_and_digest(self) -> None:
        first = tender_document_key(
            source_code="egp_bd", tender_external_id="1331101", kind="detail_html", data=HTML
        )
        second = tender_document_key(
            source_code="egp_bd", tender_external_id="1331101", kind="detail_html", data=HTML
        )

        assert first == second

    def test_different_payloads_yield_different_keys(self) -> None:
        """A re-scrape that changed must not overwrite the earlier capture."""
        first, _ = tender_document_key(
            source_code="egp_bd", tender_external_id="1331101", kind="detail_html", data=HTML
        )
        second, _ = tender_document_key(
            source_code="egp_bd",
            tender_external_id="1331101",
            kind="detail_html",
            data=HTML + b"<p>amended</p>",
        )

        assert first != second
