from datetime import UTC, datetime, timedelta

from lkscaler_core import (
    BinpackConfig,
    ClusterSnapshotCache,
    InMemoryReservationStore,
    PodOccupancy,
    ZkPaths,
    cleanup_unassigned_reservation,
    reserve_for_admission,
)


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


def test_paths_snapshot_and_admission_flow() -> None:
    config = _config()
    paths = ZkPaths(config.namespace)
    store = InMemoryReservationStore()
    snapshot_cache = ClusterSnapshotCache()
    snapshot_cache.update({"pod-a": 2, "pod-b": 1})

    snapshot = snapshot_cache.get()
    assert snapshot.min_positive_free_slots() == 1
    assert paths.pod_node(config.pod_id) == "/livekit-binpack/ns/pods/pod-a"

    result = reserve_for_admission(
        store=store,
        occupancy=PodOccupancy(active_rooms=0, reservations=0),
        pod_id=config.pod_id,
        job_id="job-1",
        room_target_n=config.room_target_n,
        overflow_margin=config.overflow_margin,
        reservation_ttl_sec=config.reservation_ttl_sec,
        now=datetime.now(UTC),
    )
    assert result.accepted is True
    assert store.get(pod_id="pod-a", job_id="job-1") is not None

    cleanup_unassigned_reservation(store=store, pod_id="pod-a", job_id="job-1")
    assert store.get(pod_id="pod-a", job_id="job-1") is None


def test_expired_reservations_are_removed() -> None:
    store = InMemoryReservationStore()
    now = datetime.now(UTC)
    _ = store.create_with_ttl(pod_id="pod-a", job_id="job-1", ttl_sec=1, now=now)

    removed = store.remove_expired(now=now + timedelta(seconds=2))
    assert removed == 1
    assert store.get(pod_id="pod-a", job_id="job-1") is None
