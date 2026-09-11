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
| Vite dev server | http://localhost:5173 after `make fe-dev` |

### Platform staff

`/admin` is the operations console: what is failing right now, the portals and
their configuration, every tenant and account, background job runs, the mail
queue, model spend, and the rate limits the deployment runs under. It is staff
only — `is_superuser`, which is *platform* staff and has nothing to do with
being an admin of an organization.

The first one has to be made from the command line, because there is nobody to
grant it yet:

```bash
make superuser EMAIL=you@example.com
```

That creates the account, marks it verified so it can sign in straight away, and
prints a generated password **once**. Store it then; it is not recoverable, and
it is worth changing after the first sign-in.

Running it again on an address that already exists **promotes** that account
instead, and deliberately leaves its password alone — granting a colleague staff
access must not lock them out of the account they are signed in to. Reactivating
a suspended account and marking an unverified one verified are part of the grant,
because staff who cannot sign in are not staff.

```bash
make superuser EMAIL=colleague@example.com                      # promote
make superuser EMAIL=you@example.com ARGS="--reset-password"    # new password
make superuser EMAIL=you@example.com ARGS="--password '...'"    # choose one
```

On a deployed VM, where there is no `make`:

```bash
docker compose run --rm api python -m scripts.create_superuser --email you@example.com
```

After the first one exists, everything else is in the console: **Operations →
Tenants** grants and revokes staff, and suspends accounts. It will not let you
do either to yourself — revoking your own access is the one change the console
cannot undo afterwards, and on a single-VM deployment there may be no second
operator to undo it. That is what the command line above is for.

Ordinary members need none of this. They see portal health and can pull the
portals by hand under Settings → Sources.

If any of those ports is already taken on your machine, change `API_PORT_HOST`,
`HTTP_PORT` or `HTTPS_PORT` in `.env`. When you move the API, point the Vite dev
proxy at it with `VITE_API_PROXY_TARGET` in `frontend/.env.local`.

`AI_PROVIDER=fake` in `.env` runs the whole pipeline offline with deterministic
stubs, so no Gemini key is needed for development. Set `AI_PROVIDER=gemini` and
`GEMINI_API_KEY` for real matching.

The assistant's **live voice** needs four settings agreeing, and `.env.example`
ships the second one off, so a deployment copied from it has voice disabled:

| Setting | Needs to be |
|---|---|
| `ASSISTANT_ENABLED` | `true` |
| `ASSISTANT_VOICE_ENABLED` | `true` |
| `AI_PROVIDER` | `gemini` — the offline stub has no live voice |
| `GEMINI_API_KEY` | set |

`APP_URL` must also be the origin people actually open, because the voice socket
refuses any other. When voice is off the panel now says which of the four is
missing, and names the setting if you are signed in as platform staff, so this
table is a confirmation rather than the only way to find out.

One thing to expect from the stub: it *ranks* correctly — the seeded IT tenders
come out on top for the sample integrator — but its similarities sit well below
the grade thresholds, which are fitted for real embeddings. So an offline demo
feed reads as all-C. Rankings, rules, decisions, notifications and the whole
pipeline behave normally; only the letter grades need a real key, or a re-fit:

```bash
uv run python -m scripts.calibrate_thresholds          # report
uv run python -m scripts.calibrate_thresholds --write  # store, and re-grade
```

Grading is arithmetic over similarities already stored, so a re-fit costs a
`thresholds_version` bump and no AI calls at all.

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

Also you can use cli:

For dependencies
```bash
docker compose up -d db redis 
```

Run backend
```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8020 

uv run arq app.jobs.worker.ScrapeWorkerSettings   # fetches notices from the portals
uv run arq app.jobs.worker.WorkerSettings         # extraction, matching, grades, email
```

For migrations
```bash
uv run alembic upgrade head
```

Run frontend
```bash
npm run dev
```

Back both up: the database holds the accounts and decisions, and the blob volume
holds raw portal payloads, which for many closed notices is the only copy left
anywhere — and the only thing that makes a broken parser fixable after the fact.

### Releasing

Pushing a `v*` tag runs the whole test suite again, publishes `api`, `worker`
and `frontend` images to GHCR, and opens a GitHub Release whose notes are the
tag's own message.

```bash
git tag -a v1.1.0 -m "What changed and why"
git push origin v1.1.0
```

The VM then pulls those images rather than building on the box:

```bash
RELEASE=v1.1.0 ./scripts/deploy.sh      # by hand, on the VM
```

The Deploy workflow does the same thing over SSH once `DEPLOY_HOST` and its
companions are set on the repository — until then it skips rather than failing,
because a pipeline that is always red is a pipeline nobody reads. The variables
it needs are listed at the top of `.github/workflows/deploy.yml`.

**[docs/RUNBOOK.md](docs/RUNBOOK.md)** covers the rest: what to check when a
portal goes quiet, why mail is not arriving, how to restore a backup, which
metrics are worth alerting on, and what is safe to restart.

Caddy terminates TLS for `DOMAIN` automatically. Outbound email goes through
Gmail SMTP: `SMTP_USER` is the mailbox and `SMTP_PASSWORD` is a 16-character
App Password, not the account password. Google rewrites `From` to that mailbox
unless `EMAIL_FROM` is an address the account is verified to send as, and caps
sending at roughly 500 messages a day on a consumer account or 2,000 on
Workspace. SPF and DKIM still have to list Google for the sending domain.

## Documentation

| Document | What it covers |
|---|---|
| `docs/IMPLEMENTATION_PLAN.md` | Architecture, data model, matching pipeline, milestones. Start here. |
| `docs/TenderSense_BRD.pdf` | The original business requirements document. |
