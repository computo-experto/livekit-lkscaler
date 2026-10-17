#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="e2e/compose.yaml"
PROFILES=(--profile real-agents --profile backends)
ARTIFACT_DIR="e2e/artifacts/real-agents"
BACKENDS="${LKSCALER_E2E_BACKENDS:-zookeeper redis}"

cd "${ROOT_DIR}"

cleanup() {
	docker compose -f "${COMPOSE_FILE}" "${PROFILES[@]}" down -v --remove-orphans || true
}
trap cleanup EXIT

capture_artifacts() {
	local backend="$1"
	mkdir -p "${ARTIFACT_DIR}/${backend}"
	docker compose -f "${COMPOSE_FILE}" "${PROFILES[@]}" ps >"${ARTIFACT_DIR}/${backend}/compose-ps.txt" || true
	docker compose -f "${COMPOSE_FILE}" "${PROFILES[@]}" logs --no-color >"${ARTIFACT_DIR}/${backend}/compose-logs.txt" || true
}

wait_for_real_agents() {
	for attempt in $(seq 1 90); do
		registered=0
		for pod in real-agent1 real-agent2 real-agent3; do
			if docker compose -f "${COMPOSE_FILE}" "${PROFILES[@]}" logs --no-color "${pod}" 2>/dev/null |
				grep -qi 'registered'; then
				registered=$((registered + 1))
			fi
		done
		if [ "${registered}" -eq 3 ]; then
			echo "real agents registered after ${attempt} attempt(s)"
			return 0
		fi
		sleep 1
	done
	echo "error: real agents did not register with the production-mode server" >&2
	return 1
}

status=0
for backend in ${BACKENDS}; do
	echo "=== real agent e2e: ${backend} ==="
	export LKSCALER_E2E_BACKEND="${backend}"
	export LKSCALER_E2E_NAMESPACE="lkscaler-real-${backend}"
	export E2E_STACK_RUNNING=1

	docker compose -f "${COMPOSE_FILE}" "${PROFILES[@]}" down -v --remove-orphans
	docker compose -f "${COMPOSE_FILE}" "${PROFILES[@]}" up -d --build
	if ! scripts/wait_for_services.sh 180 || ! wait_for_real_agents; then
		echo "=== real agent e2e: ${backend} FAILED (stack did not become ready) ===" >&2
		capture_artifacts "${backend}"
		docker compose -f "${COMPOSE_FILE}" "${PROFILES[@]}" down -v
		status=1
		continue
	fi

	if uv run pytest -m e2e e2e/tests/test_real_agent_scenarios.py; then
		echo "=== real agent e2e: ${backend} PASSED ==="
	else
		echo "=== real agent e2e: ${backend} FAILED ===" >&2
		status=1
	fi

	capture_artifacts "${backend}"
	docker compose -f "${COMPOSE_FILE}" "${PROFILES[@]}" down -v
done

exit "${status}"
