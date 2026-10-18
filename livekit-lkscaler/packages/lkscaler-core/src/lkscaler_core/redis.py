"""Redis-backed coordination for LKScaler.

    livekit-binpack:{namespace}:pods:{pod_id}
    livekit-binpack:{namespace}:rooms:{room_id}
    livekit-binpack:{namespace}:reservations:{pod_id}:{job_id}

Keys carry a TTL, which is Redis' equivalent of the ZooKeeper ephemeral node: a worker
that dies stops refreshing its keys and disappears on its own, and a reservation that is
never completed expires without anybody sweeping it. `RedisStateStore` holds the
behaviour and is testable against any `RedisCommandClient`; `RedisClientAdapter` is the
only class that knows about redis-py, and it imports it on use.
"""

from __future__ import annotations

import fnmatch
import json
from datetime import UTC, datetime
from typing import Any, Protocol

from .models import ReservationRecord
from .reservations import ReservationStore
from .state import PodState

DEFAULT_POD_STATE_TTL_SEC = 30


def _validate_segment(value: str, *, name: str) -> str:
    trimmed = value.strip()
    if not trimmed:
        raise ValueError(f"{name} cannot be empty")
    if "/" in trimmed or ":" in trimmed:
        raise ValueError(f"{name} cannot contain '/' or ':'")
    return trimmed


class RedisKeys:
    """Key layout for one namespace."""

    def __init__(self, namespace: str) -> None:
        self._base = f"livekit-binpack:{_validate_segment(namespace, name='namespace')}"

    @property
    def base(self) -> str:
        return self._base

    def pod(self, pod_id: str) -> str:
        return f"{self._base}:pods:{_validate_segment(pod_id, name='pod_id')}"

    def room(self, room_id: str) -> str:
        return f"{self._base}:rooms:{_validate_segment(room_id, name='room_id')}"

    def reservation(self, pod_id: str, job_id: str) -> str:
        pod = _validate_segment(pod_id, name="pod_id")
        job = _validate_segment(job_id, name="job_id")
        return f"{self._base}:reservations:{pod}:{job}"

    def pods_pattern(self) -> str:
        return f"{self._base}:pods:*"

    def rooms_pattern(self) -> str:
        return f"{self._base}:rooms:*"

    def reservations_pattern(self) -> str:
        return f"{self._base}:reservations:*:*"


def _encode_payload(payload: dict[str, object]) -> bytes:
    return json.dumps(payload).encode()


def _decode_payload(data: bytes) -> dict[str, Any]:
    parsed: Any = json.loads(data.decode())
    if not isinstance(parsed, dict):
        raise ValueError("Redis payload must be a JSON object")
    return parsed


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _ttl_ms(*, created_at: datetime, expires_at: datetime) -> int:
    return max(1000, int((_as_utc(expires_at) - _as_utc(created_at)).total_seconds() * 1000))


class RedisStateStore(ReservationStore):
    """Reservations and published occupancy held in Redis."""

    def __init__(
        self,
        *,
        namespace: str,
        client: RedisCommandClient,
        pod_state_ttl_sec: int = DEFAULT_POD_STATE_TTL_SEC,
    ) -> None:
        if pod_state_ttl_sec <= 0:
            raise ValueError("pod_state_ttl_sec must be positive")
        self._keys = RedisKeys(namespace)
        self._client = client
        self._pod_state_ttl_ms = pod_state_ttl_sec * 1000

    def create(self, reservation: ReservationRecord) -> bool:
        return self._client.set_if_absent(
            self._keys.reservation(reservation.pod_id, reservation.job_id),
            _encode_payload(
                {
                    "pod_id": reservation.pod_id,
                    "job_id": reservation.job_id,
                    "created_at": reservation.created_at.isoformat(),
                    "expires_at": reservation.expires_at.isoformat(),
                }
            ),
            ttl_ms=_ttl_ms(created_at=reservation.created_at, expires_at=reservation.expires_at),
        )

    def delete(self, *, pod_id: str, job_id: str) -> None:
        self._client.delete(self._keys.reservation(pod_id, job_id))

    def get(self, *, pod_id: str, job_id: str) -> ReservationRecord | None:
        data = self._client.get_value(self._keys.reservation(pod_id, job_id))
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
        for key in self._client.scan_keys(self._keys.reservations_pattern()):
            data = self._client.get_value(key)
            if data is None:
                continue
            payload = _decode_payload(data)
            if datetime.fromisoformat(str(payload["expires_at"])) <= moment:
                removed += self._client.delete(key)
        return removed

    def publish_pod_state(self, state: PodState) -> None:
        self._client.set_value(
            self._keys.pod(state.pod_id),
            _encode_payload(
                {
                    "pod_id": state.pod_id,
                    "free_slots": state.free_slots,
                    "active_rooms": state.active_rooms,
                    "reservations": state.reservations,
                    "updated_at": state.updated_at.isoformat(),
                }
            ),
            ttl_ms=self._pod_state_ttl_ms,
        )

    def read_pod_states(self) -> dict[str, PodState]:
        states: dict[str, PodState] = {}
        for key in self._client.scan_keys(self._keys.pods_pattern()):
            data = self._client.get_value(key)
            if data is None:
                continue
            payload = _decode_payload(data)
            pod_id = key.rsplit(":", 1)[-1]
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

    def publish_room(
        self,
        *,
        room_id: str,
        pod_id: str,
        job_id: str,
        started_at: datetime,
        connected_at: datetime | None = None,
    ) -> None:
        # No TTL: a room outlives the pod-state window by design, and it is retired by its owner on
        # job finish or swept once the owner stops publishing state.
        self._client.set_value(
            self._keys.room(room_id),
            _encode_payload(
                {
                    "room_id": room_id,
                    "pod_id": pod_id,
                    "job_id": job_id,
                    "started_at": _as_utc(started_at).isoformat(),
                    "connected_at": None
                    if connected_at is None
                    else _as_utc(connected_at).isoformat(),
                }
            ),
            ttl_ms=None,
        )

    def remove_room(self, *, room_id: str) -> None:
        self._client.delete(self._keys.room(room_id))

    def read_rooms(self) -> list[dict[str, Any]]:
        rooms: list[dict[str, Any]] = []
        for key in self._client.scan_keys(self._keys.rooms_pattern()):
            data = self._client.get_value(key)
            if data is not None:
                rooms.append(_decode_payload(data))
        return rooms


class RedisCommandClient(Protocol):
    """The Redis operations the store needs, and nothing more."""

    def set_if_absent(self, key: str, value: bytes, *, ttl_ms: int) -> bool: ...

    def set_value(self, key: str, value: bytes, *, ttl_ms: int | None) -> None: ...

    def get_value(self, key: str) -> bytes | None: ...

    def delete(self, *keys: str) -> int: ...

    def scan_keys(self, pattern: str) -> list[str]: ...


class MemoryRedisClient:
    """A process-local `RedisCommandClient`, for tests and single-worker use.

    It honours `ttl_ms` against a supplied clock so expiry behaviour can be tested
    without sleeping.
    """

    def __init__(self) -> None:
        self._values: dict[str, bytes] = {}
        self._expires_at_ms: dict[str, int] = {}
        self._now_ms = 0

    def advance_ms(self, delta_ms: int) -> None:
        self._now_ms += delta_ms
        for key, deadline in list(self._expires_at_ms.items()):
            if deadline <= self._now_ms:
                self._values.pop(key, None)
                self._expires_at_ms.pop(key, None)

    def set_if_absent(self, key: str, value: bytes, *, ttl_ms: int) -> bool:
        self.advance_ms(0)
        if key in self._values:
            return False
        self._values[key] = value
        self._expires_at_ms[key] = self._now_ms + ttl_ms
        return True

    def set_value(self, key: str, value: bytes, *, ttl_ms: int | None) -> None:
        self._values[key] = value
        if ttl_ms is None:
            self._expires_at_ms.pop(key, None)
        else:
            self._expires_at_ms[key] = self._now_ms + ttl_ms

    def get_value(self, key: str) -> bytes | None:
        self.advance_ms(0)
        return self._values.get(key)

    def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if self._values.pop(key, None) is not None:
                self._expires_at_ms.pop(key, None)
                removed += 1
        return removed

    def scan_keys(self, pattern: str) -> list[str]:
        self.advance_ms(0)
        return sorted(key for key in self._values if fnmatch.fnmatchcase(key, pattern))


class RedisClientAdapter:
    """`RedisCommandClient` implemented on redis-py."""

    def __init__(self, *, url: str) -> None:
        self._url = url
        self._client: Any = None

    def connect(self) -> None:
        from redis import Redis

        client = Redis.from_url(self._url)
        client.ping()
        self._client = client

    def close(self) -> None:
        if self._client is None:
            return
        self._client.close()
        self._client = None

    def set_if_absent(self, key: str, value: bytes, *, ttl_ms: int) -> bool:
        return bool(self._client.set(key, value, nx=True, px=ttl_ms))

    def set_value(self, key: str, value: bytes, *, ttl_ms: int | None) -> None:
        self._client.set(key, value, px=ttl_ms)

    def get_value(self, key: str) -> bytes | None:
        data = self._client.get(key)
        return None if data is None else bytes(data)

    def delete(self, *keys: str) -> int:
        return int(self._client.delete(*keys))

    def scan_keys(self, pattern: str) -> list[str]:
        found: list[str] = []
        cursor = 0
        while True:
            cursor, batch = self._client.scan(cursor=cursor, match=pattern, count=100)
            for key in batch:
                found.append(key.decode() if isinstance(key, bytes) else str(key))
            if cursor == 0:
                return found
