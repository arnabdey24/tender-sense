#!/usr/bin/env bash
#
# Back up everything a TenderSense instance cannot rebuild.
#
# Two things are irreplaceable and they are not the same shape:
#
#   Postgres  — accounts, organizations, profiles, rules, decisions, matches.
#   Blobs     — raw portal payloads. These matter more than they look: the
#               portals are slow, rate limited, and drop notices once they
#               close, so for many notices this is the only copy that exists.
#               Losing it also loses the ability to fix a parser and replay.
#
# Redis is deliberately not backed up. It holds queued jobs and rate-limit
# counters; a restore that replayed yesterday's queue would re-send yesterday's
# emails, which is worse than losing it.
#
# Usage:
#   ./scripts/backup.sh                     # writes to ./backups
#   BACKUP_DIR=/mnt/backups ./scripts/backup.sh
#   RETAIN_DAYS=30 ./scripts/backup.sh
#
# Restore is in docs/RUNBOOK.md. A backup nobody has restored is a hypothesis,
# so the runbook's restore drill is part of this, not an appendix to it.

set -Eeuo pipefail

BACKUP_DIR="${BACKUP_DIR:-$(pwd)/backups}"
RETAIN_DAYS="${RETAIN_DAYS:-14}"
COMPOSE="${COMPOSE:-docker compose}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
POSTGRES_USER="${POSTGRES_USER:-tendersense}"
POSTGRES_DB="${POSTGRES_DB:-tendersense}"

log() { printf '%s  %s\n' "$(date -u +%H:%M:%S)" "$*" >&2; }
fail() { log "FAILED: $*"; exit 1; }

mkdir -p "$BACKUP_DIR"

db_file="$BACKUP_DIR/db-$STAMP.dump"
blob_file="$BACKUP_DIR/blobs-$STAMP.tar.gz"

log "dumping postgres to $db_file"
# Custom format: compressed, and restorable table-by-table when only one thing
# needs rolling back.
$COMPOSE exec -T db pg_dump \
	-U "$POSTGRES_USER" \
	-d "$POSTGRES_DB" \
	--format=custom \
	--no-owner \
	--no-privileges \
	>"$db_file" || fail "pg_dump"

# An empty dump means the command "succeeded" against nothing. Catching it here
# beats discovering it during a restore.
[ -s "$db_file" ] || fail "the dump is empty"

log "archiving the blob volume to $blob_file"
$COMPOSE run --rm --no-deps --entrypoint sh -v "$BACKUP_DIR:/backup" api \
	-c "tar czf /backup/$(basename "$blob_file") -C /var/lib/tendersense blobs" \
	|| fail "blob archive"

log "verifying the dump is readable"
$COMPOSE exec -T db pg_restore --list /dev/stdin <"$db_file" >/dev/null \
	|| fail "the dump does not read back"

if [ "$RETAIN_DAYS" -gt 0 ]; then
	log "removing backups older than $RETAIN_DAYS days"
	find "$BACKUP_DIR" -maxdepth 1 -name 'db-*.dump' -mtime "+$RETAIN_DAYS" -delete
	find "$BACKUP_DIR" -maxdepth 1 -name 'blobs-*.tar.gz' -mtime "+$RETAIN_DAYS" -delete
fi

log "done: $(du -h "$db_file" | cut -f1) database, $(du -h "$blob_file" | cut -f1) blobs"
