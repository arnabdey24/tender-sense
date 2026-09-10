# TenderSense

Tender discovery and matching for bidding teams. TenderSense watches public
procurement portals, matches every new tender against a company's capability
profile by meaning rather than keywords, applies that company's hard eligibility
rules, and delivers a ranked, explained shortlist by email and in the app.

Built as a multi-tenant SaaS: a company registers, sets up its profile, bidding
criteria and notification recipients, and receives matches from then on.

## Stack

| Layer | Choice |
|---|---|
| API | FastAPI (Python 3.12), SQLAlchemy 2 async, Alembic |
| Database | PostgreSQL 17 with pgvector, citext, pg_trgm |
| Jobs | ARQ on Redis (default queue plus an isolated scrape queue) |
| AI | Google Gemini (embeddings for matching, Flash-Lite for extraction and explanations) |
| Frontend | Vite, React, TypeScript, shadcn/ui, TanStack Router and Query |
| Delivery | Docker Compose behind Caddy |

## Quick start

Requires Docker, and for local backend work `uv` plus Node 22.

```bash
make dev      # writes .env with a generated SECRET_KEY, builds and starts everything
make ps       # container status
make logs     # tail logs, S=api to filter one service
```

Once the stack is up:

| What | Where |
|---|---|
| App (through Caddy) | http://localhost:8080 |
| API docs | http://localhost:8000/docs |
| Health probe | http://localhost:8000/api/v1/health/ready |
| Prometheus metrics | http://localhost:8000/metrics |
| Mailpit inbox | http://localhost:8025 |
| Vite dev server | http://localhost:5173 after `make fe-dev` |

Sign in as a superuser to reach `/admin` — background job runs, the mail queue
and model spend. Ordinary members see portal health under Settings → Sources.

If any of those ports is already taken on your machine, change `API_PORT_HOST`,
`HTTP_PORT` or `HTTPS_PORT` in `.env`. When you move the API, point the Vite dev
proxy at it with `VITE_API_PROXY_TARGET` in `frontend/.env.local`.

`AI_PROVIDER=fake` in `.env` runs the whole pipeline offline with deterministic
stubs, so no Gemini key is needed for development. Set `AI_PROVIDER=gemini` and
`GEMINI_API_KEY` for real matching.

## Working on the backend

```bash
make install                 # uv sync
make lint                    # ruff check, ruff format --check, mypy
make test                    # unit tests
make test-all                # adds integration tests (needs Postgres and Redis)
make migration M="add users" # autogenerate a migration
make migrate                 # apply migrations
make bench                   # time the pipeline against the <60s/tender budget
```

Integration tests skip themselves when Postgres or Redis is unreachable. To run
them against the compose stack from your host:

```bash
cd backend
POSTGRES_HOST=localhost REDIS_HOST=localhost uv run pytest
```

## Working on the frontend

```bash
make fe-install
make fe-dev      # http://localhost:5173, proxies /api to the API
make fe-test
make fe-types    # regenerate the typed client from the running API's OpenAPI document
```

## Layout

```
backend/app/core        settings, logging, errors, auth primitives
backend/app/db          engine, session, declarative base
backend/app/ai          Gemini client, embeddings, extraction, explanations
backend/app/jobs        ARQ queue, worker settings, scheduled tasks
backend/app/ingestion   portal adapters and the shared upsert path
backend/app/modules     one vertical slice per domain (router, schemas, models, service)
frontend/src/routes     file-based routes; pages stay thin
frontend/src/features   domain UI, hooks and schemas
infra/                  Dockerfiles, Caddy, Postgres bootstrap
```

## Deployment

One VM running the compose stack:

```bash
cp .env.example .env      # set SECRET_KEY, DOMAIN, SMTP and Gemini credentials
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Setting `DOMAIN` is what turns TLS on: Caddy obtains and renews the certificate
itself. The production overlay publishes only ports 80 and 443 — Postgres and
Redis stay on the compose network, because a mapped database port on a single
VM is reachable from the internet the moment it exists.

```bash
make backup               # database dump + blob archive into ./backups
```

Back both up: the database holds the accounts and decisions, and the blob volume
holds raw portal payloads, which for many closed notices is the only copy left
anywhere — and the only thing that makes a broken parser fixable after the fact.

**[docs/RUNBOOK.md](docs/RUNBOOK.md)** covers the rest: what to check when a
portal goes quiet, why mail is not arriving, how to restore a backup, which
metrics are worth alerting on, and what is safe to restart.

Caddy terminates TLS for `DOMAIN` automatically. Outbound email needs SPF and
DKIM configured for the sending domain.

## Documentation

| Document | What it covers |
|---|---|
| `docs/IMPLEMENTATION_PLAN.md` | Architecture, data model, matching pipeline, milestones. Start here. |
| `docs/TenderSense_BRD.pdf` | The original business requirements document. |
