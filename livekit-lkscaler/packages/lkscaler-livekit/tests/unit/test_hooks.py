import asyncio
from dataclasses import dataclass

import pytest
from lkscaler_core import BinpackConfig, InMemoryReservationStore, PodOccupancy
from lkscaler_livekit import build_load_fnc, build_on_request_handler


@dataclass
class _FakeTracker:
    occupancy: PodOccupancy
    cluster_free_slots: dict[str, int]

    def get_local_occupancy(self) -> PodOccupancy:
        return self.occupancy

    def get_cluster_free_slots(self) -> dict[str, int]:
        return dict(self.cluster_free_slots)


class _FakeRequest:
    def __init__(self, *, request_id: str, accept_raises: bool = False) -> None:
        self.id = request_id
        self.accept_called = False
        self.reject_called = False
        self.accept_raises = accept_raises

    async def accept(self, **kwargs: object) -> None:
        _ = kwargs
        self.accept_called = True
        if self.accept_raises:
            raise RuntimeError("accept failed")

    async def reject(self, **kwargs: object) -> None:
        _ = kwargs
        self.reject_called = True


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


def test_build_load_fnc_returns_winner_signal() -> None:
    tracker = _FakeTracker(
        occupancy=PodOccupancy(active_rooms=1, reservations=0),
        cluster_free_slots={"pod-a": 1, "pod-b": 2},
    )
    load_fnc = build_load_fnc(config=_config(), store=InMemoryReservationStore(), tracker=tracker)
    assert load_fnc() == 0.0


def test_build_load_fnc_returns_loser_signal() -> None:
    tracker = _FakeTracker(
        occupancy=PodOccupancy(active_rooms=0, reservations=0),
        cluster_free_slots={"pod-a": 2, "pod-b": 1},
    )
    load_fnc = build_load_fnc(config=_config(), store=InMemoryReservationStore(), tracker=tracker)
    assert load_fnc() == 1.0


def test_on_request_rejects_when_overflow_guard_reached() -> None:
    tracker = _FakeTracker(
        occupancy=PodOccupancy(active_rooms=2, reservations=1),
        cluster_free_slots={"pod-a": 0},
    )
    request = _FakeRequest(request_id="job-1")
    handler = build_on_request_handler(_config(), InMemoryReservationStore(), tracker)

    asyncio.run(handler(request))

    assert request.reject_called is True
    assert request.accept_called is False


def test_on_request_accepts_after_reservation_creation() -> None:
    store = InMemoryReservationStore()
    tracker = _FakeTracker(
        occupancy=PodOccupancy(active_rooms=0, reservations=0),
        cluster_free_slots={"pod-a": 2},
    )
    request = _FakeRequest(request_id="job-2")
    handler = build_on_request_handler(_config(), store, tracker)

    asyncio.run(handler(request))

    assert request.accept_called is True
    assert store.get(pod_id="pod-a", job_id="job-2") is not None


def test_on_request_cleans_reservation_when_accept_raises() -> None:
    store = InMemoryReservationStore()
    tracker = _FakeTracker(
        occupancy=PodOccupancy(active_rooms=0, reservations=0),
        cluster_free_slots={"pod-a": 2},
    )
    request = _FakeRequest(request_id="job-3", accept_raises=True)
    handler = build_on_request_handler(_config(), store, tracker)

    with pytest.raises(RuntimeError, match="accept failed"):
        asyncio.run(handler(request))

    assert store.get(pod_id="pod-a", job_id="job-3") is None
