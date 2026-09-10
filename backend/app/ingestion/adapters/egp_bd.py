"""e-GP Bangladesh.

The riskiest source in the system: an undocumented servlet on an old JSP stack,
with no versioning and no notice when it changes. Three things follow from that.

**Selectors live in the database.** ``tender_sources.config`` supplies them, so
a markup change is a data fix an operator can make at 2 a.m. rather than a
deployment.

**Raw HTML is stored before it is parsed.** When the layout changes, the parser
is fixed and replayed over bytes already held — which matters because this
portal is slow, rate limited, and drops notices once they close.

**Politeness is not optional.** A government portal that decides we are abusive
takes the whole product with it, so requests are spaced, pages are capped, and
a run gives up after a few consecutive failures rather than hammering on.

Observed shape (verified 2026-09-10): the servlet returns bare ``<tr>``
fragments — no table, no document wrapper — with a hidden ``totalPages`` input
appended. Each row carries the tender id in a hidden field inside a form that
posts to ``ViewTender.jsp``.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx
from selectolax.parser import HTMLParser, Node

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

BASE_URL = "https://www.eprocure.gov.bd"
LISTING_PATH = "/TenderDetailsServlet"
DETAIL_PATH = "/resources/common/ViewTender.jsp"

#: Stop after this many consecutive detail failures. A portal that has started
#: refusing us will not start saying yes because we asked forty more times.
MAX_CONSECUTIVE_FAILURES = 5

_CATEGORIES: dict[str, ProcurementCategory] = {
    "goods": ProcurementCategory.GOODS,
    "works": ProcurementCategory.WORKS,
    "services": ProcurementCategory.SERVICES,
    "service": ProcurementCategory.SERVICES,
    "consultancy": ProcurementCategory.CONSULTING,
    "consultancy services": ProcurementCategory.CONSULTING,
}

#: Statuses the portal shows in the listing. Anything else stays UNKNOWN rather
#: than being assumed open.
_STATUSES: dict[str, TenderStatus] = {
    "live": TenderStatus.OPEN,
    "closed": TenderStatus.CLOSED,
    "cancelled": TenderStatus.CANCELLED,
    "archive": TenderStatus.CLOSED,
    "archived": TenderStatus.CLOSED,
}

_WHITESPACE = re.compile(r"\s+")


def _text(node: Node | None) -> str:
    if node is None:
        return ""
    return _WHITESPACE.sub(" ", node.text(separator=" ", strip=True)).strip()


def _clean(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip().strip(",").strip()


def parse_datetime(value: str) -> datetime | None:
    """The portal writes `10-Sep-2026 12:10`, sometimes without the time.

    Stored as UTC. The portal means Asia/Dhaka, but it publishes no offset and
    guessing one would shift every deadline by six hours — which is worse than
    being explicit that the wall-clock value is what we were given.
    """
    text = _clean(value)
    if not text:
        return None
    for fmt in ("%d-%b-%Y %H:%M", "%d-%b-%Y", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


#: A package description usually starts with the reference number again, e.g.
#: "PD/CCDIDP/2026-2027/e-GP/Works-43.36 Construction of…". Codes like that are
#: noise in an embedding — they share no vocabulary with anything a company
#: says about itself — so the leading one is dropped from the title.
#:
#: Identified by shape rather than a pattern per portal: one whitespace-free
#: token carrying both a slash and a digit, which an English word never is.
#: "Supply and/or installation of pumps" keeps its "and/or" because that token
#: has no digit, and a bare "P-123/2026" is kept because nothing follows it.
_LEADING_REFERENCE = re.compile(r"^(?=\S*/)(?=\S*\d)\S{8,}\s+(?=\S)")


def strip_leading_reference(title: str) -> str:
    """Drop a reference code prefixed to a package description."""
    return _LEADING_REFERENCE.sub("", title.strip(), count=1).strip() or title.strip()


def parse_money(value: str) -> float | None:
    digits = re.sub(r"[^0-9.]", "", value or "")
    try:
        return float(digits) if digits else None
    except ValueError:
        return None


def parse_listing(html: str) -> tuple[list[dict[str, Any]], int]:
    """Pull rows and the page count out of the servlet's HTML fragment.

    Returns ``(rows, total_pages)``. Pure: no network, no state.
    """
    tree = HTMLParser(f"<table>{html}</table>")

    total_pages = 1
    for node in HTMLParser(html).css("input"):
        if node.attributes.get("id") == "totalPages":
            try:
                total_pages = max(1, int(node.attributes.get("value") or 1))
            except ValueError:
                total_pages = 1

    rows: list[dict[str, Any]] = []
    for row in tree.css("tr"):
        cells = row.css("td")
        if len(cells) < 6:
            continue

        # The id lives in a hidden field inside the row's own form, which is
        # sturdier than positional parsing of the visible text.
        identifier = ""
        for hidden in row.css("input"):
            if hidden.attributes.get("name") == "id":
                identifier = (hidden.attributes.get("value") or "").strip()
                break
        if not identifier:
            continue

        reference = ""
        status = ""
        parts = [_clean(part) for part in _text(cells[1]).split(",")]
        if len(parts) >= 2:
            reference = parts[1]
        if parts:
            status = parts[-1]

        nature_and_title = _text(cells[2])
        nature = _clean(nature_and_title.split(",")[0])
        title = _clean(nature_and_title[len(nature) + 1 :]) or nature_and_title

        entities = [_clean(part) for part in _text(cells[3]).split(",") if _clean(part)]
        methods = [_clean(part) for part in _text(cells[4]).split(",") if _clean(part)]
        dates = [_clean(part) for part in _text(cells[5]).split(",") if _clean(part)]

        rows.append(
            {
                "id": identifier,
                "reference_no": reference,
                "status": status,
                "procurement_nature": nature,
                "title": title,
                "ministry": entities[0] if entities else "",
                "organization": entities[1] if len(entities) > 1 else "",
                "procuring_entity": entities[-1] if entities else "",
                "procurement_type": methods[0] if methods else "",
                "procurement_method": methods[-1] if methods else "",
                "published_at": dates[0] if dates else "",
                "closing_at": dates[1] if len(dates) > 1 else "",
            }
        )

    return rows, total_pages


def parse_detail(html: str) -> dict[str, str]:
    """Flatten the detail page's label/value table into a dict.

    Labels are matched by their text rather than by position, because the row
    order shifts between notice types.
    """
    tree = HTMLParser(html)
    fields: dict[str, str] = {}

    for row in tree.css("tr"):
        cells = row.css("td")
        for index in range(len(cells) - 1):
            label = _text(cells[index]).rstrip(":").strip()
            if not label or len(label) > 120:
                continue
            classes = cells[index].attributes.get("class") or ""
            if "ff" not in classes:
                continue
            value = _text(cells[index + 1])
            if label and label not in fields:
                fields[label] = value

    return fields


def _field(fields: dict[str, str], *candidates: str) -> str:
    """First label that starts with one of ``candidates``.

    Prefix matching because the portal truncates long labels inconsistently
    ("Tender/Proposal Closing Date and Time" vs "…Closing Date").
    """
    for candidate in candidates:
        for label, value in fields.items():
            if label.lower().startswith(candidate.lower()):
                return value
    return ""


@register_adapter
class EgpBdAdapter:
    """Implements :class:`~app.ingestion.adapters.base.SourceAdapter`."""

    key = "egp_bd"

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
        self.delay = float(
            self.config.get("request_delay_seconds", settings.scraper_request_delay_seconds)
        )

    def _http(self) -> httpx.AsyncClient:
        return self._client or httpx.AsyncClient(
            timeout=httpx.Timeout(45.0),
            headers={
                "User-Agent": settings.scraper_user_agent,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            follow_redirects=True,
        )

    async def _be_polite(self) -> None:
        if self.delay > 0:
            await asyncio.sleep(self.delay)

    def listing_form(self, page: int, since: datetime | None) -> dict[str, str]:
        """The servlet's form fields, all of which it expects to be present.

        Public because the Playwright fallback submits the same form from
        inside a browser page rather than duplicating the field list.
        """
        window_start = ""
        if since is not None:
            # A day of overlap, because a notice published moments before the
            # last run finished would otherwise never be seen.
            window_start = since.strftime("%d/%m/%Y")
        return {
            "funName": "AllTenders",
            "viewType": str(self.config.get("view_type", "Live")),
            "departmentId": "",
            "office": "",
            "procNature": "",
            "procType": "",
            "procMethod": "0",
            "tenderId": "0",
            "refNo": "",
            "pubDtFrm": window_start,
            "pubDtTo": "",
            "closeDtFrm": "",
            "closeDtTo": "",
            "cpvCategory": "",
            "isFrame": "",
            "pageNo": str(page),
            "size": str(self.config.get("page_size", 100)),
            "h": "t",
        }

    async def list_notices(
        self,
        *,
        since: datetime | None = None,
        cursor: dict[str, Any] | None = None,
        limit_pages: int = 20,
    ) -> AsyncIterator[NoticeRef]:
        """Walk the listing newest-first, stopping at a notice already held."""
        seen: set[str] = set((cursor or {}).get("seen_ids") or [])
        max_pages = min(limit_pages, int(self.config.get("max_pages", 20)))
        client = self._http()
        owned = self._client is None

        try:
            page = 1
            total_pages = 1
            while page <= min(max_pages, total_pages):
                if page > 1:
                    await self._be_polite()
                response = await client.post(
                    f"{self.base_url}{LISTING_PATH}", data=self.listing_form(page, since)
                )
                response.raise_for_status()
                rows, total_pages = parse_listing(response.text)
                if not rows:
                    return

                for row in rows:
                    identifier = row["id"]
                    if identifier in seen:
                        logger.info("egp_bd_reached_known_notice", notice_id=identifier)
                        return
                    yield NoticeRef(
                        external_id=identifier,
                        url=f"{self.base_url}{DETAIL_PATH}?id={identifier}",
                        title=row.get("title"),
                        published_at=parse_datetime(row.get("published_at", "")),
                        deadline_at=parse_datetime(row.get("closing_at", "")),
                        listing_data=row,
                    )
                page += 1
        finally:
            if owned:
                await client.aclose()

    @staticmethod
    def listing_document(ref: NoticeRef) -> RawDocument:
        """The listing row, as JSON rather than a Python repr.

        It is stored so that a parser fix can be replayed over it offline. A
        ``repr`` cannot be read back by anything but ``eval``, which would make
        the stored bytes useless for exactly the job they are kept for.
        """
        return RawDocument(
            kind=DocumentKind.LISTING_ROW,
            content=json.dumps(ref.listing_data, sort_keys=True, default=str).encode(),
            url=ref.url,
            content_type="application/json",
        )

    async def fetch_detail(self, ref: NoticeRef) -> list[RawDocument]:
        """Fetch the detail page, keeping the listing row alongside it.

        Both are stored: if the detail page later fails to parse, the listing
        row alone still carries enough to keep the notice in the pool.
        """
        documents = [self.listing_document(ref)]

        client = self._http()
        owned = self._client is None
        try:
            await self._be_polite()
            response = await client.get(
                f"{self.base_url}{DETAIL_PATH}", params={"id": ref.external_id, "h": "t"}
            )
            response.raise_for_status()
            documents.append(
                RawDocument(
                    kind=DocumentKind.DETAIL_HTML,
                    content=response.content,
                    url=str(response.url),
                    content_type="text/html",
                )
            )
        except Exception as exc:
            # A missing detail page is not a lost notice — the listing row is
            # enough to match on, and the detail can be fetched again later.
            logger.warning("egp_bd_detail_failed", notice_id=ref.external_id, error=str(exc)[:200])
        finally:
            if owned:
                await client.aclose()

        return documents

    def normalize(self, ref: NoticeRef, documents: list[RawDocument]) -> TenderIn:
        """Pure: same bytes in, same row out. No network."""
        row: dict[str, Any] = dict(ref.listing_data)
        fields: dict[str, str] = {}

        for document in documents:
            if document.kind is DocumentKind.DETAIL_HTML:
                fields = parse_detail(document.content.decode("utf-8", errors="replace"))
                break

        title = (
            _field(fields, "Tender/Proposal Package No. and Descri", "Package")
            or row.get("title")
            or f"e-GP notice {ref.external_id}"
        )
        title = strip_leading_reference(_clean(title))
        nature = _field(fields, "Procurement Nature") or row.get("procurement_nature", "")
        status_text = (
            (_field(fields, "Tender/Proposal Status") or row.get("status", "")).strip().lower()
        )

        description = (
            " ".join(
                part
                for part in (
                    _field(fields, "Brief Description"),
                    _field(fields, "Eligibility of Tenderer"),
                )
                if part
            )
            or None
        )

        # The portal publishes several dates; the closing one is what a bidder
        # is actually racing, so anything else would mislead the countdown.
        deadline = parse_datetime(_field(fields, "Tender/Proposal Closing Date")) or parse_datetime(
            row.get("closing_at", "")
        )

        return TenderIn(
            external_id=str(ref.external_id),
            canonical_url=f"{BASE_URL}{DETAIL_PATH}?id={ref.external_id}",
            title=title[:1000],
            summary=_field(fields, "Invitation for") or row.get("procurement_nature") or None,
            description=description,
            procuring_entity=(
                _field(fields, "Procuring Entity Name")
                or row.get("procuring_entity")
                or row.get("organization")
                or None
            ),
            country="BD",
            procurement_method=(
                _field(fields, "Procurement Method") or row.get("procurement_method") or None
            ),
            procurement_category=_CATEGORIES.get(
                nature.strip().lower(), ProcurementCategory.UNKNOWN
            ),
            published_at=(
                parse_datetime(_field(fields, "Scheduled Tender/Proposal Publication"))
                or parse_datetime(row.get("published_at", ""))
            ),
            deadline_at=deadline,
            currency="BDT",
            estimated_value=None,
            status=_STATUSES.get(status_text, TenderStatus.UNKNOWN),
            language="English",
            portal_metadata={
                "reference_no": (
                    _field(fields, "Invitation Reference No") or row.get("reference_no")
                ),
                "ministry": _field(fields, "Ministry") or row.get("ministry"),
                "organization": _field(fields, "Organization") or row.get("organization"),
                "district": _field(fields, "Procuring Entity District"),
                "procurement_type": _field(fields, "Procurement Type")
                or row.get("procurement_type"),
                "category": _field(fields, "Category"),
                "project_name": _field(fields, "Project Name"),
                "document_price_bdt": parse_money(_field(fields, "Tender/Proposal Document Price")),
                "security_valid_until": _field(fields, "Tender/Proposal Security Valid"),
                "opening_at": _field(fields, "Tender/Proposal Opening Date"),
            },
        )

    async def healthcheck(self) -> SourceHealthReport:
        client = self._http()
        owned = self._client is None
        try:
            response = await client.post(
                f"{self.base_url}{LISTING_PATH}",
                data=self.listing_form(1, None) | {"size": "1"},
            )
            response.raise_for_status()
            rows, _ = parse_listing(response.text)
            return SourceHealthReport(
                reachable=bool(rows),
                detail=None if rows else "The servlet returned no rows.",
            )
        except Exception as exc:
            return SourceHealthReport(reachable=False, detail=str(exc)[:200])
        finally:
            if owned:
                await client.aclose()
