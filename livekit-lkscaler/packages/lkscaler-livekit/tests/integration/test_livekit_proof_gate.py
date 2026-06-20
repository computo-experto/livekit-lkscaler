from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import perf_counter

import pytest
from lkscaler_core import BinpackConfig, InMemoryReservationStore, PodOccupancy
from lkscaler_livekit import build_on_request_handler

pytestmark = pytest.mark.proof


@dataclass
class _MutableTracker:
    occupancy: PodOccupancy

    def get_local_occupancy(self) -> PodOccupancy:
        return self.occupancy

    def get_cluster_free_slots(self) -> dict[str, int]:
        return {"pod-a": max(0, 2 - self.occupancy.occupied_slots()), "pod-b": 2}


class _Request:
    def __init__(self, request_id: str, *, fail_accept: bool = False) -> None:
        self.id = request_id
        self.accepted = False
        self.rejected = False
        self.fail_accept = fail_accept

    async def accept(self, **kwargs: object) -> None:
        _ = kwargs
        self.accepted = True
        if self.fail_accept:
            raise RuntimeError("simulated accept failure")

    async def reject(self, **kwargs: object) -> None:
        _ = kwargs
        self.rejected = True


def _config() -> BinpackConfig:
    return BinpackConfig(
        namespace="ns",
        pod_id="pod-a",
        room_target_n=2,
        overflow_margin=1,
        reservation_ttl_sec=30,
        zk_session_timeout_sec=10,
        sync_interval_ms=1000,
    )


def test_on_request_enforces_overflow_bound_under_churn() -> None:
    store = InMemoryReservationStore()
    tracker = _MutableTracker(PodOccupancy(active_rooms=0, reservations=0))
    handler = build_on_request_handler(_config(), store, tracker)

    # 2 + 0 occupied -> accepted
    req1 = _Request("job-proof-1")
    asyncio.run(handler(req1))
    assert req1.accepted is True

    # 2 + 1 occupied equals hard bound (N + overflow_margin) -> rejected
    tracker.occupancy = PodOccupancy(active_rooms=2, reservations=1)
    req2 = _Request("job-proof-2")
    asyncio.run(handler(req2))
    assert req2.accepted is False
    assert req2.rejected is True


def test_on_request_accept_failure_cleanup_latency() -> None:
    store = InMemoryReservationStore()
    tracker = _MutableTracker(PodOccupancy(active_rooms=0, reservations=0))
    handler = build_on_request_handler(_config(), store, tracker)
    req = _Request("job-proof-fail", fail_accept=True)

    started = perf_counter()
    with pytest.raises(RuntimeError, match="simulated accept failure"):
        asyncio.run(handler(req))
    elapsed = perf_counter() - started

    assert store.get(pod_id="pod-a", job_id="job-proof-fail") is None
    assert elapsed < 0.3, f"Accept-failure cleanup exceeded latency threshold: {elapsed:.3f}s"
