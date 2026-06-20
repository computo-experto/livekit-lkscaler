#!/usr/bin/env bash
set -euo pipefail

kubectl apply --server-side --force-conflicts -f https://github.com/kedacore/keda/releases/download/v2.4.0/keda-2.4.0.yaml
kubectl rollout status deployment/keda-operator -n keda --timeout=180s
kubectl rollout status deployment/keda-metrics-apiserver -n keda --timeout=180s