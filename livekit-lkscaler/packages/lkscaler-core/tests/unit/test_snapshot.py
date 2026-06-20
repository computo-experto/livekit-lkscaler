from lkscaler_core.snapshot import ClusterSnapshotCache, PodSnapshot, summarize_cluster_snapshot


def test_snapshot_cache_returns_independent_copy() -> None:
    cache = ClusterSnapshotCache()
    cache.update({"pod-a": 2, "pod-b": 1})

    snapshot = cache.get()
    assert snapshot.min_positive_free_slots() == 1

    snapshot.free_slots_by_pod["pod-c"] = 5

    second = cache.get()
    assert "pod-c" not in second.free_slots_by_pod


def test_cluster_snapshot_summary_counts_free_slots_and_idle_pods() -> None:
    summary = summarize_cluster_snapshot(
        pods=[
            PodSnapshot(pod_id="pod-a", active_rooms=2, reservations=1, room_target_n=4),
            PodSnapshot(pod_id="pod-b", active_rooms=0, reservations=0, room_target_n=4),
        ],
        snapshot_at=1700000000,
        observed_at=1700000030,
    )

    assert summary.cluster_free_slots == 5
    assert summary.idle_pod_count == 1
    assert summary.snapshot_age_sec == 30


def test_cluster_snapshot_summary_clamps_negative_age_to_zero() -> None:
    summary = summarize_cluster_snapshot(
        pods=[PodSnapshot(pod_id="pod-a", active_rooms=0, reservations=0, room_target_n=4)],
        snapshot_at=1700000030,
        observed_at=1700000000,
    )

    assert summary.snapshot_age_sec == 0
