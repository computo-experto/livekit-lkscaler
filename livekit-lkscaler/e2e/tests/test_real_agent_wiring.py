"""Wiring tests for the real-agent fixture, with no server and no backend.

They exist because the risky part of `real_agent.py` is the composition: which
`WorkerOptions` field carries the admission handler, how the tracker learns this
worker's active job count from the SDK, and whether the load value that reaches the
server is really the placement formula. All of that is checkable in-process.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from lkscaler_core import InMemoryReservationStore, ReservationRecord
from lkscaler_core.state import PodState

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "real_agent.py"
_POD_ID = "real-agent-1"
_PEER_ID = f"{_POD_ID}-peer"


def _fixture() -> Any:
    spec = importlib.util.spec_from_file_location("real_agent_fixture", FIXTURE)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class StubServer:
    def __init__(self, active_jobs: int = 0, job_ids: tuple[str, ...] | None = None) -> None:
        ids = job_ids if job_ids is not None else tuple(f"job-{i}" for i in range(active_jobs))
        self.active_jobs = [SimpleNamespace(job=SimpleNamespace(id=job_id)) for job_id in ids]


class StubJobContext:
    def __init__(self, job_id: str) -> None:
        self.job = SimpleNamespace(id=job_id)

    async def connect(self) -> None:
        return None


class StubClusterStore:
    def __init__(self, free_by_pod: dict[str, int]) -> None:
        self._free = dict(free_by_pod)
        self.published: list[PodState] = []
        self.rooms: dict[str, dict[str, Any]] = {}

    def publish_pod_state(self, state: PodState) -> None:
        self.published.append(state)

    def read_pod_states(self) -> dict[str, PodState]:
        return {state.pod_id: state for state in self.published}

    def free_slots_by_pod(self) -> dict[str, int]:
        return dict(self._free)

    def remove_expired(self, *, now: datetime) -> int:
        _ = now
        return 0

    def publish_room(
        self, *, room_id: str, pod_id: str, job_id: str, started_at: datetime
    ) -> None:
        self.rooms[room_id] = {
            "room_id": room_id,
            "pod_id": pod_id,
            "job_id": job_id,
            "started_at": started_at.isoformat(),
        }

    def remove_room(self, *, room_id: str) -> None:
        self.rooms.pop(room_id, None)

    def read_rooms(self) -> list[dict[str, Any]]:
        return list(self.rooms.values())


def _record(job_id: str, *, now: datetime, ttl_sec: int = 30) -> ReservationRecord:
    return ReservationRecord(
        pod_id=_POD_ID,
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


def test_a_running_job_is_not_counted_as_its_own_reservation() -> None:
    """The handler reserves, then the job starts; a started job is a room, not a claim."""
    fixture = _fixture()
    inner = InMemoryReservationStore()
    tracker = fixture.WorkerTracker(store=inner, cluster_store=None, pod_id=_POD_ID)
    store = fixture.NotifyingReservationStore(inner=inner, tracker=tracker)
    now = datetime.now(UTC)

    assert store.create(_record("job-run", now=now)) is True
    assert tracker.get_local_occupancy().reservations == 1

    tracker.attach(StubServer(active_jobs=1, job_ids=("job-run",)))

    occupancy = tracker.get_local_occupancy()

    assert occupancy.active_rooms == 1
    assert occupancy.reservations == 0
    assert occupancy.free_slots(room_target_n=2) == 1


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


def test_load_value_is_the_unique_winner_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LKSCALER_POD_ID", _POD_ID)
    fixture = _fixture()
    cluster = StubClusterStore({_POD_ID: 2, _PEER_ID: 1})
    backend = (InMemoryReservationStore(), cluster, None)
    options, tracker, _, _ = fixture.build_worker(backend=backend)
    load_one_arg = cast("Callable[[Any], float]", options.load_fnc)

    # The peer holds the fewest free slots, so the server has no reason to offer here.
    assert load_one_arg(StubServer(active_jobs=1)) == 1.0

    # Once this worker is the most loaded pod with room, it is the one job offers land on.
    cluster._free = {_POD_ID: 1, _PEER_ID: 3}
    assert load_one_arg(StubServer(active_jobs=1)) == 0.0

    # Two equally free pods must not both advertise; the lower pod id is the winner.
    cluster._free = {_POD_ID: 2, _PEER_ID: 2}
    assert _POD_ID < _PEER_ID
    assert load_one_arg(StubServer(active_jobs=1)) == 0.0

    # A worker with no free slots stops advertising itself and the peer takes over.
    cluster._free = {_POD_ID: 0, _PEER_ID: 2}
    assert load_one_arg(StubServer(active_jobs=1)) == 1.0
    assert tracker.get_cluster_free_slots() == {_POD_ID: 0, _PEER_ID: 2}


def test_publish_reports_free_slots_from_occupancy() -> None:
    fixture = _fixture()
    cluster = StubClusterStore({})
    backend = (InMemoryReservationStore(), cluster, None)
    _, tracker, _, _ = fixture.build_worker(backend=backend)
    tracker.attach(StubServer(active_jobs=0))
    runtime = fixture._ensure_runtime()
    # Occupancy comes from the shared room list, so the store is what says two rooms are live.
    for room in ("m9-a", "m9-b"):
        cluster.publish_room(
            room_id=room,
            pod_id=runtime.config.pod_id,
            job_id=f"job-{room}",
            started_at=datetime.now(UTC),
        )
    # A claim for a job the server is not running yet: only those count as reservations.
    tracker.note_reservation("job-pending", _record("job-pending", now=datetime.now(UTC)))

    fixture.publish(runtime)

    state = cluster.published[0]
    assert state.pod_id == runtime.config.pod_id
    assert state.active_rooms == 2
    assert state.reservations == 1
    assert state.free_slots == runtime.config.room_target_n - 3


@pytest.mark.asyncio
async def test_entrypoint_in_a_job_process_releases_the_reservation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture()
    inner = InMemoryReservationStore()
    backend = (inner, None, None)
    monkeypatch.setenv("LKSCALER_POD_ID", _POD_ID)
    _, tracker, _, _ = fixture.build_worker(backend=backend)
    now = datetime.now(UTC)
    record = _record("job-1", now=now)
    assert inner.create(record) is True
    tracker.note_reservation("job-1", record)

    # A job process starts with no runtime and must build its own, exactly as the SDK
    # spawns it; the reservation it releases is the one the parent's handler created.
    fixture._runtime = None
    monkeypatch.setattr(fixture, "_build_backend", lambda: backend)
    job = asyncio.create_task(fixture.entrypoint(StubJobContext("job-1")))
    try:
        await asyncio.wait_for(_await_gone(inner, "job-1"), timeout=5)
    finally:
        job.cancel()

    assert inner.get(pod_id=record.pod_id, job_id="job-1") is None
    assert fixture._runtime is not None
    assert fixture._runtime.tracker.get_local_occupancy().reservations == 0
    # The parent's tracker keeps its own pending entry until the TTL prunes it, which is
    # why the workers are configured with a short LKSCALER_RESERVATION_TTL_SEC.
    assert tracker.get_local_occupancy().reservations == 1


async def _await_gone(store: InMemoryReservationStore, job_id: str) -> None:
    deadline = datetime.now(UTC) + timedelta(seconds=5)
    while datetime.now(UTC) < deadline:
        if store.get(pod_id=_POD_ID, job_id=job_id) is None:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"reservation {job_id} was never released")
