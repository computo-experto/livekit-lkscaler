from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ScalingPolicy:
    """How many workers the fleet needs while keeping a fixed number of free slots.

    Headroom is a slot count rather than a utilization ratio: the operator decides how much
    admission capacity must stay free for their dispatch pattern, and the scaler holds it.
    """

    min_free_slots: int
    room_target_n: int
    overflow_margin: int

    @property
    def slots_per_worker(self) -> int:
        """Admission capacity of one worker: its room target plus its overflow margin."""
        return self.room_target_n + self.overflow_margin

    def required_workers(self, *, used_slots: int) -> int:
        """Workers needed so ``min_free_slots`` stay free alongside ``used_slots``."""
        demand = max(used_slots + self.min_free_slots, 1)
        return math.ceil(demand / self.slots_per_worker)
