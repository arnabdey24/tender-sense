"""Error reporting and the metrics the product is actually judged on.

Two things live here.

**Sentry**, initialised once per process and silent when no DSN is set, so a
development machine never ships an exception anywhere. Events are scrubbed
before they leave: this application handles password reset tokens, invitation
tokens and Gemini keys, and an unredacted breadcrumb would put one of them in a
third-party dashboard permanently.

**Business metrics**, alongside the HTTP metrics the instrumentator already
collects. Request latency says whether the API is up; it says nothing about
whether tenders are being ingested, matched, explained or delivered — which is
the only question that matters at three in the morning.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from prometheus_client import Counter, Gauge, Histogram

from app.core.config import settings
from app.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sentry_sdk.types import Event, Hint

logger = get_logger(__name__)

#: Query-string and header keys whose values must never leave the process.
SENSITIVE_KEYS = frozenset(
    {
        "token",
        "password",
        "secret",
        "authorization",
        "cookie",
        "set-cookie",
        "api_key",
        "apikey",
        "gemini_api_key",
        "secret_key",
        "access_token",
        "refresh_token",
        "client_secret",
    }
)

REDACTED = "[redacted]"


# --- metrics -------------------------------------------------------------

tenders_ingested = Counter(
    "tendersense_tenders_ingested_total",
    "Notices upserted into the shared pool.",
    ["source", "outcome"],
)

matches_scored = Counter(
    "tendersense_matches_scored_total",
    "Per-tenant verdicts written.",
    ["grade"],
)

notifications_queued = Counter(
    "tendersense_notifications_queued_total",
    "Messages placed in the outbox.",
    ["type"],
)

emails_delivered = Counter(
    "tendersense_emails_total",
    "Outbox rows the pump finished with.",
    ["outcome"],
)

ai_tokens_spent = Counter(
    "tendersense_ai_tokens_total",
    "Model tokens consumed, by purpose.",
    ["purpose"],
)

job_duration = Histogram(
    "tendersense_job_duration_seconds",
    "Background task wall time.",
    ["job", "status"],
    buckets=(0.1, 0.5, 1, 5, 15, 60, 300, 900),
)

source_health = Gauge(
    "tendersense_source_health",
    "1 healthy, 0.5 degraded, 0 down — per ingestion source.",
    ["source"],
)

#: The gauge only means anything if something keeps it current.
HEALTH_VALUES = {"ok": 1.0, "degraded": 0.5, "down": 0.0}


def record_source_health(code: str, health: str) -> None:
    source_health.labels(source=code).set(HEALTH_VALUES.get(health, 0.0))


# --- sentry --------------------------------------------------------------


def _scrub(value: Any) -> Any:
    """Recursively redact anything whose key looks like a credential."""
    if isinstance(value, dict):
        return {
            key: (REDACTED if str(key).lower() in SENSITIVE_KEYS else _scrub(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    return value


def before_send(event: Event, _hint: Hint) -> Event | None:
    """Strip credentials from an event before it leaves the process.

    Sentry's own default scrubbing covers common header names; this covers the
    ones specific to this application — verification and invitation tokens ride
    in query strings, and a leaked one is a working account takeover.
    """
    request = event.get("request")
    if isinstance(request, dict):
        request["headers"] = _scrub(request.get("headers") or {})
        request["cookies"] = REDACTED if request.get("cookies") else None
        query = request.get("query_string")
        if isinstance(query, str) and any(key in query.lower() for key in SENSITIVE_KEYS):
            request["query_string"] = REDACTED
        event["request"] = request

    for context in ("extra", "contexts"):
        if isinstance(event.get(context), dict):
            event[context] = _scrub(event[context])
    return event


def init_sentry(component: str) -> bool:
    """Start error reporting for this process. Returns whether it was enabled.

    A missing DSN is the normal case in development, so it is a debug line
    rather than a warning — an install that logs a warning on every start
    teaches people to ignore warnings.
    """
    if not settings.sentry_dsn:
        logger.debug("sentry_disabled", component=component)
        return False

    try:
        import sentry_sdk
    except ImportError:  # pragma: no cover - depends on the image
        logger.warning("sentry_sdk_missing", component=component)
        return False

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        release=settings.release,
        # Traces are sampled, errors are not: a slow endpoint is a statistic,
        # a 500 is an incident.
        traces_sample_rate=settings.sentry_traces_sample_rate,
        # Bodies can carry a password or a whole tender payload.
        max_request_body_size="never",
        send_default_pii=False,
        before_send=before_send,
    )
    sentry_sdk.set_tag("component", component)
    logger.info("sentry_enabled", component=component, environment=settings.environment)
    return True
