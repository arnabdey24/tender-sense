"""World Bank procurement notices.

A public JSON endpoint with no authentication, which makes it the sane portal to
prove the adapter contract against before touching anything that needs scraping.

Three things the endpoint demands, learned the hard way:

* **Always send `fl`.** Omitting the field list intermittently returns a 500.
* **Server-side date filters are unreliable**, so this polls newest-first and
  stops at the first identifier it already holds, rather than asking for
  "everything since yesterday" and trusting the answer.
* **Absent fields are omitted, not null.** A notice with no deadline simply has
  no `submission_deadline_date` key, so every read has to tolerate that.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx
from selectolax.parser import HTMLParser

from app.core.config import settings
from app.core.logging import get_logger
from app.ingestion.adapters.base import (
    NoticeRef,
    RawDocument,
    SourceHealthReport,
    TenderIn,
    register_adapter,
)
from app.modules.tenders.models import DocumentKind, ProcurementCategory, TenderStatus

logger = get_logger(__name__)

BASE_URL = "https://search.worldbank.org"
LISTING_PATH = "/api/v2/procnotices"
DETAIL_URL = "https://projects.worldbank.org/en/projects-operations/procurement-detail/{id}"

#: Omitting this intermittently 500s, so it is not optional.
FIELDS = (
    "id,notice_type,notice_status,noticedate,submission_deadline_date,"
    "submission_deadline_time,project_id,project_name,project_ctry_name,sector,"
    "procurement_group,procurement_group_desc,procurement_method_code,"
    "procurement_method_name,bid_reference_no,bid_description,notice_text,"
    "notice_lang_name,contact_name,contact_organization,contact_email"
)

PAGE_SIZE = 100


def _field_list(config: dict[str, Any]) -> str:
    """The `fl` parameter, however the source row spelled it."""
    value = config.get("fl") or config.get("fields") or FIELDS
    return value if isinstance(value, str) else ",".join(str(part) for part in value)


#: The portal's own group codes. Anything unrecognised stays UNKNOWN rather
#: than being guessed into a category a rule might then filter on.
_CATEGORIES: dict[str, ProcurementCategory] = {
    "GO": ProcurementCategory.GOODS,
    "CW": ProcurementCategory.WORKS,
    "CS": ProcurementCategory.CONSULTING,
    "NC": ProcurementCategory.CONSULTING,
    "IC": ProcurementCategory.CONSULTING,
    "NN": ProcurementCategory.SERVICES,
}

#: A notice type that describes something already decided is not biddable.
_CLOSED_NOTICE_TYPES = frozenset({"contract award", "award notice", "cancellation notice"})

#: ISO codes for the countries this project actually deals with. The endpoint
#: returns names, and mapping only what we know keeps a wrong guess out of a
#: country-eligibility rule.
_COUNTRY_CODES: dict[str, str] = {
    "bangladesh": "BD",
    "india": "IN",
    "nepal": "NP",
    "sri lanka": "LK",
    "pakistan": "PK",
    "bhutan": "BT",
    "maldives": "MV",
    "afghanistan": "AF",
    "myanmar": "MM",
    "indonesia": "ID",
    "philippines": "PH",
    "vietnam": "VN",
    "kenya": "KE",
    "nigeria": "NG",
    "ethiopia": "ET",
    "tanzania": "TZ",
    "uganda": "UG",
    "ghana": "GH",
    "egypt": "EG",
    "morocco": "MA",
}


def _parse_date(value: Any) -> datetime | None:
    """The portal writes dates as `08-Sep-2026`, sometimes with a time."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    for fmt in ("%d-%b-%Y", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%d-%b-%Y %H:%M"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _html_to_text(value: Any) -> str | None:
    """`notice_text` is a block of HTML; the matcher wants prose."""
    if not value or not isinstance(value, str):
        return None
    text = HTMLParser(value).text(separator=" ", strip=True)
    return " ".join(text.split()) or None


def _country_code(name: Any) -> str | None:
    if not name or not isinstance(name, str):
        return None
    return _COUNTRY_CODES.get(name.strip().lower())


def _sector_names(value: Any) -> list[str]:
    """`sector` is a list of `{sector_code, sector_description}`."""
    if not isinstance(value, list):
        return []
    return [
        str(entry.get("sector_description"))
        for entry in value
        if isinstance(entry, dict) and entry.get("sector_description")
    ]


@register_adapter
class WorldBankAdapter:
    """Implements :class:`~app.ingestion.adapters.base.SourceAdapter`."""

    key = "worldbank"

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

    def _http(self) -> httpx.AsyncClient:
        return self._client or httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            headers={"User-Agent": settings.scraper_user_agent},
            follow_redirects=True,
        )

    def _params(self, offset: int) -> dict[str, Any]:
        return {
            "format": "json",
            "apilang": "en",
            "rows": int(self.config.get("rows", PAGE_SIZE)),
            "os": offset,
            "srt": "noticedate",
            "order": "desc",
            # Two spellings because the seeded configuration has always said
            # `fields` while this read `fl`, so the stored list was silently
            # ignored and every deployment quietly used the default below. The
            # portal's own parameter name is `fl`; `fields` is accepted so the
            # rows already in production mean what they appear to mean.
            "fl": _field_list(self.config),
        }

    async def list_notices(
        self,
        *,
        since: datetime | None = None,
        cursor: dict[str, Any] | None = None,
        limit_pages: int = 5,
    ) -> AsyncIterator[NoticeRef]:
        """Yield notices newest first.

        ``cursor`` may carry ``seen_ids``; iteration stops at the first one,
        because the endpoint's date filters cannot be trusted to do it for us.
        """
        seen: set[str] = set((cursor or {}).get("seen_ids") or [])
        rows_per_page = int(self.config.get("rows", PAGE_SIZE))
        client = self._http()
        owned = self._client is None

        try:
            for page in range(limit_pages):
                response = await client.get(
                    f"{self.base_url}{LISTING_PATH}", params=self._params(page * rows_per_page)
                )
                response.raise_for_status()
                payload = response.json()
                notices = payload.get("procnotices") or []
                if not notices:
                    return

                for row in notices:
                    external_id = str(row.get("id") or "").strip()
                    if not external_id:
                        continue
                    if external_id in seen:
                        logger.info("worldbank_reached_known_notice", notice_id=external_id)
                        return

                    published = _parse_date(row.get("noticedate"))
                    if since and published and published < since:
                        # Newest-first, so everything after this is older too.
                        return

                    yield NoticeRef(
                        external_id=external_id,
                        url=DETAIL_URL.format(id=external_id),
                        title=row.get("bid_description") or row.get("project_name"),
                        published_at=published,
                        deadline_at=_parse_date(row.get("submission_deadline_date")),
                        listing_data=row,
                    )
        finally:
            if owned:
                await client.aclose()

    async def fetch_detail(self, ref: NoticeRef) -> list[RawDocument]:
        """The listing row is the whole notice; there is nothing else to fetch.

        Stored anyway so `normalize` can be re-run offline over the bytes we
        actually saw, exactly as it can for a scraped portal.
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
        row: dict[str, Any] = dict(ref.listing_data)
        for document in documents:
            if document.kind is DocumentKind.API_JSON:
                row = json.loads(document.content.decode())
                break

        notice_type = str(row.get("notice_type") or "").strip()
        status = (
            TenderStatus.CLOSED
            if notice_type.lower() in _CLOSED_NOTICE_TYPES
            else TenderStatus.OPEN
        )
        description = _html_to_text(row.get("notice_text"))
        sectors = _sector_names(row.get("sector"))

        title = (
            row.get("bid_description")
            or row.get("project_name")
            or f"World Bank notice {row.get('id')}"
        )

        return TenderIn(
            external_id=str(row.get("id")),
            canonical_url=DETAIL_URL.format(id=row.get("id")),
            title=str(title)[:1000],
            summary=(
                f"{notice_type} for {row.get('project_name')}".strip()
                if row.get("project_name")
                else notice_type or None
            ),
            description=description,
            procuring_entity=row.get("contact_organization") or row.get("project_name"),
            country=_country_code(row.get("project_ctry_name")),
            procurement_method=row.get("procurement_method_name"),
            procurement_category=_CATEGORIES.get(
                str(row.get("procurement_group") or "").upper(),
                ProcurementCategory.UNKNOWN,
            ),
            published_at=_parse_date(row.get("noticedate")),
            deadline_at=_parse_date(row.get("submission_deadline_date")),
            status=status,
            language=(row.get("notice_lang_name") or "")[:10] or None,
            portal_metadata={
                "notice_type": notice_type,
                "notice_status": row.get("notice_status"),
                "project_id": row.get("project_id"),
                "project_name": row.get("project_name"),
                "project_country": row.get("project_ctry_name"),
                "bid_reference_no": row.get("bid_reference_no"),
                "procurement_group": row.get("procurement_group"),
                "sectors": sectors,
            },
        )

    async def healthcheck(self) -> SourceHealthReport:
        client = self._http()
        owned = self._client is None
        try:
            response = await client.get(
                f"{self.base_url}{LISTING_PATH}", params=self._params(0) | {"rows": 1}
            )
            response.raise_for_status()
            reachable = bool(response.json().get("procnotices"))
            return SourceHealthReport(
                reachable=reachable,
                detail=None if reachable else "Endpoint returned no notices.",
            )
        except Exception as exc:
            return SourceHealthReport(reachable=False, detail=str(exc)[:200])
        finally:
            if owned:
                await client.aclose()
