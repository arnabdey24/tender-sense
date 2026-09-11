"""Asian Development Bank procurement notices.

The obvious route — scrape ``adb.org/projects/tenders`` — does not work and is
worth recording so nobody spends an afternoon rediscovering it. That page sits
behind Cloudflare, which answers a plain HTTP client with a 403 challenge page,
and the listing itself is rendered client-side, so even past the challenge
there is no markup to parse.

What the page actually does is query a **public SearchStax (Solr) index** with a
read-only token shipped to every browser that loads it. That endpoint is on a
different host, is not behind the challenge, answers in JSON, pages cleanly, and
carries every field a notice needs in the listing row — so there is no detail
fetch and no browser.

Two consequences worth knowing:

* **The token is ADB's, not ours.** It is public by construction — anybody who
  opens the page has it — but it is theirs to rotate. It lives in the source
  row's config rather than in this file, so an operator who sees the portal go
  degraded can paste a new one from the page's network tab and fix production
  without a deploy.
* **Only ``Active`` notices are asked for.** The index holds 51,000 documents
  going back years; 462 of them are open. Pulling the history would bury the
  pool in notices that closed in 2019.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.ingestion.adapters.base import (
    NoticeRef,
    RawDocument,
    SourceHealthReport,
    TenderIn,
    register_adapter,
)
from app.ingestion.countries import country_code
from app.ingestion.retry import with_retry
from app.modules.tenders.models import DocumentKind, ProcurementCategory, TenderStatus

logger = get_logger(__name__)

BASE_URL = "https://searchcloud-2-ap-southeast-1.searchstax.com"
SELECT_PATH = "/29847/tenders-11959/emselect"
SITE_URL = "https://www.adb.org"

#: ADB's own public read key, as shipped in the tenders page. Overridable per
#: source row; see the module docstring.
DEFAULT_TOKEN = "2a076eb3a48fd68fc78506c1a16a5d5000da76e4"

PAGE_SIZE = 100

#: Solr's field names carry their type and language. Naming them once here
#: keeps the rest of the module readable.
F_TITLE = "tm_X3b_en_title"
F_COUNTRY = "tm_X3b_en_country"
F_SECTOR = "tm_X3b_en_sector"
F_STATUS = "tm_X3b_en_status"
F_TYPE = "tm_X3b_en_type"
F_PROJECT = "tm_X3b_en_project_number"

#: ``/node/1174256`` — the only stable identifier in the document. Solr's own
#: ``id`` embeds the index name and a build prefix, so it changes when ADB
#: reindexes and would re-ingest the entire portal as new notices.
_NODE = re.compile(r"/node/(\d+)")

#: ADB's notice types. Consulting is the only one the portal states plainly;
#: an "Invitation for Bids" may be goods or works and the document does not say
#: which, so it stays UNKNOWN rather than being guessed into a category a
#: tenant's eligibility rule might then filter on.
_CATEGORIES: dict[str, ProcurementCategory] = {
    "firm": ProcurementCategory.CONSULTING,
    "individual": ProcurementCategory.CONSULTING,
}


def _first(value: Any) -> str | None:
    """Solr returns multi-valued text fields as lists of one."""
    if isinstance(value, list):
        value = value[0] if value else None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_date(value: Any) -> datetime | None:
    """Solr date fields are ``2026-11-02T12:00:00Z``."""
    text = _first(value)
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def _node_id(doc: dict[str, Any]) -> str | None:
    match = _NODE.search(str(doc.get("ss_url") or ""))
    return match.group(1) if match else None


@register_adapter
class AdbAdapter:
    """Implements :class:`~app.ingestion.adapters.base.SourceAdapter`."""

    key = "adb"

    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        config: dict[str, Any] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.config = config or {}
        self._client = client

    @property
    def _token(self) -> str:
        return str(self.config.get("token") or DEFAULT_TOKEN)

    @property
    def _path(self) -> str:
        return str(self.config.get("select_path") or SELECT_PATH)

    def _http(self) -> httpx.AsyncClient:
        return self._client or httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            headers={
                "User-Agent": settings.scraper_user_agent,
                "Authorization": f"Token {self._token}",
            },
            follow_redirects=True,
        )

    def _params(self, offset: int, rows: int) -> dict[str, Any]:
        return {
            "q": "*:*",
            # Without this the pass reaches back through every notice ADB has
            # ever posted, newest-first, and fills the pool with closed ones.
            "fq": str(self.config.get("filter") or f"{F_STATUS}:Active"),
            "sort": "ds_date_posted desc",
            "rows": rows,
            "start": offset,
            "wt": "json",
        }

    async def list_notices(
        self,
        *,
        since: datetime | None = None,
        cursor: dict[str, Any] | None = None,
        limit_pages: int = 5,
    ) -> AsyncIterator[NoticeRef]:
        """Yield active notices, most recently posted first."""
        seen: set[str] = set((cursor or {}).get("seen_ids") or [])
        rows = int(self.config.get("rows", PAGE_SIZE))
        client = self._http()
        owned = self._client is None

        try:
            for page in range(limit_pages):

                async def fetch(page: int = page) -> httpx.Response:
                    got = await client.get(
                        f"{self.base_url}{self._path}",
                        params=self._params(page * rows, rows),
                        headers={"Authorization": f"Token {self._token}"},
                    )
                    got.raise_for_status()
                    return got

                response = await with_retry(fetch, what="adb listing")
                docs = (response.json().get("response") or {}).get("docs") or []
                if not docs:
                    return

                for doc in docs:
                    external_id = _node_id(doc)
                    if not external_id:
                        # No stable identifier means no idempotent upsert, and
                        # a row we would re-create on every pass.
                        continue
                    if external_id in seen:
                        logger.info("adb_reached_known_notice", notice_id=external_id)
                        return

                    published = _parse_date(doc.get("ds_date_posted"))
                    if since and published and published < since:
                        return

                    yield NoticeRef(
                        external_id=external_id,
                        url=f"{SITE_URL}/node/{external_id}",
                        title=_first(doc.get(F_TITLE)),
                        published_at=published,
                        deadline_at=_parse_date(doc.get("ds_date_closing")),
                        listing_data=doc,
                    )
        finally:
            if owned:
                await client.aclose()

    async def fetch_detail(self, ref: NoticeRef) -> list[RawDocument]:
        """The listing row is the whole notice.

        Stored anyway so ``normalize`` can be replayed offline over the bytes we
        actually saw, which is what makes re-parse safe against a portal that
        has started refusing us.
        """
        return [
            RawDocument(
                kind=DocumentKind.API_JSON,
                content=json.dumps(ref.listing_data, sort_keys=True).encode(),
                url=ref.url,
                content_type="application/json",
            )
        ]

    def normalize(self, ref: NoticeRef, documents: list[RawDocument]) -> TenderIn:
        """Pure: same bytes in, same row out. No network."""
        doc: dict[str, Any] = dict(ref.listing_data)
        for document in documents:
            if document.kind is DocumentKind.API_JSON:
                doc = json.loads(document.content.decode())
                break

        external_id = _node_id(doc) or ref.external_id
        notice_type = _first(doc.get(F_TYPE))
        sector = _first(doc.get(F_SECTOR))
        project = _first(doc.get(F_PROJECT))
        status_text = (_first(doc.get(F_STATUS)) or "").lower()
        title = _first(doc.get(F_TITLE)) or ref.title or f"ADB notice {external_id}"

        file_url = _first(doc.get("ss_file_url"))
        if file_url and file_url.startswith("/"):
            file_url = f"{SITE_URL}{file_url}"

        return TenderIn(
            external_id=external_id,
            canonical_url=f"{SITE_URL}/node/{external_id}",
            title=title[:1000],
            # The index carries no abstract, so the summary is assembled from
            # the facets rather than invented: what kind of notice, for which
            # project, in which sector.
            summary=" · ".join(p for p in (notice_type, project, sector) if p) or None,
            procuring_entity="Asian Development Bank",
            country=country_code(_first(doc.get(F_COUNTRY))),
            procurement_method=notice_type,
            procurement_category=_CATEGORIES.get(
                (notice_type or "").lower(), ProcurementCategory.UNKNOWN
            ),
            published_at=_parse_date(doc.get("ds_date_posted")),
            deadline_at=_parse_date(doc.get("ds_date_closing")),
            status=TenderStatus.OPEN if status_text == "active" else TenderStatus.CLOSED,
            language="English",
            portal_metadata={
                "notice_type": notice_type,
                "notice_status": _first(doc.get(F_STATUS)),
                "project_number": project,
                "sector": sector,
                "country_name": _first(doc.get(F_COUNTRY)),
                "document_url": file_url,
                "solr_id": doc.get("id"),
            },
        )

    async def healthcheck(self) -> SourceHealthReport:
        client = self._http()
        owned = self._client is None
        try:
            response = await client.get(
                f"{self.base_url}{self._path}",
                params=self._params(0, 1),
                headers={"Authorization": f"Token {self._token}"},
            )
            response.raise_for_status()
            found = int((response.json().get("response") or {}).get("numFound") or 0)
            return SourceHealthReport(
                reachable=found > 0,
                detail=None if found else "Index returned no active notices.",
            )
        except Exception as exc:
            return SourceHealthReport(reachable=False, detail=str(exc)[:200])
        finally:
            if owned:
                await client.aclose()
