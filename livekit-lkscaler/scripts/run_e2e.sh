#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="e2e/compose.yaml"
ARTIFACT_DIR="e2e/artifacts"

cleanup() {
	mkdir -p "${ARTIFACT_DIR}"
	docker compose -f "${COMPOSE_FILE}" ps >"${ARTIFACT_DIR}/compose-ps.txt" || true
	docker compose -f "${COMPOSE_FILE}" logs --no-color >"${ARTIFACT_DIR}/compose-logs.txt" || true
	docker compose -f "${COMPOSE_FILE}" down -v || true
}

trap cleanup EXIT

docker compose -f "${COMPOSE_FILE}" up -d --build
scripts/wait_for_services.sh 180

E2E_STACK_RUNNING=1 uv run pytest -m e2e e2e/tests/test_e2e_stack.py
uv run pytest e2e/tests/test_compose_contract.py
E2E_STACK_RUNNING=1 uv run pytest e2e/tests/test_e2e_binpack.py
