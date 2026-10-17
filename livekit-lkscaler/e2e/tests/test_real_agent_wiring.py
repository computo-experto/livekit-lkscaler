"""Wiring tests for the real-agent fixture, with no server and no backend.

They exist because the risky part of `real_agent.py` is the composition: which
`WorkerOptions` field carries the admission handler, how the tracker learns this
worker's active job count from the SDK, and whether the load value that reaches the
server is really the placement formula. All of that is checkable in-process.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from lkscaler_core import InMemoryReservationStore, PodOccupancy, ReservationRecord
from lkscaler_core.state import PodState

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "real_agent.py"


def _fixture() -> Any:
    spec = importlib.util.spec_from_file_location("real_agent_fixture", FIXTURE)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StubServer:
    def __init__(self, active_jobs: int = 0) -> None:
        self.active_jobs = [object() for _ in range(active_jobs)]


class StubClusterStore:
    def __init__(self, free_by_pod: dict[str, int]) -> None:
        self._free = dict(free_by_pod)
        self.published: list[PodState] = []

    def publish_pod_state(self, state: PodState) -> None:
        self.published.append(state)

    def free_slots_by_pod(self) -> dict[str, int]:
        return dict(self._free)

    def remove_expired(self, *, now: datetime) -> int:
        _ = now
        return 0


def _record(job_id: str, *, now: datetime, ttl_sec: int = 30) -> ReservationRecord:
    return ReservationRecord(
        pod_id="real-agent-1",
        job_id=job_id,
        created_at=now,
        expires_at=now + timedelta(seconds=ttl_sec),
    )


def test_tracker_counts_active_jobs_reported_by_the_sdk_server() -> None:
    fixture = _fixture()
    tracker = fixture.WorkerTracker(
        store=InMemoryReservationStore(), cluster_store=None, pod_id="real-agent-1"
    )

    tracker.attach(StubServer(active_jobs=2))

    assert tracker.get_local_occupancy().active_rooms == 2


def test_reservations_made_through_the_notifying_store_count_as_occupied() -> None:
    fixture = _fixture()
    inner = InMemoryReservationStore()
    tracker = fixture.WorkerTracker(store=inner, cluster_store=None, pod_id="real-agent-1")
    store = fixture.NotifyingReservationStore(inner=inner, tracker=tracker)
    now = datetime.now(UTC)

    assert store.create(_record("job-1", now=now)) is True
    assert tracker.get_local_occupancy().reservations == 1
    assert inner.get(pod_id="real-agent-1", job_id="job-1") is not None

    store.delete(pod_id="real-agent-1", job_id="job-1")

    assert tracker.get_local_occupancy().reservations == 0


def test_cluster_view_comes_from_the_backend_store() -> None:
    fixture = _fixture()
    cluster = StubClusterStore({"real-agent-1": 2, "real-agent-2": 0})
    tracker = fixture.WorkerTracker(
        store=InMemoryReservationStore(), cluster_store=cluster, pod_id="real-agent-1"
    )

    assert tracker.get_cluster_free_slots() == {"real-agent-1": 2, "real-agent-2": 0}


def test_expired_reservations_stop_counting() -> None:
    fixture = _fixture()
    tracker = fixture.WorkerTracker(
        store=InMemoryReservationStore(), cluster_store=None, pod_id="real-agent-1"
    )
    tracker.note_reservation(
        "job-old", _record("job-old", now=datetime.now(UTC) - timedelta(seconds=60), ttl_sec=1)
    )

    assert tracker.get_local_occupancy().reservations == 0


def test_build_worker_wires_the_hooks_and_threshold() -> None:
    fixture = _fixture()
    cluster = StubClusterStore({"real-agent-1": 2})
    backend = (InMemoryReservationStore(), cluster, None)

    options, tracker, returned_cluster, closer = fixture.build_worker(backend=backend)

    assert options.request_fnc is not None
    assert options.load_fnc is not None
    assert options.load_threshold == 0.7
    assert returned_cluster is cluster
    assert closer is None
    assert tracker is not None


def test_load_value_is_the_placement_formula() -> None:
    fixture = _fixture()
    cluster = StubClusterStore({"real-agent-1": 2, "real-agent-2": 1})
    backend = (InMemoryReservationStore(), cluster, None)
    options, tracker, _, _ = fixture.build_worker(backend=backend)
    load_one_arg = cast("Callable[[Any], float]", options.load_fnc)

    # Cluster minimum is 1 and this worker has one active job (free = 2 - 1), so it wins.
    assert load_one_arg(StubServer(active_jobs=1)) == 0.0

    cluster._free = {"real-agent-1": 1, "real-agent-2": 2}

    # Three active jobs put this worker over its target (free = 2 - 3 < 0), so it is not the winner.
    assert load_one_arg(StubServer(active_jobs=3)) == 1.0
    assert tracker.get_cluster_free_slots() == {"real-agent-1": 1, "real-agent-2": 2}


def test_publish_reports_free_slots_from_occupancy() -> None:
    fixture = _fixture()
    cluster = StubClusterStore({})

    fixture._publish(
        cluster,
        pod_id="real-agent-1",
        occupancy=PodOccupancy(active_rooms=2, reservations=1),
        room_target_n=3,
    )

    state = cluster.published[0]
    assert state.pod_id == "real-agent-1"
    assert state.free_slots == 0
    assert state.active_rooms == 2
    assert state.reservations == 1
