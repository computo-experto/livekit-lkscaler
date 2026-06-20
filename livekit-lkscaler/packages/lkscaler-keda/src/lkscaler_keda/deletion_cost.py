from dataclasses import dataclass
from typing import Protocol


def choose_deletion_cost(
    *,
    active_rooms: int,
    reservations: int,
    idle_cost: int,
    busy_cost: int,
) -> int:
    if active_rooms < 0:
        raise ValueError("active_rooms must be >= 0")
    if reservations < 0:
        raise ValueError("reservations must be >= 0")

    return idle_cost if active_rooms == 0 and reservations == 0 else busy_cost


class _PodClient(Protocol):
    def patch_namespaced_pod(
        self, name: str, namespace: str, body: dict[str, object]
    ) -> object: ...


@dataclass(frozen=True)
class PodDeletionCostReconciler:
    namespace: str
    pod_client: _PodClient
    idle_pod_deletion_cost: int
    busy_pod_deletion_cost: int

    def reconcile_pod(self, *, pod_name: str, active_rooms: int, reservations: int) -> int:
        deletion_cost = choose_deletion_cost(
            active_rooms=active_rooms,
            reservations=reservations,
            idle_cost=self.idle_pod_deletion_cost,
            busy_cost=self.busy_pod_deletion_cost,
        )

        self.pod_client.patch_namespaced_pod(
            name=pod_name,
            namespace=self.namespace,
            body={
                "metadata": {
                    "annotations": {
                        "controller.kubernetes.io/pod-deletion-cost": str(deletion_cost)
                    }
                }
            },
        )

        return deletion_cost
