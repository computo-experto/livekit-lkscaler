from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from lkscaler_core.models import ReservationRecord
from lkscaler_core.redis import MemoryRedisClient, RedisKeys, RedisStateStore
from lkscaler_core.state import PodState


def _store() -> tuple[RedisStateStore, MemoryRedisClient]:
    client = MemoryRedisClient()
    return RedisStateStore(namespace="demo", client=client), client


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


def test_key_layout_is_namespaced_and_validated() -> None:
    keys = RedisKeys(namespace="demo")

    assert keys.base == "livekit-binpack:demo"
    assert keys.pod("pod-a") == "livekit-binpack:demo:pods:pod-a"
    assert keys.room("room-1") == "livekit-binpack:demo:rooms:room-1"
    assert keys.reservation("pod-a", "job-1") == "livekit-binpack:demo:reservations:pod-a:job-1"
    assert keys.reservations_pattern() == "livekit-binpack:demo:reservations:*:*"

    with pytest.raises(ValueError):
        RedisKeys(namespace="")
    with pytest.raises(ValueError):
        RedisKeys(namespace="bad:namespace")


def test_second_reservation_for_same_job_loses_the_race() -> None:
    store, _ = _store()
    now = datetime(2026, 1, 1, tzinfo=UTC)

    assert store.create(_record("job-1", now=now)) is True
    assert store.create(_record("job-1", now=now)) is False


def test_get_round_trips_the_record_and_reads_missing_as_none() -> None:
    store, _ = _store()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    store.create(_record("job-1", now=now, ttl_sec=45))

    record = store.get(pod_id="pod-a", job_id="job-1")

    assert record is not None
    assert record.expires_at == now + timedelta(seconds=45)
    assert store.get(pod_id="pod-a", job_id="missing") is None


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


def test_reservation_key_ttl_matches_the_record_lifetime() -> None:
    client = MemoryRedisClient()
    store = RedisStateStore(namespace="demo", client=client)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    store.create(_record("job-1", now=now, ttl_sec=30))

    client.advance_ms(29_000)
    assert store.get(pod_id="pod-a", job_id="job-1") is not None

    client.advance_ms(2_000)
    assert store.get(pod_id="pod-a", job_id="job-1") is None


def test_pod_state_publish_read_and_update_in_place() -> None:
    store, client = _store()
    stamp = datetime(2026, 1, 1, tzinfo=UTC)
    store.publish_pod_state(
        PodState(pod_id="pod-a", free_slots=2, active_rooms=1, reservations=1, updated_at=stamp)
    )
    store.publish_pod_state(
        PodState(pod_id="pod-b", free_slots=0, active_rooms=4, reservations=0, updated_at=stamp)
    )

    assert store.free_slots_by_pod() == {"pod-a": 2, "pod-b": 0}

    store.publish_pod_state(
        PodState(pod_id="pod-a", free_slots=1, active_rooms=3, reservations=0, updated_at=stamp)
    )

    assert store.free_slots_by_pod() == {"pod-a": 1, "pod-b": 0}
    pods_for_a = [
        key for key in client.scan_keys("livekit-binpack:demo:pods:*") if key.endswith("pod-a")
    ]
    assert len(pods_for_a) == 1


def test_pod_state_disappears_after_its_ttl() -> None:
    client = MemoryRedisClient()
    store = RedisStateStore(namespace="demo", client=client, pod_state_ttl_sec=5)
    store.publish_pod_state(
        PodState(
            pod_id="pod-a",
            free_slots=2,
            active_rooms=0,
            reservations=0,
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )

    assert store.free_slots_by_pod() == {"pod-a": 2}

    client.advance_ms(6_000)

    assert store.free_slots_by_pod() == {}


def test_pod_state_ttl_must_be_positive() -> None:
    with pytest.raises(ValueError):
        RedisStateStore(namespace="demo", client=MemoryRedisClient(), pod_state_ttl_sec=0)


def test_room_publish_and_removal() -> None:
    store, _ = _store()
    started = datetime(2026, 1, 1, tzinfo=UTC)
    store.publish_room(room_id="room-1", pod_id="pod-a", job_id="job-1", started_at=started)

    assert store.read_rooms() == [
        {
            "room_id": "room-1",
            "pod_id": "pod-a",
            "job_id": "job-1",
            "started_at": started.isoformat(),
        }
    ]

    store.remove_room(room_id="room-1")

    assert store.read_rooms() == []


def test_a_room_record_outlives_the_pod_state_ttl() -> None:
    store, client = _store()
    store.publish_room(
        room_id="room-1",
        pod_id="pod-a",
        job_id="job-1",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    client.advance_ms(600_000)

    assert [room["room_id"] for room in store.read_rooms()] == ["room-1"]


def test_naive_timestamps_are_treated_as_utc() -> None:
    store, _ = _store()
    store.create(_record("job-1", now=datetime(2026, 1, 1, tzinfo=UTC), ttl_sec=30))

    assert store.remove_expired(now=datetime(2026, 1, 1, 0, 0, 31)) == 1


def test_keys_vanishing_mid_scan_are_skipped() -> None:
    class GhostKeyClient(MemoryRedisClient):
        def scan_keys(self, pattern: str) -> list[str]:
            return [*super().scan_keys(pattern), f"{pattern[:-1]}-ghost"]

    client = GhostKeyClient()
    store = RedisStateStore(namespace="demo", client=client)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    store.create(_record("job-1", now=now, ttl_sec=1))
    store.publish_pod_state(
        PodState(pod_id="pod-a", free_slots=1, active_rooms=0, reservations=0, updated_at=now)
    )
    store.publish_room(room_id="room-1", pod_id="pod-a", job_id="job-1", started_at=now)

    assert store.remove_expired(now=now + timedelta(seconds=2)) == 1
    assert sorted(store.read_pod_states()) == ["pod-a"]
    assert len(store.read_rooms()) == 1


def test_json_that_is_not_an_object_is_rejected() -> None:
    store, client = _store()
    client.set_value("livekit-binpack:demo:reservations:pod-a:job-1", b"[1, 2]", ttl_ms=1000)

    with pytest.raises(ValueError, match="must be a JSON object"):
        store.get(pod_id="pod-a", job_id="job-1")
