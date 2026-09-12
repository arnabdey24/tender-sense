#!/usr/bin/env bash
#
# Why is this deployment not sending email?
#
#   ./scripts/email-doctor.sh
#
# Read-only. It changes nothing, sends nothing, and prints no secret — the
# relay password is reported as set or unset and never echoed, so the output
# is safe to paste into an issue.
#
# It exists because the failure it diagnoses is silent. When the relay is
# misconfigured nothing on the send path errors: the outbox row is written,
# the pump claims it, the transport reports success, and the message is
# swallowed by a sink or refused for a sender no receiver will accept. Every
# counter reads healthy and the only evidence is an inbox that stayed empty,
# which is why "no email arrived, nothing in spam" was as far as anyone got.
#
# Six questions, in the order that narrows fastest: what is running, is it
# configured to send, did the application itself complain at boot, what is in
# the queue, what did the relay say, and is anything stuck.

set -Eeuo pipefail

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)
PSQL=("${COMPOSE[@]}" exec -T db psql -U "${POSTGRES_USER:-tendersense}" -d "${POSTGRES_DB:-tendersense}" -qtA)

rule() { printf '\n\033[1m── %s\033[0m\n' "$*"; }
note() { printf '   %s\n' "$*"; }

rule "1. What is running"
git describe --tags --always 2>/dev/null || note "not a git checkout"
"${COMPOSE[@]}" ps --format '   {{.Service}}  {{.State}}  {{.Image}}' 2>/dev/null || note "compose not up"

rule "2. Is it configured to send"
# Read from the container's own environment, not from .env on disk: those
# disagree whenever someone edited the file and did not restart, and the
# container's view is the one that actually sends.
if "${COMPOSE[@]}" exec -T api sh -lc 'true' >/dev/null 2>&1; then
  "${COMPOSE[@]}" exec -T api sh -lc '
    for k in SMTP_HOST SMTP_PORT SMTP_USER SMTP_STARTTLS SMTP_SSL EMAIL_FROM EMAIL_REPLY_TO APP_URL ENVIRONMENT; do
      printf "   %-18s %s\n" "$k" "$(printenv "$k" 2>/dev/null || echo "(unset)")"
    done
    if [ -n "${SMTP_PASSWORD:-}" ]; then
      printf "   %-18s set, %s characters\n" SMTP_PASSWORD "${#SMTP_PASSWORD}"
    else
      printf "   %-18s (unset)\n" SMTP_PASSWORD
    fi'
else
  note "api container is not running"
fi

rule "3. What the application said about it at boot"
# Emitted once per start since 1.11.1. Empty here means either a clean
# configuration or a version too old to check — section 1 says which.
if ! "${COMPOSE[@]}" logs api 2>/dev/null | grep -F "email_configuration_problem" | tail -20; then
  note "no complaints logged"
fi

rule "4. What is in the queue"
"${COMPOSE[@]}" exec -T db psql -U "${POSTGRES_USER:-tendersense}" -d "${POSTGRES_DB:-tendersense}" -c "
  select status, count(*) as rows, max(attempts) as worst_attempts,
         to_char(max(created_at), 'YYYY-MM-DD HH24:MI') as newest
  from email_outbox group by status order by 2 desc;" 2>/dev/null \
  || note "could not read the outbox"

rule "5. What the relay actually said"
"${COMPOSE[@]}" exec -T db psql -U "${POSTGRES_USER:-tendersense}" -d "${POSTGRES_DB:-tendersense}" -c "
  select template_key, status, attempts,
         to_char(created_at, 'MM-DD HH24:MI') as created,
         left(coalesce(last_error, '—'), 90) as last_error
  from email_outbox
  where status in ('failed','sending') or last_error is not null
  order by created_at desc limit 10;" 2>/dev/null \
  || note "could not read the outbox"

rule "6. Anything stranded by a restart"
STUCK="$("${PSQL[@]}" -c "select count(*) from email_outbox where status='sending';" 2>/dev/null || echo '?')"
note "rows in 'sending': ${STUCK}"
note "a row here for more than EMAIL_STALLED_AFTER_MINUTES was abandoned by a"
note "worker that died mid-send. Since 1.11.1 the pump takes these back on its"
note "next pass; before that they were stuck, invisible and unretryable."
"${COMPOSE[@]}" logs worker 2>/dev/null | grep -F "email_reclaimed_stalled" | tail -5 || true

printf '\n'
