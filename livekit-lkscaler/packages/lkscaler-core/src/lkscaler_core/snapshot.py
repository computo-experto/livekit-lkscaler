from dataclasses import dataclass
from threading import Lock

from .load_signal import min_positive_free_slots


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
