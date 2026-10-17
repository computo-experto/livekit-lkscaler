"""Coordination contracts shared by every backend.

A backend has to answer two questions for the placement logic: who holds a slot,
and how much room every worker in the cluster has left. `ReservationStore` covers
the first; `ClusterStateStore` and `ExpiringReservationStore` below cover the rest,
so no backend semantics leak into the placement math.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .models import ReservationRecord


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


class ExpiringReservationStore(Protocol):
    """Reservation store whose records carry a TTL and are cleaned up on demand."""

    def create(self, reservation: ReservationRecord) -> bool: ...

    def delete(self, *, pod_id: str, job_id: str) -> None: ...

    def get(self, *, pod_id: str, job_id: str) -> ReservationRecord | None: ...

    def remove_expired(self, *, now: datetime) -> int: ...
