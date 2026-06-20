from __future__ import annotations

import os
import subprocess
import time

import pytest

from lkscaler_core.snapshot import ClusterSnapshotSummary

from lkscaler_keda.policy import AutoscalerPolicy

pytestmark = pytest.mark.e2e


def _require_keda_stack() -> None:
    if os.environ.get("KEDA_E2E_RUNNING") != "1":
        pytest.skip("KEDA e2e stack not running. Use scripts/run_keda_e2e.sh")


def _namespace() -> str:
    return os.environ.get("KEDA_E2E_NAMESPACE", "livekit-system")


def _kubectl_get(resource: str, namespace: str, name: str) -> str:
    proc = subprocess.run(
        ["kubectl", "get", resource, name, "-n", namespace, "-o", "name"],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


def _kubectl_scale(name: str, replicas: int) -> None:
    subprocess.run(
        ["kubectl", "scale", "deployment", name, "-n", _namespace(), f"--replicas={replicas}"],
        check=True,
        capture_output=True,
        text=True,
    )


def _wait_for_ready_replicas(name: str, expected: int, timeout_sec: int = 120) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        proc = subprocess.run(
            [
                "kubectl",
                "get",
                "deployment",
                name,
                "-n",
                _namespace(),
                "-o",
                "jsonpath={.status.readyReplicas}",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        ready = int(proc.stdout.strip() or "0")
        if ready == expected:
            return
        time.sleep(2)

    raise AssertionError(f"deployment {name} did not reach {expected} ready replicas")


def test_keda_operator_ready() -> None:
    _require_keda_stack()
    result = _kubectl_get("deployment", "keda", "keda-operator")
    assert result == "deployment.apps/keda-operator"


def test_keda_scaledobject_and_target_exist() -> None:
    _require_keda_stack()

    scaled_object = _kubectl_get("scaledobject", _namespace(), "livekit-agents-keda")
    deployment = _kubectl_get("deployment", _namespace(), "livekit-agents")

    assert scaled_object == "scaledobject.keda.sh/livekit-agents-keda"
    assert deployment == "deployment.apps/livekit-agents"


def test_keda_workload_can_scale_up_and_down() -> None:
    _require_keda_stack()

    policy = AutoscalerPolicy(min_cluster_free_slots=4, scale_down_dwell_sec=900)
    scale_up_summary = ClusterSnapshotSummary(
        cluster_free_slots=3,
        idle_pod_count=0,
        snapshot_age_sec=1200,
        smallest_idle_pod_free_slots=None,
    )
    scale_down_summary = ClusterSnapshotSummary(
        cluster_free_slots=5,
        idle_pod_count=1,
        snapshot_age_sec=901,
        smallest_idle_pod_free_slots=1,
    )

    assert policy.evaluate(summary=scale_up_summary).scale_up is True
    assert policy.evaluate(summary=scale_down_summary).scale_down_allowed is True

    _wait_for_ready_replicas("livekit-agents", 2)

    _kubectl_scale("livekit-agents", 3)
    _wait_for_ready_replicas("livekit-agents", 3)

    _kubectl_scale("livekit-agents", 2)
    _wait_for_ready_replicas("livekit-agents", 2)