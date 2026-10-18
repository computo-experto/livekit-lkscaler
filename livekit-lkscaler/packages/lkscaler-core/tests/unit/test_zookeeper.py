from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from lkscaler_core.models import ReservationRecord
from lkscaler_core.state import PodState
from lkscaler_core.zookeeper import ZooKeeperStateStore


class FakeNodeClient:
    """In-memory stand-in for a ZooKeeper connection, with znode semantics."""

    def __init__(self) -> None:
        self.nodes: dict[str, bytes] = {}

    def start(self) -> None: ...

    def close(self) -> None: ...

    def create_if_absent(self, path: str, data: bytes, *, ephemeral: bool) -> bool:
        _ = ephemeral
        if path in self.nodes:
            return False
        self.nodes[path] = data
        return True

    def upsert(self, path: str, data: bytes, *, ephemeral: bool) -> None:
        _ = ephemeral
        self.nodes[path] = data

    def read(self, path: str) -> bytes | None:
        return self.nodes.get(path)

    def remove(self, path: str) -> None:
        self.nodes.pop(path, None)

    def children(self, path: str) -> list[str]:
        prefix = f"{path}/"
        children: set[str] = set()
        for node in self.nodes:
            if node.startswith(prefix):
                children.add(node[len(prefix) :].split("/", 1)[0])
        return sorted(children)


def _store() -> tuple[ZooKeeperStateStore, FakeNodeClient]:
    client = FakeNodeClient()
    return ZooKeeperStateStore(namespace="demo", client=client), client


def _record(
    job_id: str,
    *,
    now: datetime,
    ttl_sec: int = 30,
    pod_id: str = "pod-a",
) -> ReservationRecord:
    return ReservationRecord(
        pod_id=pod_id,
        job_id=job_id,
        created_at=now,
        expires_at=now + timedelta(seconds=ttl_sec),
    )


def test_reservation_paths_follow_the_documented_layout() -> None:
    store, client = _store()
    now = datetime(2026, 1, 1, tzinfo=UTC)

    assert store.create(_record("job-1", now=now)) is True

    assert "/livekit-binpack/demo/reservations/pod-a/job-1" in client.nodes


def test_second_reservation_for_same_job_loses_the_race() -> None:
    store, _ = _store()
    now = datetime(2026, 1, 1, tzinfo=UTC)

    assert store.create(_record("job-1", now=now)) is True
    assert store.create(_record("job-1", now=now)) is False


def test_get_round_trips_the_record() -> None:
    store, _ = _store()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    store.create(_record("job-1", now=now, ttl_sec=45))

    record = store.get(pod_id="pod-a", job_id="job-1")

    assert record is not None
    assert record.pod_id == "pod-a"
    assert record.job_id == "job-1"
    assert record.expires_at == now + timedelta(seconds=45)


def test_missing_reservation_reads_as_none() -> None:
    store, _ = _store()

    assert store.get(pod_id="pod-a", job_id="absent") is None


def test_delete_is_idempotent() -> None:
    store, _ = _store()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    store.create(_record("job-1", now=now))

    store.delete(pod_id="pod-a", job_id="job-1")
    store.delete(pod_id="pod-a", job_id="job-1")

    assert store.get(pod_id="pod-a", job_id="job-1") is None


def test_only_expired_reservations_are_removed() -> None:
    store, _ = _store()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    store.create(_record("short", now=now, ttl_sec=10))
    store.create(_record("long", now=now, ttl_sec=600, pod_id="pod-b"))

    removed = store.remove_expired(now=now + timedelta(seconds=30))

    assert removed == 1
    assert store.get(pod_id="pod-a", job_id="short") is None
    assert store.get(pod_id="pod-b", job_id="long") is not None


def test_remove_expired_at_the_exact_deadline_removes_once() -> None:
    store, _ = _store()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    store.create(_record("job-1", now=now, ttl_sec=30))
    deadline = now + timedelta(seconds=30)

    assert store.remove_expired(now=deadline) == 1
    assert store.remove_expired(now=deadline) == 0


def test_naive_timestamps_are_treated_as_utc() -> None:
    store, _ = _store()
    store.create(_record("job-1", now=datetime(2026, 1, 1, tzinfo=UTC), ttl_sec=30))

    assert store.remove_expired(now=datetime(2026, 1, 1, 0, 0, 31)) == 1


def test_pod_state_publish_and_read_back() -> None:
    store, _ = _store()
    store.publish_pod_state(
        PodState(
            pod_id="pod-a",
            free_slots=2,
            active_rooms=1,
            reservations=1,
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    store.publish_pod_state(
        PodState(
            pod_id="pod-b",
            free_slots=0,
            active_rooms=4,
            reservations=0,
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )

    states = store.read_pod_states()

    assert sorted(states) == ["pod-a", "pod-b"]
    assert states["pod-a"].free_slots == 2
    assert states["pod-b"].free_slots == 0
    assert store.free_slots_by_pod() == {"pod-a": 2, "pod-b": 0}


def test_republishing_a_pod_state_updates_in_place() -> None:
    store, client = _store()
    store.publish_pod_state(
        PodState(
            pod_id="pod-a",
            free_slots=3,
            active_rooms=1,
            reservations=0,
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    store.publish_pod_state(
        PodState(
            pod_id="pod-a",
            free_slots=1,
            active_rooms=3,
            reservations=0,
            updated_at=datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
        )
    )

    assert store.free_slots_by_pod() == {"pod-a": 1}
    assert sum(1 for node in client.nodes if node.endswith("/pods/pod-a")) == 1


def test_room_publish_and_removal() -> None:
    store, _ = _store()
    started = datetime(2026, 1, 1, tzinfo=UTC)
    store.publish_room(room_id="room-1", pod_id="pod-a", job_id="job-1", started_at=started)

    rooms = store.read_rooms()

    assert rooms == [
        {
            "room_id": "room-1",
            "pod_id": "pod-a",
            "job_id": "job-1",
            "started_at": started.isoformat(),
            "connected_at": None,
        }
    ]

    store.remove_room(room_id="room-1")

    assert store.read_rooms() == []


def test_store_satisfies_the_expiring_reservation_contract() -> None:
    store, _ = _store()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert store.create(_record("job-1", now=now)) is True
    assert store.remove_expired(now=now + timedelta(seconds=60)) == 1


def test_malformed_node_payload_is_rejected() -> None:
    store, client = _store()
    client.nodes["/livekit-binpack/demo/reservations/pod-a/job-1"] = b"not-json"

    with pytest.raises(ValueError):
        store.get(pod_id="pod-a", job_id="job-1")


def test_json_that_is_not_an_object_is_rejected() -> None:
    store, client = _store()
    client.nodes["/livekit-binpack/demo/reservations/pod-a/job-1"] = b"[1, 2]"

    with pytest.raises(ValueError, match="must be a JSON object"):
        store.get(pod_id="pod-a", job_id="job-1")


def test_pod_listed_but_vanished_mid_read_is_skipped() -> None:
    store, client = _store()
    stamp = datetime(2026, 1, 1, tzinfo=UTC)
    store.publish_pod_state(
        PodState(pod_id="pod-a", free_slots=2, active_rooms=0, reservations=0, updated_at=stamp)
    )
    store.publish_pod_state(
        PodState(pod_id="pod-b", free_slots=1, active_rooms=0, reservations=0, updated_at=stamp)
    )

    class VanishingClient(FakeNodeClient):
        def read(self, path: str) -> bytes | None:
            if path.endswith("/pods/pod-b"):
                return None
            return super().read(path)

    hiding = VanishingClient()
    hiding.nodes.update(client.nodes)
    store._client = hiding

    assert sorted(store.read_pod_states()) == ["pod-a"]
