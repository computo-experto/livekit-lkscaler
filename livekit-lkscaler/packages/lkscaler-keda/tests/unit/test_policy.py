from lkscaler_core.snapshot import ClusterSnapshotSummary
from lkscaler_keda.policy import AutoscalerPolicy


def test_safe_scale_down_requires_threshold_dwell_and_idle_pod() -> None:
    policy = AutoscalerPolicy(min_cluster_free_slots=4, scale_down_dwell_sec=900)

    result = policy.evaluate(
        summary=ClusterSnapshotSummary(
            cluster_free_slots=5,
            idle_pod_count=1,
            snapshot_age_sec=901,
            smallest_idle_pod_free_slots=1,
        )
    )

    assert result.scale_up is False
    assert result.scale_down_allowed is True


def test_scale_up_when_cluster_free_slots_below_threshold() -> None:
    policy = AutoscalerPolicy(min_cluster_free_slots=4, scale_down_dwell_sec=900)

    result = policy.evaluate(
        summary=ClusterSnapshotSummary(
            cluster_free_slots=3,
            idle_pod_count=0,
            snapshot_age_sec=1200,
            smallest_idle_pod_free_slots=None,
        )
    )

    assert result.scale_up is True
    assert result.scale_down_allowed is False


def test_scale_down_allowed_on_dwell_and_threshold_boundary() -> None:
    policy = AutoscalerPolicy(min_cluster_free_slots=4, scale_down_dwell_sec=900)

    result = policy.evaluate(
        summary=ClusterSnapshotSummary(
            cluster_free_slots=5,
            idle_pod_count=1,
            snapshot_age_sec=900,
            smallest_idle_pod_free_slots=1,
        )
    )

    assert result.scale_up is False
    assert result.scale_down_allowed is True
    assert result.safe_remaining_free_slots_after_one_idle_removal == 4
