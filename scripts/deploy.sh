#!/usr/bin/env bash
#
# Roll the stack on the VM to a released version.
#
# Lives in the repository rather than inside the workflow so it can be read,
# reviewed and — most importantly — run by hand at three in the morning when
# GitHub is the last thing anyone wants in the loop:
#
#   RELEASE=v1.0.0 ./scripts/deploy.sh
#
# Pull first, then restart. Pulling is the slow, failure-prone half, and doing
# it while the old version is still serving keeps the outage to the length of a
# container restart rather than the length of a download.

set -Eeuo pipefail

RELEASE="${RELEASE:?set RELEASE to a tag, e.g. RELEASE=v1.0.0}"
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)
HEALTH_ATTEMPTS="${HEALTH_ATTEMPTS:-30}"

log() { printf '%s  %s\n' "$(date -u +%H:%M:%S)" "$*" >&2; }
fail() { log "FAILED: $*"; exit 1; }

log "checking out $RELEASE"
git fetch --tags --prune origin
git checkout --detach "$RELEASE" || fail "no such tag: $RELEASE"

export RELEASE

# Git tags carry a leading `v`; the images do not. docker/metadata-action's
# `type=semver` strips it, so v1.0.0 publishes as 1.0.0 — asking the registry
# for `v1.0.0` gets "manifest unknown". Convert at the boundary rather than
# making the tag or the pipeline lie about which namespace it is in.
IMAGE_TAG="${RELEASE#v}"
export IMAGE_TAG
log "images pinned to ${IMAGE_TAG}"

log "pulling images"
"${COMPOSE[@]}" pull || fail "could not pull the images for $RELEASE"

# Migrations run to completion before anything serves the new schema. A failure
# here leaves the old containers running, which is the right way to fail.
log "applying migrations"
"${COMPOSE[@]}" run --rm migrate || fail "migrations did not apply"

log "restarting"
"${COMPOSE[@]}" up -d --remove-orphans || fail "the stack did not come up"

log "waiting for the API to report ready"
for _ in $(seq 1 "$HEALTH_ATTEMPTS"); do
	if "${COMPOSE[@]}" exec -T api \
		python -c 'import json,sys,urllib.request; sys.exit(0 if json.load(urllib.request.urlopen("http://localhost:8000/api/v1/health/ready"))["status"]=="ok" else 1)' \
		2>/dev/null; then
		log "ready on $RELEASE"
		docker image prune -f >/dev/null
		exit 0
	fi
	sleep 5
done

# Reporting success while the API is down is worse than failing: it sends
# everyone to bed.
"${COMPOSE[@]}" logs --tail=50 api >&2 || true
fail "the API did not become ready; the previous version's containers are gone, so this needs a look"
