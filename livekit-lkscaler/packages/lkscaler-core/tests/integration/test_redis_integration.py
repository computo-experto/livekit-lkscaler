"""Integration test for the Redis backend against a real server.

Skipped unless LKSCALER_REDIS_URL points at a reachable Redis, so the default
unit/integration run stays hermetic. Use `make test-integration-redis` to start the
compose Redis and run this.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from lkscaler_core.admission import cleanup_unassigned_reservation, reserve_for_admission
from lkscaler_core.models import PodOccupancy, ReservationRecord
from lkscaler_core.redis import RedisClientAdapter, RedisStateStore
from lkscaler_core.state import PodState

pytestmark = pytest.mark.integration

URL_ENV = "LKSCALER_REDIS_URL"


def _url() -> str:
    url = os.environ.get(URL_ENV, "")
    if not url:
        pytest.skip(f"{URL_ENV} is not set; start Redis to run this test")
    return url


@pytest.fixture
def namespace() -> str:
    return f"itest-{int(datetime.now(UTC).timestamp())}-{os.getpid()}"


@pytest.fixture
def store(namespace: str) -> Iterator[RedisStateStore]:
    adapter = RedisClientAdapter(url=_url())
    adapter.connect()
    try:
        yield RedisStateStore(namespace=namespace, client=adapter)
    finally:
        adapter.close()


def test_reservation_races_resolve_on_the_server(store: RedisStateStore) -> None:
    now = datetime.now(UTC)

    first = reserve_for_admission(
        store=store,
        occupancy=PodOccupancy(active_rooms=0, reservations=0),
        pod_id="pod-a",
        job_id="job-1",
        room_target_n=2,
        overflow_margin=1,
        reservation_ttl_sec=30,
        now=now,
    )
    second = reserve_for_admission(
        store=store,
        occupancy=PodOccupancy(active_rooms=0, reservations=0),
        pod_id="pod-a",
        job_id="job-1",
        room_target_n=2,
        overflow_margin=1,
        reservation_ttl_sec=30,
        now=now,
    )

    assert first.accepted is True
    assert second.accepted is False
    assert second.reason == "reservation_create_failed"

    cleanup_unassigned_reservation(store=store, pod_id="pod-a", job_id="job-1")
    assert store.get(pod_id="pod-a", job_id="job-1") is None


def test_overflow_guard_still_applies_with_a_shared_store(store: RedisStateStore) -> None:
    result = reserve_for_admission(
        store=store,
        occupancy=PodOccupancy(active_rooms=2, reservations=1),
        pod_id="pod-a",
        job_id="job-overflow",
        room_target_n=2,
        overflow_margin=1,
        reservation_ttl_sec=30,
        now=datetime.now(UTC),
    )

    assert result.accepted is False
    assert result.reason == "overflow_guard"


def test_expiry_cleanup_round_trips_through_the_server(store: RedisStateStore) -> None:
    now = datetime.now(UTC)
    reservation = ReservationRecord(
        pod_id="pod-a",
        job_id="job-short",
        created_at=now,
        expires_at=now + timedelta(seconds=1),
    )
    assert store.create(reservation) is True

    removed = store.remove_expired(now=now + timedelta(seconds=2))

    assert removed == 1
    assert store.get(pod_id="pod-a", job_id="job-short") is None


def test_pod_states_are_visible_to_other_workers(store: RedisStateStore) -> None:
    stamp = datetime.now(UTC)
    store.publish_pod_state(
        PodState(pod_id="pod-a", free_slots=2, active_rooms=1, reservations=1, updated_at=stamp)
    )
    store.publish_pod_state(
        PodState(pod_id="pod-b", free_slots=0, active_rooms=4, reservations=0, updated_at=stamp)
    )

    assert store.free_slots_by_pod() == {"pod-a": 2, "pod-b": 0}
