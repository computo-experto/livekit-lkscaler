from dataclasses import dataclass
from threading import Lock

from .load_signal import min_positive_free_slots
from .models import PodOccupancy


@dataclass(frozen=True)
class PodSnapshot:
    pod_id: str
    active_rooms: int
    reservations: int
    room_target_n: int

    def free_slots(self) -> int:
        return PodOccupancy(
            active_rooms=self.active_rooms,
            reservations=self.reservations,
        ).free_slots(room_target_n=self.room_target_n)

    def is_idle(self) -> bool:
        return self.active_rooms == 0 and self.reservations == 0


@dataclass(frozen=True)
class ClusterSnapshotSummary:
    cluster_free_slots: int
    idle_pod_count: int
    snapshot_age_sec: int
    smallest_idle_pod_free_slots: int | None = None


@dataclass(frozen=True)
class ClusterSnapshot:
    free_slots_by_pod: dict[str, int]

    def min_positive_free_slots(self) -> int | None:
        return min_positive_free_slots(self.free_slots_by_pod.values())


class ClusterSnapshotCache:
    def __init__(self) -> None:
        self._snapshot = ClusterSnapshot(free_slots_by_pod={})
        self._lock = Lock()

    def update(self, free_slots_by_pod: dict[str, int]) -> None:
        with self._lock:
            self._snapshot = ClusterSnapshot(free_slots_by_pod=dict(free_slots_by_pod))

    def get(self) -> ClusterSnapshot:
        with self._lock:
            return ClusterSnapshot(free_slots_by_pod=dict(self._snapshot.free_slots_by_pod))


def summarize_cluster_snapshot(
    pods: list[PodSnapshot],
    snapshot_at: int,
    observed_at: int,
) -> ClusterSnapshotSummary:
    cluster_free_slots = sum(pod.free_slots() for pod in pods)
    idle_pod_count = sum(1 for pod in pods if pod.is_idle())
    snapshot_age_sec = max(0, observed_at - snapshot_at)
    idle_pod_free_slots = [pod.free_slots() for pod in pods if pod.is_idle()]
    smallest_idle_pod_free_slots = min(idle_pod_free_slots) if idle_pod_free_slots else None

    return ClusterSnapshotSummary(
        cluster_free_slots=cluster_free_slots,
        idle_pod_count=idle_pod_count,
        snapshot_age_sec=snapshot_age_sec,
        smallest_idle_pod_free_slots=smallest_idle_pod_free_slots,
    )
