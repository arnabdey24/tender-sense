"""Storage for raw portal payloads.

Every fetched listing row, detail page and API response is written here before
it is parsed. When a portal changes its markup and the parser breaks, the fix
can be replayed over stored bytes instead of re-scraping, which matters because
these portals are slow, rate limited and sometimes remove closed notices.

Bodies are gzipped on a volume rather than kept in Postgres: they are large,
write-once and read rarely, and keeping them out of the database keeps backups
and query plans small. The protocol leaves room for an object store later.
"""

from __future__ import annotations

import gzip
import hashlib
from datetime import date
from pathlib import Path
from typing import Protocol

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger

logger = get_logger(__name__)


def content_digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_key(*, source_code: str, tender_external_id: str, kind: str, digest: str) -> str:
    """A stable, sortable path.

    Dating the prefix keeps directories small enough to list and makes a
    retention sweep a matter of deleting old day folders.
    """
    safe_external_id = "".join(
        char if char.isalnum() or char in "-_" else "_" for char in tender_external_id
    )[:100]
    today = date.today().isoformat()
    return f"{source_code}/{today}/{safe_external_id}/{kind}-{digest[:16]}.gz"


class BlobStore(Protocol):
    """Write-once storage addressed by key."""

    async def put(self, key: str, data: bytes) -> int:
        """Store ``data`` and return the number of bytes written on disk."""

    async def get(self, key: str) -> bytes: ...

    async def exists(self, key: str) -> bool: ...

    async def delete(self, key: str) -> bool: ...


class LocalFileBlobStore:
    """Gzipped files under a directory, typically a mounted Docker volume."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or settings.blob_storage_dir)

    def _path(self, key: str) -> Path:
        # Refuse keys that would escape the root, whatever produced them.
        candidate = (self.root / key).resolve()
        root = self.root.resolve()
        if not candidate.is_relative_to(root):
            raise ValueError(f"Blob key escapes the storage root: {key!r}")
        return candidate

    async def put(self, key: str, data: bytes) -> int:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        compressed = gzip.compress(data)
        path.write_bytes(compressed)
        logger.debug("blob_stored", key=key, raw_bytes=len(data), stored_bytes=len(compressed))
        return len(compressed)

    async def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.exists():
            raise NotFoundError(f"No stored payload for {key!r}.", code="blob_not_found")
        return gzip.decompress(path.read_bytes())

    async def exists(self, key: str) -> bool:
        return self._path(key).exists()

    async def delete(self, key: str) -> bool:
        path = self._path(key)
        if not path.exists():
            return False
        path.unlink()
        return True


_store: BlobStore | None = None


def get_blob_store() -> BlobStore:
    global _store
    if _store is None:
        _store = LocalFileBlobStore()
    return _store


def set_blob_store(store: BlobStore | None) -> None:
    """Point storage elsewhere; tests use a temporary directory."""
    global _store
    _store = store


def tender_document_key(
    *, source_code: str, tender_external_id: str, kind: str, data: bytes
) -> tuple[str, str]:
    """Return ``(key, digest)`` for a payload."""
    digest = content_digest(data)
    return (
        build_key(
            source_code=source_code,
            tender_external_id=tender_external_id,
            kind=kind,
            digest=digest,
        ),
        digest,
    )
