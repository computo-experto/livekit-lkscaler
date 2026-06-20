from datetime import UTC, datetime

from lkscaler_core.admission import cleanup_unassigned_reservation, reserve_for_admission
from lkscaler_core.models import PodOccupancy
from lkscaler_core.reservations import InMemoryReservationStore


def test_rejects_when_overflow_guard_reached_with_greater_or_equal() -> None:
    store = InMemoryReservationStore()
    result = reserve_for_admission(
        store=store,
        occupancy=PodOccupancy(active_rooms=3, reservations=0),
        pod_id="pod-1",
        job_id="job-1",
        room_target_n=2,
        overflow_margin=1,
        reservation_ttl_sec=10,
        now=datetime.now(UTC),
    )

    assert result.accepted is False
    assert result.reason == "overflow_guard"


def test_reservation_is_created_before_accept_path() -> None:
    store = InMemoryReservationStore()
    result = reserve_for_admission(
        store=store,
        occupancy=PodOccupancy(active_rooms=0, reservations=0),
        pod_id="pod-1",
        job_id="job-1",
        room_target_n=2,
        overflow_margin=1,
        reservation_ttl_sec=10,
        now=datetime.now(UTC),
    )

    assert result.accepted is True
    assert store.get(pod_id="pod-1", job_id="job-1") is not None


def test_cleanup_unassigned_reservation_removes_record() -> None:
    store = InMemoryReservationStore()
    _ = reserve_for_admission(
        store=store,
        occupancy=PodOccupancy(active_rooms=0, reservations=0),
        pod_id="pod-1",
        job_id="job-1",
        room_target_n=2,
        overflow_margin=1,
        reservation_ttl_sec=10,
        now=datetime.now(UTC),
    )

    cleanup_unassigned_reservation(store=store, pod_id="pod-1", job_id="job-1")
    assert store.get(pod_id="pod-1", job_id="job-1") is None
