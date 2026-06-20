from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class PodOccupancy:
    active_rooms: int
    reservations: int

    def occupied_slots(self) -> int:
        return self.active_rooms + self.reservations

    def free_slots(self, *, room_target_n: int) -> int:
        return room_target_n - self.occupied_slots()


@dataclass(frozen=True)
class ReservationRecord:
    pod_id: str
    job_id: str
    created_at: datetime
    expires_at: datetime

    def is_expired(self, *, now: datetime) -> bool:
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        return now >= self.expires_at


@dataclass(frozen=True)
class RoomRecord:
    room_id: str
    pod_id: str
    job_id: str
    started_at: datetime
