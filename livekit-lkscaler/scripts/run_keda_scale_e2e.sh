#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLUSTER_NAME="lkscaler-keda-scale"
NAMESPACE="livekit-system"
AGENT_IMAGE="lkscaler-e2e-real-agent:local"
# KEDA renders autoscaling/v2 HorizontalPodAutoscalers, which needs Kubernetes 1.23 or newer.
NODE_IMAGE="${NODE_IMAGE:-kindest/node:v1.27.3}"
KEDA_VERSION="2.10.1"
LIVEKIT_PORT="17880"
ZK_PORT="12181"
ARTIFACT_DIR="e2e/artifacts/keda-scale"

cd "${ROOT_DIR}"

for cmd in kind kubectl docker uv; do
	if ! command -v "${cmd}" >/dev/null 2>&1; then
		echo "error: required command not found: ${cmd}" >&2
		exit 1
	fi
done

kind_version="$(kind version | awk '{print $2}')"
case "${kind_version}" in
v0.1?|v0.1?.*) echo "error: kind ${kind_version} cannot boot ${NODE_IMAGE}; install kind v0.20 or newer" >&2; exit 1 ;;
esac

PORT_FORWARD_PID=""
ZK_FORWARD_PID=""

cleanup() {
	mkdir -p "${ARTIFACT_DIR}"
	kubectl get pods -A >"${ARTIFACT_DIR}/pods.txt" 2>&1 || true
	kubectl get deployments -A >"${ARTIFACT_DIR}/deployments.txt" 2>&1 || true
	kubectl get scaledobject -A >"${ARTIFACT_DIR}/scaledobjects.txt" 2>&1 || true
	kubectl get hpa -A >"${ARTIFACT_DIR}/hpa.txt" 2>&1 || true
	kubectl describe scaledobject -A >"${ARTIFACT_DIR}/scaledobject-describe.txt" 2>&1 || true
	kubectl logs -n "${NAMESPACE}" deployment/livekit-agents >"${ARTIFACT_DIR}/livekit-agents-logs.txt" 2>&1 || true
	kubectl logs -n "${NAMESPACE}" deployment/lkscaler-keda >"${ARTIFACT_DIR}/lkscaler-keda-logs.txt" 2>&1 || true
	kubectl logs -n "${NAMESPACE}" deployment/livekit >"${ARTIFACT_DIR}/livekit-logs.txt" 2>&1 || true
	if [ -n "${PORT_FORWARD_PID}" ]; then
		kill "${PORT_FORWARD_PID}" 2>/dev/null || true
	fi
	if [ -n "${ZK_FORWARD_PID}" ]; then
		kill "${ZK_FORWARD_PID}" 2>/dev/null || true
	fi
	kind delete cluster --name "${CLUSTER_NAME}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

wait_for_http() {
	local url="$1" attempts="${2:-60}"
	for _ in $(seq 1 "${attempts}"); do
		if curl -fsS --max-time 2 "${url}" >/dev/null 2>&1; then
			return 0
		fi
		sleep 0.5
	done
	echo "error: ${url} did not answer" >&2
	return 1
}

echo "=== creating kind cluster ${CLUSTER_NAME} on ${NODE_IMAGE} (kind ${kind_version}) ==="
if kind get clusters 2>/dev/null | grep -qx "${CLUSTER_NAME}"; then
	kind delete cluster --name "${CLUSTER_NAME}"
fi
kind create cluster --name "${CLUSTER_NAME}" --image "${NODE_IMAGE}" --wait 180s

echo "=== building and loading the worker image ==="
docker build -t "${AGENT_IMAGE}" -f e2e/Dockerfile .
kind load docker-image --name "${CLUSTER_NAME}" "${AGENT_IMAGE}"

echo "=== installing KEDA ${KEDA_VERSION} ==="
kubectl apply -f "https://github.com/kedacore/keda/releases/download/v${KEDA_VERSION}/keda-${KEDA_VERSION}.yaml"
kubectl rollout status deployment/keda-operator -n keda --timeout=240s
kubectl rollout status deployment/keda-metrics-apiserver -n keda --timeout=240s
kubectl version --output=yaml >"${ARTIFACT_DIR}/kubectl-version.yaml" 2>&1 || true

echo "=== applying the fixture stack ==="
kubectl apply -f e2e/kind/namespace.yaml
kubectl apply -f e2e/kind/zookeeper.yaml
kubectl apply -f e2e/kind/livekit.yaml
kubectl rollout status deployment/zk -n "${NAMESPACE}" --timeout=240s
kubectl rollout status deployment/livekit -n "${NAMESPACE}" --timeout=240s

kubectl apply -f e2e/kind/agents.yaml
kubectl rollout status deployment/livekit-agents -n "${NAMESPACE}" --timeout=240s

kubectl apply -f e2e/kind/scaler.yaml
kubectl rollout status deployment/lkscaler-keda -n "${NAMESPACE}" --timeout=180s

kubectl apply -f e2e/kind/scaledobject.yaml
kubectl wait --for=create "hpa/keda-hpa-livekit-agents-keda" -n "${NAMESPACE}" --timeout=180s

echo "=== port-forwarding the LiveKit API ==="
kubectl port-forward -n "${NAMESPACE}" svc/livekit "${LIVEKIT_PORT}:7880" >/dev/null 2>&1 &
PORT_FORWARD_PID=$!
wait_for_http "http://127.0.0.1:${LIVEKIT_PORT}/"

# The scenario reads the placement store the scaler reads, so it can tell a booked room from a
# dispatch LiveKit dropped because no worker had registered yet.
echo "=== port-forwarding the placement store ==="
kubectl port-forward -n "${NAMESPACE}" svc/zk "${ZK_PORT}:2181" >/dev/null 2>&1 &
ZK_FORWARD_PID=$!
until (exec 3<>"/dev/tcp/127.0.0.1/${ZK_PORT}") 2>/dev/null; do
	sleep 0.5
done

# KEDA polls every 5s and stabilizes for 30s, so the scenario owns the deadlines.
echo "=== running the scale scenario ==="
export LKSCALER_E2E_SERVER_HTTP="http://127.0.0.1:${LIVEKIT_PORT}"
export LKSCALER_E2E_ZK_HOSTS="127.0.0.1:${ZK_PORT}"
export KEDA_SCALE_E2E=1
uv run pytest e2e/tests/test_keda_scale.py -q
