"""The shared room list every consumer derives occupancy from.

A worker writes one record per room it accepts and deletes it when the job ends, so the store -
not a worker's view of its own processes - is the authority on what the fleet is serving. A room
only counts while its owner still publishes a pod state, which is what retires the rooms of a
worker that died without cleaning up.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any, Protocol

from .models import RoomRecord
from .state import PodState


class RoomRegistry(Protocol):
    """The room slice of a coordination backend."""

    def publish_room(
        self,
        *,
        room_id: str,
        pod_id: str,
        job_id: str,
        started_at: datetime,
        connected_at: datetime | None = None,
    ) -> None: ...

    def remove_room(self, *, room_id: str) -> None: ...

    def read_rooms(self) -> list[dict[str, Any]]: ...


def decode_rooms(payloads: Iterable[Mapping[str, Any]]) -> list[RoomRecord]:
    """Store payloads as room records, skipping any payload missing a required field."""
    records: list[RoomRecord] = []
    for payload in payloads:
        try:
            records.append(
                RoomRecord(
                    room_id=str(payload["room_id"]),
                    pod_id=str(payload["pod_id"]),
                    job_id=str(payload["job_id"]),
                    started_at=datetime.fromisoformat(str(payload["started_at"])),
                    connected_at=_optional_time(payload.get("connected_at")),
                )
            )
        except (KeyError, ValueError):
            continue
    return records


def _optional_time(value: object) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def live_rooms(
    rooms: Iterable[RoomRecord], pod_states: Mapping[str, PodState]
) -> list[RoomRecord]:
    """Rooms whose owning pod still publishes state."""
    return [room for room in rooms if room.pod_id in pod_states]


def rooms_by_pod(
    rooms: Iterable[RoomRecord], pod_states: Mapping[str, PodState]
) -> dict[str, int]:
    """Live rooms per pod, for the `active_rooms` every pod publishes about itself."""
    counts: dict[str, int] = {pod_id: 0 for pod_id in pod_states}
    for room in live_rooms(rooms, pod_states):
        counts[room.pod_id] += 1
    return counts


def orphan_room_ids(
    rooms: Iterable[RoomRecord], pod_states: Mapping[str, PodState]
) -> list[str]:
    """Records left behind by pods whose state has expired; safe for any worker to delete."""
    return [room.room_id for room in rooms if room.pod_id not in pod_states]
