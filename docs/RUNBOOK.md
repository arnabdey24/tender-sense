# TenderSense runbook

For whoever is on the other end of the pager. Every section answers one
question: what is broken, how do I confirm it, and what do I do about it.

The stack is one VM running Docker Compose. Unless stated otherwise, commands
run from the repository root on that VM.

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f api
```

Set an alias for the rest of this document:

```bash
alias dc='docker compose -f docker-compose.yml -f docker-compose.prod.yml'
```

## Is it up?

| Check | Command | Healthy answer |
|---|---|---|
| Edge | `curl -sS https://$DOMAIN/api/v1/health/live` | `{"status":"ok"}` |
| Dependencies | `curl -sS https://$DOMAIN/api/v1/health/ready` | `{"status":"ok","database":true,"redis":true}` |
| Workers | `dc logs --tail=20 worker worker-scrape` | recent `job_finished` lines |
| Metrics | `dc exec api curl -sS localhost:8000/metrics \| head` | Prometheus text |

`/health/ready` returns 503 when Postgres or Redis is unreachable, so a load
balancer takes the instance out on its own. `/health/live` stays 200 as long as
the process is alive — restarting on a database blip would turn a ten-second
outage into a crash loop.

## The alarms worth having

Point Prometheus at `api:8000/metrics` on the compose network. It is not
exposed through Caddy, and it should not be: it is unauthenticated.

| Metric | Alert when | Means |
|---|---|---|
| `tendersense_source_health` | `< 1` for 6h | A portal has stopped answering |
| `tendersense_tenders_ingested_total` | no increase in 24h | Ingestion has silently stopped |
| `tendersense_emails_total{outcome="failed"}` | rising | The SMTP relay is rejecting mail |
| `tendersense_job_duration_seconds{status="failed"}` | any | A background task is throwing |
| `tendersense_ai_tokens_total` | flat while matches rise | The daily budget is exhausted |

## Common incidents

### A portal stopped returning notices

A scraper that quietly stops looks exactly like a portal with nothing to
publish. The run records are the only thing that tells them apart.

```bash
curl -sS -H "Authorization: Bearer $STAFF_TOKEN" \
  https://$DOMAIN/api/v1/admin/scraper-runs | jq '.[0]'
curl -sS -X POST -H "Authorization: Bearer $STAFF_TOKEN" \
  https://$DOMAIN/api/v1/admin/sources/$SOURCE_ID/check
```

- **Reachable, but no rows** — the portal changed its markup. Fix the selectors
  in `tender_sources.config` (a `PATCH /admin/sources/{id}` — no deploy), then
  replay the notices already held: `POST /admin/sources/{id}/reparse`. Nothing
  is fetched from the portal during a replay.
- **Not reachable at all** — if e-GP has started refusing the HTTP client,
  switch to the browser adapter: `PATCH /admin/sources/{id}` with
  `{"adapter_key": "egp_bd_playwright"}`. The scrape worker already runs the
  Playwright image. No deploy, no code change.
- **Health stuck at `down` after recovery** — health is derived from
  consecutive failures; one successful run clears it. Force one with
  `POST /admin/sources/{id}/run`.

### Nobody is receiving email

Start here. It is read-only, prints no secret, and answers the whole question
in one pass:

```bash
./scripts/email-doctor.sh                 # on the VM, in DEPLOY_PATH
```

The trap this exists for is that **none of the common causes produce an
error**. The outbox row is written, the pump claims it, the transport reports
success, and the message is swallowed by a sink or refused for a sender no
receiver accepts. Every counter reads healthy, so "no `last_error` anywhere"
rules nothing out — it is the expected symptom.

The console says the same thing: `/admin` shows a panel naming any
configuration fault, and its mail tile separates *gave up* from *stuck
mid-send* from *never configured to send*.

In order of likelihood:

1. **The deployment is not configured to send at all.** A sender on a reserved
   domain (`.local`, `.test`, `.invalid`), or `SMTP_HOST` still pointing at a
   development sink such as `mailpit`. Both discard mail and report success.
   The shipped `.env.example`, deployed unchanged, has both. Section 3 of the
   doctor output lists these; so does the console.
2. **The relay rejects the credentials.** `SMTP_USER` / `SMTP_PASSWORD` are
   passed through by compose; confirm they reached the container with
   `dc exec api printenv SMTP_HOST SMTP_USER`. Gmail needs a 16-character App
   Password, not the account password.
3. **The relay rejects the sender.** `EMAIL_FROM` must be a domain whose SPF
   record lists the relay, and on Gmail an address the account is verified to
   send as — otherwise Google rewrites it.
4. **The links are dead even though the mail arrived.** `APP_URL` pointing at
   `localhost` makes every verification and reset link unreachable, which gets
   reported as "the email never worked".
5. **A message was stranded by a restart.** A worker killed mid-send used to
   leave its row in `sending` where nothing retried it, nothing listed it and
   the retry button could not reach it. Workers restart on every deploy. Since
   1.11.1 the pump reclaims these; `email_reclaimed_stalled` in the worker log
   is it happening.
6. **Nobody is a verified recipient.** An organization with no confirmed
   address receives nothing by design. Check
   `GET /api/v1/notification-recipients` as one of its admins.

Retry a specific failed message with
`POST /admin/email-outbox/{id}/retry`. The pump runs twice a minute.

### Nobody can reach /admin

The console refuses to let an operator revoke their own staff access or suspend
their own account, so the usual way into this is a deployment that never had a
superuser, or one whose only operator has left. Make another from the box:

```bash
docker compose run --rm api python -m scripts.create_superuser --email you@example.com
```

On an address that already exists this promotes it and leaves its password
alone; add `--reset-password` if the password is what was lost. The generated
password is printed once and is not recoverable afterwards.

```bash
docker compose exec db psql -U tendersense -d tendersense \
  -c "select email, is_superuser, is_active from users where is_superuser;"
```

### Live voice will not start

Open the assistant and press the waveform button in the composer. It answers
with the reason rather than doing nothing, and as a superuser it also names the
setting to change. The four conditions are in the README; `ASSISTANT_VOICE_ENABLED`
defaults to `false`, so a deployment made from `.env.example` has voice off and
nothing is broken.

If the panel says voice is available but a call never connects, check `APP_URL`:
the socket compares the browser's `Origin` against `APP_URL` plus
`BACKEND_CORS_ORIGINS` and closes with 1008 on a mismatch, which in the browser
looks like a connection that opens and immediately drops. A deployment that
moved to a real domain without updating `APP_URL` fails exactly this way.

```bash
docker compose logs api | grep -i voice
```

### Matches stopped appearing

```bash
curl -sS -H "Authorization: Bearer $STAFF_TOKEN" \
  "https://$DOMAIN/api/v1/admin/jobs/runs?name=process_tender" | jq '.[0]'
curl -sS -H "Authorization: Bearer $STAFF_TOKEN" \
  https://$DOMAIN/api/v1/admin/ai-usage | jq '{budget:.daily_token_budget, spent:.spent_today}'
```

- **`spent_today` at the budget** — explanations degrade to the templated ones
  and matches still score. Raise `AI_DAILY_TOKEN_BUDGET` or wait for midnight
  UTC. A budget of `0` means unlimited.
- **`process_tender` runs failing** — the error is on the run record. Matching
  is written to degrade: extraction failing still leaves an embedded, scored
  match, so a total absence of matches points at embeddings or the database
  rather than the model.
- **A verdict that is wrong and stays wrong** — a match whose inputs are
  unchanged is deliberately never recomputed, which also makes a bad verdict
  sticky. `rematch_org(org_id, reason, force=True)` is the only thing that
  clears it.

### The queue is backed up

```bash
dc exec redis redis-cli llen arq:queue
dc exec redis redis-cli llen arq:queue:scrape
```

The scrape queue is capped at one job at a time on purpose — portals are
visited in series. A depth of a few is normal after a dispatch; a depth that
only grows means the scrape worker is stuck. Restart it: `dc restart worker-scrape`.
Jobs are re-enqueued by their crons, and every one of them is idempotent.

### Scraping stores nothing ("permission denied" on the blob volume)

Symptom: runs finish `partial` with every notice counted as lost, and
`dc logs worker-scrape` shows
`notice_not_stored ... Permission denied: '/var/lib/tendersense/blobs/<source>'`.

The API and the scrape worker are built from different base images and run as
different users. Docker fixes a named volume's ownership from whichever image
mounts it first, so a volume created before both images shared a group is owned
by one of them alone. Current images put both users in a `tendersense` group and
set the setgid bit; a volume from before that needs fixing once:

```bash
dc run --rm --no-deps --user root --entrypoint sh api \
  -c 'chgrp -R tendersense /var/lib/tendersense && chmod -R 2775 /var/lib/tendersense'
```

Nothing is lost — the notices were never stored, so the next scrape picks them
up again.

### Disk filling up

```bash
dc exec api du -sh /var/lib/tendersense/blobs
docker system df
```

Raw payloads accumulate. `purge_orphan_blobs` runs weekly and removes files no
document row points at; run it now with
`POST /admin/jobs/trigger {"job": "purge_orphan_blobs"}`. Postgres growth is
usually `job_runs` — `purge_old_runs` sweeps past `JOB_RUN_RETENTION_DAYS`
(default 30).

## Backup and restore

```bash
./scripts/backup.sh              # database dump + blob archive into ./backups
RETAIN_DAYS=30 ./scripts/backup.sh
```

Put it in cron at a quiet hour and copy the output off the VM. A backup that
lives only on the machine it is protecting is not a backup.

```cron
30 1 * * * cd /srv/tendersense && BACKUP_DIR=/mnt/backups ./scripts/backup.sh >> /var/log/tendersense-backup.log 2>&1
```

**Restore the database:**

```bash
dc stop api worker worker-scrape
dc exec -T db psql -U tendersense -d postgres -c 'DROP DATABASE tendersense;'
dc exec -T db psql -U tendersense -d postgres -c 'CREATE DATABASE tendersense;'
dc exec -T db psql -U tendersense -d tendersense -f /docker-entrypoint-initdb.d/00-init.sql
dc exec -T db pg_restore -U tendersense -d tendersense --no-owner < backups/db-<stamp>.dump
dc run --rm migrate
dc start api worker worker-scrape
```

The extensions must be recreated before the restore, because the dump's vector
columns reference a type that does not exist in a fresh database.

**Restore the blobs:**

```bash
dc run --rm --no-deps --entrypoint sh -v "$PWD/backups:/backup" api \
  -c 'tar xzf /backup/blobs-<stamp>.tar.gz -C /var/lib/tendersense'
```

**Drill it.** Restore into a scratch VM once a quarter and sign in. A backup
nobody has restored is a hypothesis.

## Deploying

Releases are cut by tag. Pushing `v*` runs the suite, publishes images to GHCR
and opens a GitHub Release; the VM pulls those images rather than building.

```bash
RELEASE=v1.1.0 ./scripts/deploy.sh
```

That script is the whole deployment: check out the tag, `docker compose pull`,
run migrations, restart, and wait for `/health/ready`. The Deploy workflow runs
exactly the same script over SSH, so a GitHub outage costs you nothing — the
manual path is the real path.

It pulls before it restarts, deliberately. Pulling is the slow, failure-prone
half, and doing it while the old version still serves keeps the outage to a
container restart rather than a download.

`migrate` runs to completion before `api` and the workers start, so a schema
change lands before anything reads the new shape. Migrations apply, downgrade
and re-apply cleanly (CI proves the round trip on every push); if one fails the
API does not start, which is intended — a half-migrated database serving traffic
is worse than a few minutes of downtime.

**Rolling back:**

```bash
RELEASE=v1.0.0 ./scripts/deploy.sh
```

or run the Deploy workflow with the older tag. Do not downgrade a migration to
roll back an application change unless the migration is the problem: downgrades
drop columns, and the data in them does not come back. If a release added a
column, the previous version simply ignores it.

**What is actually running:**

```bash
git -C /srv/tendersense describe --tags
curl -sS https://$DOMAIN/openapi.json | jq -r .info.version
```

The second reads the version the API reports for itself, which is the one that
matters when the checkout and the containers have drifted apart.

## Rotating secrets

| Secret | Effect of rotating |
|---|---|
| `SECRET_KEY` | Signs access tokens and the OAuth state cookie. Rotating signs everyone out. Verification, reset and invitation links keep working — they are database rows, not signed tokens. |
| `POSTGRES_PASSWORD` | Change it in the database and `.env` together, then `dc up -d`. |
| `GEMINI_API_KEY` | Takes effect on the next process start. Matching continues on stored embeddings meanwhile. |
| `SMTP_PASSWORD` | Queued mail retries with backoff, so a brief mismatch delays delivery rather than losing it. |

Every secret is read from the environment. Nothing is baked into an image, and
`repr(settings)` deliberately omits the database and Redis URLs so a crash
traceback cannot print the password.

## What is safe to restart

| Service | Effect |
|---|---|
| `api` | In-flight requests fail; the SPA retries. |
| `worker` | The running job is re-enqueued. Every task is idempotent. |
| `worker-scrape` | A partial scrape is recorded `failed` and re-run on the next cron. |
| `caddy` | A few seconds of connection refused. Certificates are on a volume. |
| `db` | Everything else reconnects. Do not do this during a migration. |
