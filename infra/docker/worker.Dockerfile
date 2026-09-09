# syntax=docker/dockerfile:1
# Worker image with Playwright browsers, used by the scrape worker and available
# as a fallback ingestion path for portals that block plain HTTP clients.
FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv

WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev --extra scrape

COPY backend/ ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra scrape \
 && mkdir -p /var/lib/tendersense/blobs && chown -R pwuser:pwuser /var/lib/tendersense /app

USER pwuser

CMD ["arq", "app.jobs.worker.ScrapeWorkerSettings"]
