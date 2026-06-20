import asyncio

import pytest
from lkscaler_core import BinpackConfig, InMemoryReservationStore, PodOccupancy
from lkscaler_livekit import build_load_fnc, build_on_request_handler


class _Tracker:
    def __init__(self, occupancy: PodOccupancy) -> None:
        self._occupancy = occupancy

    def get_local_occupancy(self) -> PodOccupancy:
        return self._occupancy

    def get_cluster_free_slots(self) -> dict[str, int]:
        return {"pod-a": self._occupancy.free_slots(room_target_n=2)}


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


def test_mocked_livekit_hook_flow_accepts() -> None:
    store = InMemoryReservationStore()
    tracker = _Tracker(occupancy=PodOccupancy(active_rooms=0, reservations=0))
    request = _Request("job-integration-accept")
    handler = build_on_request_handler(_config(), store, tracker)

    asyncio.run(handler(request))

    assert request.accepted is True
    assert request.rejected is False
    assert store.get(pod_id="pod-a", job_id="job-integration-accept") is not None


def test_mocked_livekit_hook_flow_rejects() -> None:
    store = InMemoryReservationStore()
    tracker = _Tracker(occupancy=PodOccupancy(active_rooms=2, reservations=1))
    request = _Request("job-integration-reject")
    handler = build_on_request_handler(_config(), store, tracker)

    asyncio.run(handler(request))

    assert request.accepted is False
    assert request.rejected is True
    assert store.get(pod_id="pod-a", job_id="job-integration-reject") is None


def test_mocked_livekit_hook_accept_failure_cleans_reservation() -> None:
    store = InMemoryReservationStore()
    tracker = _Tracker(occupancy=PodOccupancy(active_rooms=0, reservations=0))
    request = _Request("job-integration-fail", fail_accept=True)
    handler = build_on_request_handler(_config(), store, tracker)

    with pytest.raises(RuntimeError, match="simulated accept failure"):
        asyncio.run(handler(request))

    assert store.get(pod_id="pod-a", job_id="job-integration-fail") is None


def test_mocked_livekit_load_flow_winner_vs_loser() -> None:
    tracker_winner = _Tracker(occupancy=PodOccupancy(active_rooms=1, reservations=0))
    winner = build_load_fnc(_config(), InMemoryReservationStore(), tracker_winner)
    assert winner() == 0.0

    tracker_loser = _Tracker(occupancy=PodOccupancy(active_rooms=0, reservations=0))

    def get_cluster_free_slots_override() -> dict[str, int]:
        return {"pod-a": 2, "pod-b": 1}

    tracker_loser.get_cluster_free_slots = get_cluster_free_slots_override  # type: ignore[method-assign]
    loser = build_load_fnc(_config(), InMemoryReservationStore(), tracker_loser)
    assert loser() == 1.0
