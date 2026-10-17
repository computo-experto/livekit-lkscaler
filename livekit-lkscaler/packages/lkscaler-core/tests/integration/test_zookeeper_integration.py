"""Integration test for the ZooKeeper backend against a real ensemble.

Skipped unless LKSCALER_ZK_HOSTS points at reachable ZooKeeper servers, so the
default unit/integration run stays hermetic. Use `make test-integration-zookeeper`
to start the compose ZooKeeper and run this.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from lkscaler_core.admission import cleanup_unassigned_reservation, reserve_for_admission
from lkscaler_core.models import PodOccupancy, ReservationRecord
from lkscaler_core.state import PodState
from lkscaler_core.zookeeper import KazooNodeClient, ZooKeeperStateStore

pytestmark = pytest.mark.integration

HOSTS_ENV = "LKSCALER_ZK_HOSTS"


def _hosts() -> list[str]:
    raw = os.environ.get(HOSTS_ENV, "")
    if not raw:
        pytest.skip(f"{HOSTS_ENV} is not set; start ZooKeeper to run this test")
    return [host.strip() for host in raw.split(",") if host.strip()]


@pytest.fixture
def namespace() -> str:
    return f"itest-{int(datetime.now(UTC).timestamp())}-{os.getpid()}"


@pytest.fixture
def store(namespace: str) -> Iterator[ZooKeeperStateStore]:
    client = KazooNodeClient(hosts=_hosts(), session_timeout_sec=10)
    client.start()
    try:
        yield ZooKeeperStateStore(namespace=namespace, client=client)
    finally:
        client.close()


def test_reservation_races_resolve_on_the_server(store: ZooKeeperStateStore) -> None:
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
    assert first.reason == "reserved"
    assert second.accepted is False
    assert second.reason == "reservation_create_failed"

    cleanup_unassigned_reservation(store=store, pod_id="pod-a", job_id="job-1")
    assert store.get(pod_id="pod-a", job_id="job-1") is None


def test_overflow_guard_still_applies_with_a_shared_store(store: ZooKeeperStateStore) -> None:
    now = datetime.now(UTC)

    result = reserve_for_admission(
        store=store,
        occupancy=PodOccupancy(active_rooms=2, reservations=1),
        pod_id="pod-a",
        job_id="job-overflow",
        room_target_n=2,
        overflow_margin=1,
        reservation_ttl_sec=30,
        now=now,
    )

    assert result.accepted is False
    assert result.reason == "overflow_guard"
    assert store.get(pod_id="pod-a", job_id="job-overflow") is None


def test_expiry_cleanup_round_trips_through_the_server(store: ZooKeeperStateStore) -> None:
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


def test_pod_states_are_visible_to_other_workers(store: ZooKeeperStateStore) -> None:
    now = datetime.now(UTC)
    store.publish_pod_state(
        PodState(
            pod_id="pod-a",
            free_slots=2,
            active_rooms=1,
            reservations=1,
            updated_at=now,
        )
    )
    store.publish_pod_state(
        PodState(
            pod_id="pod-b",
            free_slots=0,
            active_rooms=4,
            reservations=0,
            updated_at=now,
        )
    )

    assert store.free_slots_by_pod() == {"pod-a": 2, "pod-b": 0}
