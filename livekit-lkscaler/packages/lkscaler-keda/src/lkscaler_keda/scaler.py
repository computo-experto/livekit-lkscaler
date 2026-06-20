from collections.abc import Callable
from dataclasses import dataclass

from lkscaler_core.snapshot import ClusterSnapshotSummary

from .policy import AutoscalerPolicy


@dataclass(frozen=True)
class ExternalMetricValue:
    metricName: str
    metricValue: str


@dataclass(frozen=True)
class MetricSpec:
    metricName: str
    targetSize: int


class KedaExternalScaler:
    def __init__(
        self,
        *,
        policy: AutoscalerPolicy,
        summary_provider: Callable[[], ClusterSnapshotSummary],
    ) -> None:
        self._policy = policy
        self._summary_provider = summary_provider

    def is_active(self) -> bool:
        summary = self._summary_provider()
        return summary.cluster_free_slots < self._policy.min_cluster_free_slots

    def stream_is_active(self) -> list[bool]:
        return [self.is_active()]

    def get_metric_spec(self) -> list[MetricSpec]:
        return [
            MetricSpec(
                metricName="cluster_free_slots",
                targetSize=self._policy.min_cluster_free_slots,
            ),
            MetricSpec(
                metricName="safe_remaining_free_slots_after_one_idle_removal",
                targetSize=self._policy.min_cluster_free_slots,
            ),
        ]

    def get_metrics(self, metric_name: str) -> list[ExternalMetricValue]:
        summary = self._summary_provider()
        decision = self._policy.evaluate(summary=summary)

        if metric_name == "cluster_free_slots":
            metric_value = summary.cluster_free_slots
        elif metric_name == "safe_remaining_free_slots_after_one_idle_removal":
            metric_value = decision.safe_remaining_free_slots_after_one_idle_removal
        else:
            raise ValueError(f"unknown metric: {metric_name}")

        return [ExternalMetricValue(metricName=metric_name, metricValue=str(metric_value))]