"""Retrying what is worth retrying, and nothing else."""

from __future__ import annotations

import httpx
import pytest

from app.ingestion.retry import retry_after_seconds, with_retry


def _response(status: int, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(
        status, headers=headers or {}, request=httpx.Request("GET", "https://example.invalid")
    )


class TestWhatIsRetried:
    async def test_a_timeout_is_weather_and_is_tried_again(self) -> None:
        calls = {"n": 0}

        async def flaky() -> str:
            calls["n"] += 1
            if calls["n"] < 3:
                raise httpx.ReadTimeout("")
            return "listing"

        assert await with_retry(flaky, attempts=3, base_delay=0) == "listing"
        assert calls["n"] == 3

    async def test_a_portal_pacing_us_is_tried_again(self) -> None:
        calls = {"n": 0}

        async def throttled() -> str:
            calls["n"] += 1
            if calls["n"] == 1:
                raise httpx.HTTPStatusError("", request=None, response=_response(429))  # type: ignore[arg-type]
            return "listing"

        assert await with_retry(throttled, attempts=3, base_delay=0) == "listing"

    async def test_a_clear_answer_is_not_argued_with(self) -> None:
        """A 404 is not a blip, and asking a 403 again is the worst available
        idea — it is how an address stops being answered at all."""
        calls = {"n": 0}

        async def refused() -> str:
            calls["n"] += 1
            raise httpx.HTTPStatusError("", request=None, response=_response(403))  # type: ignore[arg-type]

        with pytest.raises(httpx.HTTPStatusError):
            await with_retry(refused, attempts=3, base_delay=0)
        assert calls["n"] == 1

    async def test_a_portal_that_is_genuinely_down_still_fails(self) -> None:
        """The pass must still give up; retrying is not a way to never fail."""

        async def down() -> str:
            raise httpx.ConnectError("")

        with pytest.raises(httpx.ConnectError):
            await with_retry(down, attempts=2, base_delay=0)


class TestRetryAfter:
    async def test_the_portal_s_own_number_is_preferred(self) -> None:
        """It is the only figure in the exchange that reflects what the portal
        actually wants."""
        assert retry_after_seconds(_response(429, {"retry-after": "7"})) == 7.0

    async def test_an_http_date_is_not_guessed_at(self) -> None:
        assert (
            retry_after_seconds(_response(429, {"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"}))
            is None
        )

    async def test_no_header_means_back_off_on_our_own_schedule(self) -> None:
        assert retry_after_seconds(_response(503)) is None
