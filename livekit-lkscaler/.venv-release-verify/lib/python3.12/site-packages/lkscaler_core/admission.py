from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .models import PodOccupancy, ReservationRecord
from .reservations import ReservationStore


def should_reject_overflow(
    *,
    occupancy: PodOccupancy,
    room_target_n: int,
    overflow_margin: int,
) -> bool:
    """Reject when occupancy already reached the hard bound.

    Hard bound is ``room_target_n + overflow_margin``.
    """
    return occupancy.occupied_slots() >= room_target_n + overflow_margin


@dataclass(frozen=True)
class AdmissionResult:
    accepted: bool
    reason: str


def reserve_for_admission(
    *,
    store: ReservationStore,
    occupancy: PodOccupancy,
    pod_id: str,
    job_id: str,
    room_target_n: int,
    overflow_margin: int,
    reservation_ttl_sec: int,
    now: datetime,
) -> AdmissionResult:
    """Reserve a slot before on_request accept is called."""
    if should_reject_overflow(
        occupancy=occupancy,
        room_target_n=room_target_n,
        overflow_margin=overflow_margin,
    ):
        return AdmissionResult(accepted=False, reason="overflow_guard")

    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    reservation = ReservationRecord(
        pod_id=pod_id,
        job_id=job_id,
        created_at=now,
        expires_at=now + timedelta(seconds=reservation_ttl_sec),
    )

    if not store.create(reservation):
        return AdmissionResult(accepted=False, reason="reservation_create_failed")

    return AdmissionResult(accepted=True, reason="reserved")


def cleanup_unassigned_reservation(*, store: ReservationStore, pod_id: str, job_id: str) -> None:
    """Remove reservation when accept does not lead to assignment/start."""
    store.delete(pod_id=pod_id, job_id=job_id)
