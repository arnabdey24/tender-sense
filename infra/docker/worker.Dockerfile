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

# The API and the scrape worker are built from *different* base images and run
# as different users, but they share one blob volume. Docker fixes a named
# volume's ownership from whichever image mounts it first, so without a shared
# group the second one cannot write — and every scraped notice is lost with a
# permission error nobody sees. A fixed gid, plus setgid on the directory so
# files created by either user stay group-writable, is what keeps both working.
ARG BLOB_GID=10001

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra scrape \
 && groupadd --gid ${BLOB_GID} tendersense \
 && usermod --append --groups tendersense pwuser \
 && mkdir -p /var/lib/tendersense/blobs \
 && chown -R pwuser:tendersense /var/lib/tendersense \
 && chmod -R 2775 /var/lib/tendersense \
 && chown -R pwuser:pwuser /app

USER pwuser

CMD ["arq", "app.jobs.worker.ScrapeWorkerSettings"]
