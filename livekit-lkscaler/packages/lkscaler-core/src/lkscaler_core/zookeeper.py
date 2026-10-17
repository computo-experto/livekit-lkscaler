"""ZooKeeper-backed coordination for LKScaler.

Node layout, from the design spec:

    /livekit-binpack/{namespace}/pods/{pod_id}
    /livekit-binpack/{namespace}/rooms/{room_id}
    /livekit-binpack/{namespace}/reservations/{pod_id}/{job_id}

`ZooKeeperStateStore` holds the behaviour and is testable against any
`ZooKeeperNodeClient`. `KazooNodeClient` is the only class that knows about
kazoo, and it imports kazoo on use so a base install without the optional
`zookeeper` extra can still import this module.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

from .models import ReservationRecord
from .paths import ZkPaths
from .reservations import ReservationStore
from .state import PodState


class ZooKeeperNodeClient(Protocol):
    """The node operations the store needs, and nothing more."""

    def start(self) -> None: ...

    def close(self) -> None: ...

    def create_if_absent(self, path: str, data: bytes, *, ephemeral: bool) -> bool: ...

    def upsert(self, path: str, data: bytes, *, ephemeral: bool) -> None: ...

    def read(self, path: str) -> bytes | None: ...

    def remove(self, path: str) -> None: ...

    def children(self, path: str) -> list[str]: ...


def _encode_payload(payload: Mapping[str, object]) -> bytes:
    return json.dumps(payload).encode()


def _decode_payload(data: bytes) -> dict[str, Any]:
    parsed: Any = json.loads(data.decode())
    if not isinstance(parsed, dict):
        raise ValueError("ZooKeeper node payload must be a JSON object")
    return parsed


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class ZooKeeperStateStore(ReservationStore):
    """Reservations and published occupancy held in ZooKeeper."""

    def __init__(self, *, namespace: str, client: ZooKeeperNodeClient) -> None:
        self._paths = ZkPaths(namespace)
        self._client = client

    def create(self, reservation: ReservationRecord) -> bool:
        payload = {
            "pod_id": reservation.pod_id,
            "job_id": reservation.job_id,
            "created_at": reservation.created_at.isoformat(),
            "expires_at": reservation.expires_at.isoformat(),
        }
        return self._client.create_if_absent(
            self._paths.reservation_node(reservation.pod_id, reservation.job_id),
            _encode_payload(payload),
            ephemeral=True,
        )

    def delete(self, *, pod_id: str, job_id: str) -> None:
        self._client.remove(self._paths.reservation_node(pod_id, job_id))

    def get(self, *, pod_id: str, job_id: str) -> ReservationRecord | None:
        data = self._client.read(self._paths.reservation_node(pod_id, job_id))
        if data is None:
            return None
        payload = _decode_payload(data)
        return ReservationRecord(
            pod_id=str(payload["pod_id"]),
            job_id=str(payload["job_id"]),
            created_at=datetime.fromisoformat(str(payload["created_at"])),
            expires_at=datetime.fromisoformat(str(payload["expires_at"])),
        )

    def remove_expired(self, *, now: datetime) -> int:
        moment = _as_utc(now)
        removed = 0
        for pod_id in self._client.children(self._reservations_root()):
            for job_id in self._client.children(self._paths.reservation_parent(pod_id)):
                record = self.get(pod_id=pod_id, job_id=job_id)
                if record is not None and record.is_expired(now=moment):
                    self.delete(pod_id=pod_id, job_id=job_id)
                    removed += 1
        return removed

    def publish_pod_state(self, state: PodState) -> None:
        payload = {
            "pod_id": state.pod_id,
            "free_slots": state.free_slots,
            "active_rooms": state.active_rooms,
            "reservations": state.reservations,
            "updated_at": state.updated_at.isoformat(),
        }
        self._client.upsert(
            self._paths.pod_node(state.pod_id),
            _encode_payload(payload),
            ephemeral=True,
        )

    def read_pod_states(self) -> dict[str, PodState]:
        states: dict[str, PodState] = {}
        for pod_id in self._client.children(self._pods_root()):
            data = self._client.read(self._paths.pod_node(pod_id))
            if data is None:
                continue
            payload = _decode_payload(data)
            states[pod_id] = PodState(
                pod_id=pod_id,
                free_slots=int(payload["free_slots"]),
                active_rooms=int(payload["active_rooms"]),
                reservations=int(payload["reservations"]),
                updated_at=datetime.fromisoformat(str(payload["updated_at"])),
            )
        return states

    def free_slots_by_pod(self) -> dict[str, int]:
        return {pod_id: state.free_slots for pod_id, state in self.read_pod_states().items()}

    def publish_room(self, *, room_id: str, pod_id: str, job_id: str, started_at: datetime) -> None:
        payload = {
            "room_id": room_id,
            "pod_id": pod_id,
            "job_id": job_id,
            "started_at": _as_utc(started_at).isoformat(),
        }
        self._client.upsert(
            self._paths.room_node(room_id),
            _encode_payload(payload),
            ephemeral=True,
        )

    def remove_room(self, *, room_id: str) -> None:
        self._client.remove(self._paths.room_node(room_id))

    def read_rooms(self) -> list[dict[str, Any]]:
        rooms: list[dict[str, Any]] = []
        for room_id in self._client.children(self._rooms_root()):
            data = self._client.read(self._paths.room_node(room_id))
            if data is not None:
                rooms.append(_decode_payload(data))
        return rooms

    def _pods_root(self) -> str:
        return f"{self._paths.base}/pods"

    def _rooms_root(self) -> str:
        return f"{self._paths.base}/rooms"

    def _reservations_root(self) -> str:
        return f"{self._paths.base}/reservations"


class KazooNodeClient:
    """`ZooKeeperNodeClient` implemented on kazoo.

    Kazoo raises for control flow (node exists, node missing); this class is where
    those become the booleans and `None` the store expects, so no other module has
    to know about kazoo.
    """

    def __init__(self, *, hosts: Sequence[str], session_timeout_sec: int = 10) -> None:
        self._hosts = ",".join(hosts)
        self._session_timeout_sec = session_timeout_sec
        self._client: Any = None

    def start(self) -> None:
        from kazoo.client import KazooClient

        client = KazooClient(hosts=self._hosts, timeout=self._session_timeout_sec)
        client.start(timeout=max(5, self._session_timeout_sec))
        self._client = client

    def close(self) -> None:
        if self._client is None:
            return
        self._client.stop()
        self._client.close()
        self._client = None

    def create_if_absent(self, path: str, data: bytes, *, ephemeral: bool) -> bool:
        from kazoo.exceptions import NodeExistsError

        try:
            self._client.create(path, data, ephemeral=ephemeral, makepath=True)
        except NodeExistsError:
            return False
        return True

    def upsert(self, path: str, data: bytes, *, ephemeral: bool) -> None:
        from kazoo.exceptions import NodeExistsError

        try:
            self._client.create(path, data, ephemeral=ephemeral, makepath=True)
            return
        except NodeExistsError:
            pass
        self._client.set(path, data)

    def read(self, path: str) -> bytes | None:
        from kazoo.exceptions import NoNodeError

        try:
            data, _stat = self._client.get(path)
        except NoNodeError:
            return None
        return bytes(data)

    def remove(self, path: str) -> None:
        from kazoo.exceptions import NoNodeError

        try:
            self._client.delete(path)
        except NoNodeError:
            return

    def children(self, path: str) -> list[str]:
        from kazoo.exceptions import NoNodeError

        try:
            return [str(child) for child in self._client.get_children(path)]
        except NoNodeError:
            return []
