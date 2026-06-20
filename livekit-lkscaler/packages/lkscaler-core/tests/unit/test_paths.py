import pytest
from lkscaler_core.paths import ZkPaths


def test_builds_expected_paths() -> None:
    paths = ZkPaths("team-a")

    assert paths.base == "/livekit-binpack/team-a"
    assert paths.pod_node("pod-1") == "/livekit-binpack/team-a/pods/pod-1"
    assert paths.room_node("room-1") == "/livekit-binpack/team-a/rooms/room-1"
    assert (
        paths.reservation_node("pod-1", "job-1")
        == "/livekit-binpack/team-a/reservations/pod-1/job-1"
    )


def test_invalid_segment_rejected() -> None:
    paths = ZkPaths("team-a")

    with pytest.raises(ValueError):
        paths.room_node("bad/value")
