"""Coordination contracts shared by every backend.

A backend has to answer two questions for the placement logic: who holds a slot, and how
much room every worker in the cluster has left. `ReservationStore` (in `reservations`)
covers the first, including dropping records whose TTL has passed; `ClusterStateStore`
below covers the second. No backend semantics leak into the placement math.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class PodState:
    """What one worker publishes about itself for the rest of the cluster."""

    pod_id: str
    free_slots: int
    active_rooms: int
    reservations: int
    updated_at: datetime


class ClusterStateStore(Protocol):
    """Publishes this worker's occupancy and reads the cluster's."""

    def publish_pod_state(self, state: PodState) -> None: ...

    def read_pod_states(self) -> dict[str, PodState]: ...

    def free_slots_by_pod(self) -> dict[str, int]: ...
