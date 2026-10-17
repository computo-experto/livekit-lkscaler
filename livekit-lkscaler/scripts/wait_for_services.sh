#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="e2e/compose.yaml"
MAX_SECONDS="${1:-120}"
START_TS="$(date +%s)"
# A service that crashed on start still leaves the stack "healthy" by the healthcheck rule, so the
# number of running containers is compared with the containers the active profiles actually created.
MIN_SERVICES=6
# A container that crashes a second after start still counts as running in the first sample, so the
# stack has to look right twice before the suite is allowed to start.
STABLE_SAMPLES=2
consecutive_ok=0

echo "Waiting for E2E services to become healthy (timeout ${MAX_SECONDS}s)..."

while true; do
	if docker compose -f "${COMPOSE_FILE}" ps --format json >/tmp/lkscaler_e2e_ps.json 2>/dev/null; then
		created_services="$(docker compose -f "${COMPOSE_FILE}" ps --all --services 2>/dev/null | wc -l)"
		running_services="$(docker compose -f "${COMPOSE_FILE}" ps --services --status running 2>/dev/null | wc -l)"
		if grep -q '"Health":"healthy"' /tmp/lkscaler_e2e_ps.json && grep -q '"Service":"livekit"' /tmp/lkscaler_e2e_ps.json && [ "${running_services}" -eq "${created_services}" ] && [ "${running_services}" -ge "${MIN_SERVICES}" ]; then
			consecutive_ok=$((consecutive_ok + 1))
			if [ "${consecutive_ok}" -ge "${STABLE_SAMPLES}" ]; then
				echo "E2E stack is healthy with ${running_services} running services."
				rm -f /tmp/lkscaler_e2e_ps.json
				exit 0
			fi
			sleep 5
			continue
		fi
		consecutive_ok=0
	fi

	now_ts="$(date +%s)"
	if (( now_ts - START_TS >= MAX_SECONDS )); then
		echo "Timed out waiting for E2E stack health." >&2
		docker compose -f "${COMPOSE_FILE}" ps || true
		docker compose -f "${COMPOSE_FILE}" logs --no-color || true
		rm -f /tmp/lkscaler_e2e_ps.json
		exit 1
	fi

	sleep 3
done
