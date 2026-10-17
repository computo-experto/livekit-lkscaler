#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER_NAME="lkscaler-redis-integration"
HOST_PORT="${LKSCALER_REDIS_PORT:-26379}"  # not 6379, so a local Redis is left alone

cleanup() {
	docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

cleanup
echo "starting redis:7 as ${CONTAINER_NAME} on port ${HOST_PORT}"
docker run -d --name "${CONTAINER_NAME}" -p "${HOST_PORT}:6379" redis:7 >/dev/null

echo "waiting for Redis to answer PING"
for attempt in $(seq 1 60); do
	if docker exec "${CONTAINER_NAME}" redis-cli ping 2>/dev/null | grep -q PONG; then
		echo "Redis is up after ${attempt} attempt(s)"
		break
	fi
	if [[ "${attempt}" -eq 60 ]]; then
		echo "error: Redis did not become ready" >&2
		docker logs "${CONTAINER_NAME}" >&2 || true
		exit 1
	fi
	sleep 1
done

export LKSCALER_REDIS_URL="redis://127.0.0.1:${HOST_PORT}/0"
cd "${ROOT_DIR}"
uv run pytest packages/lkscaler-core/tests/integration/test_redis_integration.py -v
