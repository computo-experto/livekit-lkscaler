#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="e2e/compose.yaml"
ARTIFACT_DIR="e2e/artifacts/backends"
BACKENDS="${LKSCALER_E2E_BACKENDS:-zookeeper redis}"

cd "${ROOT_DIR}"

capture_artifacts() {
	local backend="$1"
	mkdir -p "${ARTIFACT_DIR}/${backend}"
	docker compose -f "${COMPOSE_FILE}" --profile backends ps >"${ARTIFACT_DIR}/${backend}/compose-ps.txt" || true
	docker compose -f "${COMPOSE_FILE}" --profile backends logs --no-color >"${ARTIFACT_DIR}/${backend}/compose-logs.txt" || true
}

wait_for_agents() {
	for attempt in $(seq 1 60); do
		if curl -fsS http://127.0.0.1:18090/health >/dev/null 2>&1 &&
			curl -fsS http://127.0.0.1:18091/health >/dev/null 2>&1; then
			echo "backend-wired agents are up after ${attempt} attempt(s)"
			return 0
		fi
		sleep 1
	done
	echo "error: backend-wired agents did not become ready" >&2
	return 1
}

status=0
for backend in ${BACKENDS}; do
	echo "=== coordination e2e: ${backend} ==="
	export LKSCALER_E2E_BACKEND="${backend}"
	export E2E_STACK_RUNNING=1

	docker compose -f "${COMPOSE_FILE}" --profile backends up -d --build
	if ! scripts/wait_for_services.sh 180 || ! wait_for_agents; then
		echo "=== coordination e2e: ${backend} FAILED (stack did not become ready) ===" >&2
		capture_artifacts "${backend}"
		docker compose -f "${COMPOSE_FILE}" --profile backends down -v
		status=1
		continue
	fi

	if uv run pytest -m e2e e2e/tests/test_e2e_backends.py; then
		echo "=== coordination e2e: ${backend} PASSED ==="
	else
		echo "=== coordination e2e: ${backend} FAILED ===" >&2
		status=1
	fi

	capture_artifacts "${backend}"
	docker compose -f "${COMPOSE_FILE}" --profile backends down -v
done

exit "${status}"
