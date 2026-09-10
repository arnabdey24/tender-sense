# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv

WORKDIR /app

# Dependencies first so code edits do not invalidate the layer.
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY backend/ ./

# The API and the scrape worker are built from *different* base images and run
# as different users, but they share one blob volume. Docker fixes a named
# volume's ownership from whichever image mounts it first, so without a shared
# group the second one cannot write — and every scraped notice is lost with a
# permission error nobody sees. A fixed gid, plus setgid on the directory so
# files created by either user stay group-writable, is what keeps both working.
ARG BLOB_GID=10001

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev \
 && groupadd --system app && useradd --system --gid app --create-home app \
 && groupadd --gid ${BLOB_GID} tendersense \
 && usermod --append --groups tendersense app \
 && mkdir -p /var/lib/tendersense/blobs \
 && chown -R app:tendersense /var/lib/tendersense \
 && chmod -R 2775 /var/lib/tendersense \
 && chown -R app:app /app

USER app
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
