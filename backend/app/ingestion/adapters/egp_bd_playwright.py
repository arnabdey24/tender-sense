"""e-GP Bangladesh, driven through a real browser.

This exists for one scenario: the servlet the primary adapter posts to starts
refusing plain HTTP clients. That has not happened, and the day it does is the
worst possible day to start writing a browser adapter — so the shape is here,
tested where it can be, and switching to it is a `adapter_key` edit on the
source row rather than a deploy.

Two decisions keep it honest:

**Parsing is not duplicated.** ``normalize`` and the listing/detail parsers are
imported from the HTTP adapter rather than reimplemented. The reason to reach
for a browser is that the *transport* was blocked; the markup is the same markup,
and two copies of it would drift the moment one is fixed.

**Playwright is imported inside the methods that use it.** The default worker
image has no browser and no ``playwright`` package, and a module-level import
would make the whole adapter registry fail to load there — taking the working
HTTP adapter down with it.

Enabling it: install the extra (``uv sync --extra scrape``), run
``playwright install --with-deps chromium`` in the scrape image, then point the
source at it::

    PATCH /api/v1/admin/sources/{id}  {"adapter_key": "egp_bd_playwright"}
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import TYPE_CHECKING, Any

from app.core.config import settings
from app.core.logging import get_logger
from app.ingestion.adapters.base import (
    NoticeRef,
    RawDocument,
    SourceHealthReport,
    TenderIn,
    register_adapter,
)
from app.ingestion.adapters.egp_bd import (
    BASE_URL,
    DETAIL_PATH,
    LISTING_PATH,
    EgpBdAdapter,
    parse_datetime,
    parse_listing,
)
from app.modules.tenders.models import DocumentKind

if TYPE_CHECKING:  # pragma: no cover - typing only
    from playwright.async_api import Browser, Page

logger = get_logger(__name__)

#: The servlet renders server-side, so there is no XHR to wait for beyond load.
LOAD_STATE = "domcontentloaded"
NAVIGATION_TIMEOUT_MS = 60_000


class PlaywrightUnavailableError(RuntimeError):
    """Playwright is not installed in this image."""


@register_adapter
class EgpBdPlaywrightAdapter:
    """Implements :class:`~app.ingestion.adapters.base.SourceAdapter`.

    A drop-in replacement for :class:`~app.ingestion.adapters.egp_bd.EgpBdAdapter`
    that fetches through Chromium instead of httpx.
    """

    key = "egp_bd_playwright"

    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        config: dict[str, Any] | None = None,
        browser: Browser | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.config = config or {}
        #: Injected in tests; otherwise one is launched per operation.
        self._browser = browser
        self.delay = float(
            self.config.get("request_delay_seconds", settings.scraper_request_delay_seconds)
        )
        #: Parsing, date handling and normalisation are the HTTP adapter's.
        self._http_adapter = EgpBdAdapter(base_url=base_url, config=self.config)

    # -- browser lifecycle ---------------------------------------------------

    @asynccontextmanager
    async def _page(self) -> AsyncIterator[Page]:
        """A page in a fresh context, on an injected or freshly launched browser."""
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:  # pragma: no cover - depends on the image
            raise PlaywrightUnavailableError(
                "The egp_bd_playwright adapter needs the 'scrape' extra: "
                "uv sync --extra scrape && playwright install --with-deps chromium"
            ) from exc

        if self._browser is not None:
            context = await self._browser.new_context(user_agent=settings.scraper_user_agent)
            try:
                yield await context.new_page()
            finally:
                await context.close()
            return

        async with async_playwright() as driver:
            browser = await driver.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=settings.scraper_user_agent)
            try:
                yield await context.new_page()
            finally:
                await context.close()
                await browser.close()

    async def _be_polite(self) -> None:
        if self.delay > 0:
            await asyncio.sleep(self.delay)

    async def _listing_html(self, page: Page, page_no: int, since: datetime | None) -> str:
        """Submit the servlet's form from inside the page.

        Posting the form through the page rather than fetching a URL is the
        whole point: the request then carries the session cookies, referer and
        headers a browser would send, which is what a transport block rejects
        a bare client for.
        """
        form = self._http_adapter.listing_form(page_no, since)
        return str(
            await page.evaluate(
                """
                async ({url, form}) => {
                    const body = new URLSearchParams(form).toString();
                    const response = await fetch(url, {
                        method: "POST",
                        headers: {"Content-Type": "application/x-www-form-urlencoded"},
                        body,
                        credentials: "include",
                    });
                    return await response.text();
                }
                """,
                {"url": f"{self.base_url}{LISTING_PATH}", "form": form},
            )
        )

    # -- adapter contract ----------------------------------------------------

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

        async with self._page() as page:
            page.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)
            # Land on the portal first so the servlet call carries a session.
            await page.goto(f"{self.base_url}/", wait_until=LOAD_STATE)

            page_no = 1
            total_pages = 1
            while page_no <= min(max_pages, total_pages):
                if page_no > 1:
                    await self._be_polite()
                rows, total_pages = parse_listing(await self._listing_html(page, page_no, since))
                if not rows:
                    return

                for row in rows:
                    identifier = row["id"]
                    if identifier in seen:
                        logger.info("egp_bd_pw_reached_known_notice", notice_id=identifier)
                        return
                    yield NoticeRef(
                        external_id=identifier,
                        url=f"{self.base_url}{DETAIL_PATH}?id={identifier}",
                        title=row.get("title"),
                        published_at=parse_datetime(row.get("published_at", "")),
                        deadline_at=parse_datetime(row.get("closing_at", "")),
                        listing_data=row,
                    )
                page_no += 1

    async def fetch_detail(self, ref: NoticeRef) -> list[RawDocument]:
        """Open the detail page and keep its rendered HTML beside the listing row."""
        documents = [self._http_adapter.listing_document(ref)]

        try:
            async with self._page() as page:
                page.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)
                await self._be_polite()
                url = f"{self.base_url}{DETAIL_PATH}?id={ref.external_id}&h=t"
                await page.goto(url, wait_until=LOAD_STATE)
                documents.append(
                    RawDocument(
                        kind=DocumentKind.DETAIL_HTML,
                        content=(await page.content()).encode(),
                        url=url,
                        content_type="text/html",
                    )
                )
        except Exception as exc:
            # As in the HTTP adapter: a missing detail page is not a lost
            # notice, because the listing row alone is enough to match on.
            logger.warning(
                "egp_bd_pw_detail_failed", notice_id=ref.external_id, error=str(exc)[:200]
            )

        return documents

    def normalize(self, ref: NoticeRef, documents: list[RawDocument]) -> TenderIn:
        """Delegated: the markup is the same markup, so the parser is the same parser."""
        return self._http_adapter.normalize(ref, documents)

    async def healthcheck(self) -> SourceHealthReport:
        try:
            async with self._page() as page:
                page.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)
                await page.goto(f"{self.base_url}/", wait_until=LOAD_STATE)
                rows, _ = parse_listing(await self._listing_html(page, 1, None))
            return SourceHealthReport(
                reachable=bool(rows),
                detail=None if rows else "The servlet returned no rows.",
            )
        except PlaywrightUnavailableError as exc:
            return SourceHealthReport(reachable=False, detail=str(exc))
        except Exception as exc:
            return SourceHealthReport(reachable=False, detail=str(exc)[:200])
