"""Cross-cutting HTTP concerns: request identity and browser hardening.

Both are the kind of thing that is invisible until it is missing. A request id
turns "a customer says it failed at about four" into one log line; the security
headers turn a stored-XSS bug from a session theft into a rendering glitch.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings
from app.core.ids import new_id

REQUEST_ID_HEADER = "X-Request-ID"

#: Sent on every response. The API returns JSON and the SPA is served by Caddy,
#: so these are cheap here and belong on both — a header the proxy forgets is a
#: header nobody notices missing.
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    # The API serves no HTML and no scripts, so the strictest policy that
    # exists is also the correct one for it.
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}

#: A year, with subdomains, preloadable. Only sent over HTTPS in production:
#: sending it from a plain-HTTP development server would pin localhost to
#: HTTPS in the developer's browser for a year.
HSTS = "max-age=31536000; includeSubDomains"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a request id to the response, the logs and any Sentry event.

    An id the caller supplied is honoured, so a trace started at the proxy or
    in the SPA survives into the backend logs.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(new_id())
        request.state.request_id = request_id

        structlog.contextvars.bind_contextvars(request_id=request_id)
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars("request_id")

        response.headers[REQUEST_ID_HEADER] = request_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        if settings.is_production:
            response.headers.setdefault("Strict-Transport-Security", HSTS)
        return response
