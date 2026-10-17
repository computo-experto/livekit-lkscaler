#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER_NAME="lkscaler-zk-integration"
HOST_PORT="${LKSCALER_ZK_PORT:-22181}"  # not 2181, so a local ZooKeeper is left alone

cleanup() {
	docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

cleanup
echo "starting zookeeper:3.9 as ${CONTAINER_NAME} on port ${HOST_PORT}"
docker run -d --name "${CONTAINER_NAME}" -p "${HOST_PORT}:2181" zookeeper:3.9 >/dev/null

echo "waiting for ZooKeeper to answer"
for attempt in $(seq 1 60); do
	if docker exec "${CONTAINER_NAME}" bash -c "exec 3<>/dev/tcp/127.0.0.1/2181 && echo srvr >&3 && cat <&3" 2>/dev/null | grep -q "Zookeeper version:"; then
		echo "ZooKeeper is up after ${attempt} attempt(s)"
		break
	fi
	if [[ "${attempt}" -eq 60 ]]; then
		echo "error: ZooKeeper did not become ready" >&2
		docker logs "${CONTAINER_NAME}" >&2 || true
		exit 1
	fi
	sleep 1
done

export LKSCALER_ZK_HOSTS="127.0.0.1:${HOST_PORT}"
cd "${ROOT_DIR}"
uv run pytest packages/lkscaler-core/tests/integration/test_zookeeper_integration.py -v
