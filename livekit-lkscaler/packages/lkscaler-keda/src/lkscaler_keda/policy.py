from dataclasses import dataclass

from lkscaler_core.snapshot import ClusterSnapshotSummary


@dataclass(frozen=True)
class AutoscalerDecision:
    scale_up: bool
    scale_down_allowed: bool
    safe_remaining_free_slots_after_one_idle_removal: int


@dataclass(frozen=True)
class AutoscalerPolicy:
    min_cluster_free_slots: int
    scale_down_dwell_sec: int

    def evaluate(self, *, summary: ClusterSnapshotSummary) -> AutoscalerDecision:
        scale_up = summary.cluster_free_slots < self.min_cluster_free_slots
        dwell_satisfied = summary.snapshot_age_sec >= self.scale_down_dwell_sec
        has_idle_pod = summary.smallest_idle_pod_free_slots is not None
        safe_remaining = summary.cluster_free_slots - (summary.smallest_idle_pod_free_slots or 0)

        scale_down_allowed = (
            not scale_up
            and dwell_satisfied
            and has_idle_pod
            and safe_remaining >= self.min_cluster_free_slots
        )

        if not scale_down_allowed:
            safe_remaining = self.min_cluster_free_slots

        return AutoscalerDecision(
            scale_up=scale_up,
            scale_down_allowed=scale_down_allowed,
            safe_remaining_free_slots_after_one_idle_removal=safe_remaining,
        )