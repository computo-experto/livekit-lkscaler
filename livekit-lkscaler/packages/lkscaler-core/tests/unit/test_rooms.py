"""The shared room list is the occupancy authority, so its liveness rule is unit-tested."""

from __future__ import annotations

from datetime import UTC, datetime

from lkscaler_core.models import RoomRecord
from lkscaler_core.rooms import decode_rooms, live_rooms, orphan_room_ids, rooms_by_pod
from lkscaler_core.state import PodState


def _state(pod_id: str) -> PodState:
    return PodState(
        pod_id=pod_id,
        free_slots=1,
        active_rooms=0,
        reservations=0,
        updated_at=datetime.now(UTC),
    )


def _payload(room_id: str, pod_id: str, job_id: str = "AJ_1") -> dict[str, object]:
    return {
        "room_id": room_id,
        "pod_id": pod_id,
        "job_id": job_id,
        "started_at": datetime.now(UTC).isoformat(),
    }


def test_decode_rooms_keeps_well_formed_payloads_and_skips_the_rest() -> None:
    records = decode_rooms(
        [
            _payload("m9-1", "pod-a"),
            {"room_id": "m9-2"},
            {"room_id": "m9-3", "pod_id": "pod-a", "job_id": "AJ_1", "started_at": "not-a-date"},
        ]
    )

    assert [record.room_id for record in records] == ["m9-1"]


def test_a_room_only_counts_while_its_pod_publishes_state() -> None:
    rooms = [
        RoomRecord("m9-1", "pod-a", "AJ_1", datetime.now(UTC)),
        RoomRecord("m9-2", "pod-b", "AJ_2", datetime.now(UTC)),
    ]

    live = live_rooms(rooms, {"pod-a": _state("pod-a")})

    assert [room.room_id for room in live] == ["m9-1"]


def test_rooms_by_pod_counts_every_live_pod_and_ignores_orphans() -> None:
    rooms = [
        RoomRecord("m9-1", "pod-a", "AJ_1", datetime.now(UTC)),
        RoomRecord("m9-2", "pod-a", "AJ_2", datetime.now(UTC)),
        RoomRecord("m9-3", "pod-dead", "AJ_3", datetime.now(UTC)),
    ]

    counts = rooms_by_pod(rooms, {"pod-a": _state("pod-a"), "pod-b": _state("pod-b")})

    assert counts == {"pod-a": 2, "pod-b": 0}


def test_orphan_room_ids_are_the_records_a_worker_may_sweep() -> None:
    rooms = [
        RoomRecord("m9-1", "pod-a", "AJ_1", datetime.now(UTC)),
        RoomRecord("m9-2", "pod-dead", "AJ_2", datetime.now(UTC)),
    ]

    assert orphan_room_ids(rooms, {"pod-a": _state("pod-a")}) == ["m9-2"]


def test_a_removed_room_stops_counting_immediately() -> None:
    states = {"pod-a": _state("pod-a")}
    rooms = [RoomRecord("m9-1", "pod-a", "AJ_1", datetime.now(UTC))]
    assert rooms_by_pod(rooms, states) == {"pod-a": 1}

    assert rooms_by_pod([], states) == {"pod-a": 0}


def test_connected_at_is_optional_and_decoded_when_present() -> None:
    now = datetime.now(UTC)
    pending = decode_rooms([{**_payload("m9-a", "pod-a"), "connected_at": None}])
    connected = decode_rooms([{**_payload("m9-b", "pod-a"), "connected_at": now.isoformat()}])

    assert pending[0].connected_at is None
    assert connected[0].connected_at == now
