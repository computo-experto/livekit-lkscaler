#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="e2e/compose.yaml"
MAX_SECONDS="${1:-120}"
START_TS="$(date +%s)"

echo "Waiting for E2E services to become healthy (timeout ${MAX_SECONDS}s)..."

while true; do
	if docker compose -f "${COMPOSE_FILE}" ps --format json >/tmp/lkscaler_e2e_ps.json 2>/dev/null; then
		if grep -q '"Health":"healthy"' /tmp/lkscaler_e2e_ps.json && grep -q '"Service":"livekit"' /tmp/lkscaler_e2e_ps.json; then
			echo "E2E stack is healthy."
			rm -f /tmp/lkscaler_e2e_ps.json
			exit 0
		fi
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
