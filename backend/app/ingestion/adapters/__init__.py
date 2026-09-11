"""Portal adapters, and the one place that turns a source row into one.

Importing this package registers every adapter. That matters because
``ADAPTERS`` is populated by import side effect: a process that never imported
these modules sees an empty registry and concludes no portal is known, which
looks exactly like a misconfigured source. The API needs them for health probes
and adapter validation, the worker needs them to scrape, so registration belongs
here rather than in whichever entrypoint remembered to do it.

The Playwright fallback is registered too, but it imports Playwright only when
it is actually run — the slim worker image does not ship a browser.
"""

from __future__ import annotations

from typing import Any

# Imported for their registration side effect; `build_adapter` resolves by key.
from app.ingestion.adapters import adb as _adb  # noqa: F401
from app.ingestion.adapters import egp_bd as _egp_bd  # noqa: F401
from app.ingestion.adapters import egp_bd_playwright as _egp_bd_playwright  # noqa: F401
from app.ingestion.adapters import worldbank as _worldbank  # noqa: F401
from app.ingestion.adapters.base import (
    ADAPTERS,
    NoticeRef,
    RawDocument,
    SourceAdapter,
    SourceHealthReport,
    TenderIn,
    get_adapter_class,
    register_adapter,
)


def build_adapter(
    adapter_key: str, *, base_url: str | None = None, config: dict[str, Any] | None = None
) -> Any:
    """Instantiate the adapter a source names, with its stored configuration.

    An empty ``base_url`` is left out entirely rather than passed as ``None``,
    so the adapter keeps its own default instead of being handed nothing.
    """
    adapter_cls = get_adapter_class(adapter_key)
    kwargs: dict[str, Any] = {"config": dict(config or {})}
    if base_url:
        kwargs["base_url"] = base_url
    return adapter_cls(**kwargs)


__all__ = [
    "ADAPTERS",
    "NoticeRef",
    "RawDocument",
    "SourceAdapter",
    "SourceHealthReport",
    "TenderIn",
    "build_adapter",
    "get_adapter_class",
    "register_adapter",
]
