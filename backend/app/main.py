"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.middleware.sessions import SessionMiddleware

from app.api.v1 import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from app.core.observability import init_sentry

# Configures the full SQLAlchemy registry regardless of which routers are
# mounted, so cross-module foreign keys always resolve.
from app.db import models as _models  # noqa: F401
from app.db.session import dispose_engine
from app.jobs.queue import close_queue

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    init_sentry("api")
    logger.info("api_starting", environment=settings.environment)
    yield
    await close_queue()
    await dispose_engine()
    logger.info("api_stopped")


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title=settings.project_name,
        version=settings.release or "1.10.0",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url=None,
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Starlette runs middleware in reverse registration order, so these two are
    # added first to sit outermost: every response gets its headers and its
    # request id, including ones an inner middleware short-circuits.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)

    # Short-lived signed cookie holding only the OAuth state and nonce during a
    # Google sign-in round trip. It is not the application session.
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key.get_secret_value(),
        session_cookie="ts_oauth",
        max_age=600,
        same_site="lax",
        https_only=settings.refresh_cookie_secure,
    )

    if settings.backend_cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.backend_cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    if settings.metrics_enabled:
        # Business metrics are registered by importing the module above; this
        # adds the HTTP ones and the scrape endpoint that serves both.
        Instrumentator(
            should_group_status_codes=True,
            excluded_handlers=["/metrics", "/api/v1/health/live"],
        ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

    return app


app = create_app()
