import pytest

from lkscaler_core.snapshot import ClusterSnapshotSummary

from lkscaler_keda.policy import AutoscalerPolicy
from lkscaler_keda.scaler import KedaExternalScaler


def test_external_scaler_reports_cluster_free_slots_metric() -> None:
    summary = ClusterSnapshotSummary(
        cluster_free_slots=5,
        idle_pod_count=1,
        snapshot_age_sec=901,
        smallest_idle_pod_free_slots=1,
    )
    policy = AutoscalerPolicy(min_cluster_free_slots=4, scale_down_dwell_sec=900)
    scaler = KedaExternalScaler(policy=policy, summary_provider=lambda: summary)

    metrics = scaler.get_metrics("cluster_free_slots")

    assert metrics[0].metricName == "cluster_free_slots"
    assert metrics[0].metricValue == "5"


def test_external_scaler_reports_safe_down_metric() -> None:
    summary = ClusterSnapshotSummary(
        cluster_free_slots=5,
        idle_pod_count=1,
        snapshot_age_sec=901,
        smallest_idle_pod_free_slots=1,
    )
    policy = AutoscalerPolicy(min_cluster_free_slots=4, scale_down_dwell_sec=900)
    scaler = KedaExternalScaler(policy=policy, summary_provider=lambda: summary)

    metrics = scaler.get_metrics("safe_remaining_free_slots_after_one_idle_removal")

    assert metrics[0].metricName == "safe_remaining_free_slots_after_one_idle_removal"
    assert metrics[0].metricValue == "4"


def test_external_scaler_rejects_unknown_metric() -> None:
    summary = ClusterSnapshotSummary(
        cluster_free_slots=5,
        idle_pod_count=1,
        snapshot_age_sec=901,
        smallest_idle_pod_free_slots=1,
    )
    policy = AutoscalerPolicy(min_cluster_free_slots=4, scale_down_dwell_sec=900)
    scaler = KedaExternalScaler(policy=policy, summary_provider=lambda: summary)

    with pytest.raises(ValueError):
        scaler.get_metrics("unknown_metric")


def test_external_scaler_exposes_activity_and_metric_spec() -> None:
    summary = ClusterSnapshotSummary(
        cluster_free_slots=3,
        idle_pod_count=0,
        snapshot_age_sec=901,
        smallest_idle_pod_free_slots=None,
    )
    policy = AutoscalerPolicy(min_cluster_free_slots=4, scale_down_dwell_sec=900)
    scaler = KedaExternalScaler(policy=policy, summary_provider=lambda: summary)

    specs = scaler.get_metric_spec()

    assert scaler.is_active() is True
    assert scaler.stream_is_active() == [True]
    assert {spec.metricName for spec in specs} == {
        "cluster_free_slots",
        "safe_remaining_free_slots_after_one_idle_removal",
    }