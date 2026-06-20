from lkscaler_core.snapshot import ClusterSnapshotCache


def test_snapshot_cache_returns_independent_copy() -> None:
    cache = ClusterSnapshotCache()
    cache.update({"pod-a": 2, "pod-b": 1})

    snapshot = cache.get()
    assert snapshot.min_positive_free_slots() == 1

    snapshot.free_slots_by_pod["pod-c"] = 5

    second = cache.get()
    assert "pod-c" not in second.free_slots_by_pod
