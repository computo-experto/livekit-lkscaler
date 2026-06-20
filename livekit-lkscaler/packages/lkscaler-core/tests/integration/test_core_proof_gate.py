from __future__ import annotations

from datetime import UTC, datetime, timedelta
from time import perf_counter

import pytest
from lkscaler_core.admission import cleanup_unassigned_reservation, reserve_for_admission
from lkscaler_core.load_signal import choose_load_signal, min_positive_free_slots
from lkscaler_core.models import PodOccupancy
from lkscaler_core.reservations import InMemoryReservationStore

pytestmark = pytest.mark.proof


def test_reservation_cleanup_latency_on_assignment_failure() -> None:
    store = InMemoryReservationStore()
    now = datetime.now(UTC)
    _ = reserve_for_admission(
        store=store,
        occupancy=PodOccupancy(active_rooms=0, reservations=0),
        pod_id="pod-a",
        job_id="job-latency",
        room_target_n=2,
        overflow_margin=1,
        reservation_ttl_sec=30,
        now=now,
    )
    assert store.get(pod_id="pod-a", job_id="job-latency") is not None

    started = perf_counter()
    cleanup_unassigned_reservation(store=store, pod_id="pod-a", job_id="job-latency")
    elapsed = perf_counter() - started

    assert store.get(pod_id="pod-a", job_id="job-latency") is None
    assert elapsed < 0.2, f"Cleanup exceeded latency threshold: {elapsed:.3f}s"


def test_expiry_cleanup_respects_ttl_boundary() -> None:
    store = InMemoryReservationStore()
    now = datetime.now(UTC)
    _ = store.create_with_ttl(pod_id="pod-a", job_id="job-ttl", ttl_sec=5, now=now)

    removed_early = store.remove_expired(now=now + timedelta(seconds=4))
    assert removed_early == 0
    assert store.get(pod_id="pod-a", job_id="job-ttl") is not None

    removed_on_deadline = store.remove_expired(now=now + timedelta(seconds=5))
    assert removed_on_deadline == 1
    assert store.get(pod_id="pod-a", job_id="job-ttl") is None


def test_binpack_trend_under_synthetic_churn() -> None:
    room_target_n = 3
    assigned_sequence: list[str] = []
    occupancy = {"pod-a": 0, "pod-b": 0}

    for _ in range(6):
        free_slots = {pod: room_target_n - used for pod, used in occupancy.items()}
        threshold = min_positive_free_slots(free_slots.values())

        winners = [
            pod
            for pod, free in free_slots.items()
            if choose_load_signal(local_free_slots=free, min_positive_free_slots=threshold) == 0.0
        ]
        assert winners, "Expected at least one winner pod"

        selected = "pod-a" if "pod-a" in winners else winners[0]
        assigned_sequence.append(selected)
        occupancy[selected] += 1

    assert assigned_sequence == ["pod-a", "pod-a", "pod-a", "pod-b", "pod-b", "pod-b"]
