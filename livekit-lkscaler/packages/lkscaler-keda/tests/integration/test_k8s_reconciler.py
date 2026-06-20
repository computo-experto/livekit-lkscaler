from lkscaler_keda.deletion_cost import PodDeletionCostReconciler


class _FakePodClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    def patch_namespaced_pod(self, name: str, namespace: str, body: dict[str, object]) -> object:
        self.calls.append((name, namespace, body))
        return {"status": "ok"}


class _FailingPodClient:
    def patch_namespaced_pod(self, name: str, namespace: str, body: dict[str, object]) -> object:
        raise RuntimeError("patch failed")


def test_reconciler_patches_idle_and_busy_pod_deletion_cost_annotations() -> None:
    client = _FakePodClient()
    reconciler = PodDeletionCostReconciler(
        namespace="default",
        pod_client=client,
        idle_pod_deletion_cost=0,
        busy_pod_deletion_cost=100,
    )

    idle_cost = reconciler.reconcile_pod(pod_name="agent-0", active_rooms=0, reservations=0)
    busy_cost = reconciler.reconcile_pod(pod_name="agent-1", active_rooms=1, reservations=0)

    assert idle_cost == 0
    assert busy_cost == 100

    assert client.calls[0][0] == "agent-0"
    assert client.calls[0][1] == "default"
    assert client.calls[0][2] == {
        "metadata": {
            "annotations": {
                "controller.kubernetes.io/pod-deletion-cost": "0",
            }
        }
    }

    assert client.calls[1][0] == "agent-1"
    assert client.calls[1][1] == "default"
    assert client.calls[1][2] == {
        "metadata": {
            "annotations": {
                "controller.kubernetes.io/pod-deletion-cost": "100",
            }
        }
    }


def test_reconciler_propagates_patch_errors() -> None:
    reconciler = PodDeletionCostReconciler(
        namespace="default",
        pod_client=_FailingPodClient(),
        idle_pod_deletion_cost=0,
        busy_pod_deletion_cost=100,
    )

    try:
        reconciler.reconcile_pod(pod_name="agent-0", active_rooms=0, reservations=0)
    except RuntimeError as exc:
        assert str(exc) == "patch failed"
    else:
        raise AssertionError("expected RuntimeError")