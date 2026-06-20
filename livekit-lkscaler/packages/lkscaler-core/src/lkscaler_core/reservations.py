from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock

from .models import ReservationRecord


class ReservationStore:
    def create(self, reservation: ReservationRecord) -> bool:
        raise NotImplementedError

    def delete(self, *, pod_id: str, job_id: str) -> None:
        raise NotImplementedError

    def get(self, *, pod_id: str, job_id: str) -> ReservationRecord | None:
        raise NotImplementedError


@dataclass
class InMemoryReservationStore(ReservationStore):
    _records: dict[tuple[str, str], ReservationRecord]

    def __init__(self) -> None:
        self._records = {}
        self._lock = Lock()

    def create(self, reservation: ReservationRecord) -> bool:
        key = (reservation.pod_id, reservation.job_id)
        with self._lock:
            if key in self._records:
                return False
            self._records[key] = reservation
            return True

    def delete(self, *, pod_id: str, job_id: str) -> None:
        with self._lock:
            self._records.pop((pod_id, job_id), None)

    def get(self, *, pod_id: str, job_id: str) -> ReservationRecord | None:
        with self._lock:
            return self._records.get((pod_id, job_id))

    def remove_expired(self, *, now: datetime) -> int:
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        removed = 0
        with self._lock:
            keys = [key for key, value in self._records.items() if value.is_expired(now=now)]
            for key in keys:
                removed += 1
                del self._records[key]
        return removed

    def create_with_ttl(self, *, pod_id: str, job_id: str, ttl_sec: int, now: datetime) -> bool:
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        reservation = ReservationRecord(
            pod_id=pod_id,
            job_id=job_id,
            created_at=now,
            expires_at=now + timedelta(seconds=ttl_sec),
        )
        return self.create(reservation)
