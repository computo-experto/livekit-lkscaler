from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from lkscaler_core import (
    BinpackConfig,
    PodOccupancy,
    ReservationStore,
    choose_load_signal,
    cleanup_unassigned_reservation,
    reserve_for_admission,
)


class _RequestLike(Protocol):
    id: str

    async def accept(self, **kwargs: Any) -> None: ...

    async def reject(self, **kwargs: Any) -> None: ...


class _TrackerLike(Protocol):
    def get_local_occupancy(self) -> PodOccupancy: ...

    def get_cluster_free_slots(self) -> dict[str, int]: ...


def _extract_job_id(job_req: _RequestLike) -> str:
    if getattr(job_req, "id", ""):
        return str(job_req.id)
    raise ValueError("Job request does not provide a valid id")


def build_on_request_handler(
    config: BinpackConfig,
    store: ReservationStore,
    tracker: _TrackerLike,
) -> Callable[[_RequestLike], Any]:
    """Build LiveKit ``on_request`` admission handler.

    Behavior:
    - evaluate overflow guard (>= hard bound)
    - create reservation before calling accept
    - reject if reservation cannot be created
    - clean up reservation if accept fails
    """

    async def on_request(job_req: _RequestLike) -> None:
        occupancy = tracker.get_local_occupancy()
        job_id = _extract_job_id(job_req)
        now = datetime.now(UTC)

        result = reserve_for_admission(
            store=store,
            occupancy=occupancy,
            pod_id=config.pod_id,
            job_id=job_id,
            room_target_n=config.room_target_n,
            overflow_margin=config.overflow_margin,
            reservation_ttl_sec=config.reservation_ttl_sec,
            now=now,
        )

        if not result.accepted:
            await job_req.reject(terminate=False)
            return

        try:
            await job_req.accept()
        except Exception:
            cleanup_unassigned_reservation(store=store, pod_id=config.pod_id, job_id=job_id)
            raise

    return on_request


def build_load_fnc(
    config: BinpackConfig,
    store: ReservationStore,
    tracker: _TrackerLike,
) -> Callable[..., float]:
    """Build LiveKit ``load_fnc`` callback.

    The single winner reports ``0.0`` and every other pod reports ``1.0``, so the server
    keeps offering jobs to the pod that is filling toward its target.
    """

    _ = store

    def load_fnc(*args: Any, **kwargs: Any) -> float:
        _ = (args, kwargs)
        return choose_load_signal(
            local_pod_id=config.pod_id,
            free_slots_by_pod=tracker.get_cluster_free_slots(),
        )

    return load_fnc
