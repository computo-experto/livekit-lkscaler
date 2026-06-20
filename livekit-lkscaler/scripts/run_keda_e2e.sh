#!/usr/bin/env bash
set -euo pipefail

ARTIFACT_DIR="e2e/artifacts"
CLUSTER_NAME="lkscaler-keda-e2e"
NAMESPACE="livekit-system"
AGENT_IMAGE="lkscaler-e2e-agent:local"

for cmd in kind kubectl envsubst; do
	if ! command -v "${cmd}" >/dev/null 2>&1; then
		echo "error: required command not found: ${cmd}" >&2
		exit 1
	fi
done

cleanup() {
	mkdir -p "${ARTIFACT_DIR}"
	kubectl get pods -A >"${ARTIFACT_DIR}/keda-kubectl-pods.txt" || true
	kubectl get deployments -A >"${ARTIFACT_DIR}/keda-kubectl-deployments.txt" || true
	kubectl describe pod -n "${NAMESPACE}" -l app=livekit-server >"${ARTIFACT_DIR}/keda-livekit-server-describe.txt" || true
	kubectl logs deployment/livekit-server -n "${NAMESPACE}" >"${ARTIFACT_DIR}/keda-livekit-server-logs.txt" 2>&1 || true
	kubectl describe pod -n "${NAMESPACE}" -l app=livekit-agents >"${ARTIFACT_DIR}/keda-livekit-agents-describe.txt" || true
	kubectl logs deployment/livekit-agents -n "${NAMESPACE}" >"${ARTIFACT_DIR}/keda-livekit-agents-logs.txt" 2>&1 || true
	kubectl get pods -A >"${ARTIFACT_DIR}/keda-kubectl-pods.txt" || true
	kubectl get scaledobject -A >"${ARTIFACT_DIR}/keda-kubectl-scaledobjects.txt" || true
	kind delete cluster --name "${CLUSTER_NAME}" || true
}

trap cleanup EXIT

kind create cluster --name "${CLUSTER_NAME}" --image kindest/node:v1.22.17 --config e2e/kind/kind-config.yaml

docker build -t "${AGENT_IMAGE}" -f e2e/Dockerfile .
kind load docker-image --name "${CLUSTER_NAME}" "${AGENT_IMAGE}"

bash e2e/kind/install_keda.sh

env \
	NAMESPACE="${NAMESPACE}" \
	AGENT_IMAGE="${AGENT_IMAGE}" \
	envsubst < e2e/kind/workload.yaml | kubectl apply -f -

kubectl rollout status deployment/livekit-server -n "${NAMESPACE}" --timeout=180s
kubectl rollout status deployment/livekit-agents -n "${NAMESPACE}" --timeout=180s

SCALER_ADDRESS="lkscaler-keda.livekit-system.svc.cluster.local:9090"

env \
	SCALEDOBJECT_NAME="livekit-agents-keda" \
	NAMESPACE="livekit-system" \
	DEPLOYMENT_NAME="livekit-agents" \
	MIN_REPLICA_COUNT="1" \
	MAX_REPLICA_COUNT="20" \
	POLL_INTERVAL_SEC="15" \
	SCALE_DOWN_DWELL_SEC="900" \
	MIN_CLUSTER_FREE_SLOTS="4" \
	SCALER_ADDRESS="${SCALER_ADDRESS}" \
	envsubst < packages/lkscaler-keda/src/lkscaler_keda/manifests/scaledobject.yaml | kubectl apply -f -

env \
	SERVICE_ACCOUNT_NAME="lkscaler-keda" \
	NAMESPACE="livekit-system" \
	ROLE_NAME="lkscaler-keda" \
	ROLE_BINDING_NAME="lkscaler-keda" \
	envsubst < packages/lkscaler-keda/src/lkscaler_keda/manifests/rbac.yaml | kubectl apply -f -

KEDA_E2E_RUNNING=1 KEDA_E2E_NAMESPACE="${NAMESPACE}" uv run --directory e2e pytest tests/test_keda_e2e.py -q