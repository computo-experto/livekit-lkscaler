"""Backend-wired agent simulator for the coordination e2e tests.

It drives the real placement functions (`reserve_for_admission` and `build_load_fnc`)
against a real coordination backend and exposes them over a small HTTP API, so the e2e
suite can put load on two workers at once and watch the cluster view through the backend
rather than through container logs.

Configuration comes from the environment: LKSCALER_BACKEND (zookeeper | redis | memory),
LKSCALER_NAMESPACE, LKSCALER_POD_ID, LKSCALER_ZK_HOSTS, LKSCALER_REDIS_URL,
LKSCALER_ROOM_TARGET_N, LKSCALER_OVERFLOW_MARGIN, LKSCALER_RESERVATION_TTL_SEC,
LKSCALER_POD_STATE_TTL_SEC, LKSCALER_HTTP_PORT.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import threading
import time
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Protocol

from lkscaler_core import (
    BinpackConfig,
    InMemoryReservationStore,
    PodOccupancy,
    ReservationRecord,
    reserve_for_admission,
)
from lkscaler_core.reservations import ReservationStore
from lkscaler_core.state import PodState
from lkscaler_livekit import build_load_fnc

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("packed-agent")

_running = True


def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, str(default)))


class _ClusterCapableStore(Protocol):
    """A store that can also publish and read cluster occupancy."""

    def publish_pod_state(self, state: PodState) -> None: ...

    def free_slots_by_pod(self) -> dict[str, int]: ...


class PackedAgent:
    def __init__(self) -> None:
        self.backend = os.environ.get("LKSCALER_BACKEND", "memory")
        self.namespace = os.environ.get("LKSCALER_NAMESPACE", "livekit-lkscaler")
        self.pod_id = os.environ.get("LKSCALER_POD_ID", "packed-agent")
        self.config = BinpackConfig(
            namespace=self.namespace,
            pod_id=self.pod_id,
            room_target_n=_env_int("LKSCALER_ROOM_TARGET_N", 3),
            overflow_margin=_env_int("LKSCALER_OVERFLOW_MARGIN", 1),
            reservation_ttl_sec=_env_int("LKSCALER_RESERVATION_TTL_SEC", 30),
            zk_session_timeout_sec=_env_int("LKSCALER_ZK_SESSION_TIMEOUT_SEC", 10),
            sync_interval_ms=_env_int("LKSCALER_SYNC_INTERVAL_MS", 250),
        )
        self._lock = threading.Lock()
        self._jobs: dict[str, ReservationRecord] = {}
        self._active: dict[str, datetime] = {}
        self._httpd: ThreadingHTTPServer | None = None
        self.store: ReservationStore
        self._cluster_store: _ClusterCapableStore | None
        self._closer: Any = None
        self.store, self._cluster_store = self._build_store()
        self._load_fnc = build_load_fnc(config=self.config, store=self.store, tracker=self)

    def _build_store(self) -> tuple[ReservationStore, _ClusterCapableStore | None]:
        if self.backend == "zookeeper":
            from lkscaler_core.zookeeper import KazooNodeClient, ZooKeeperStateStore

            kazoo_client = KazooNodeClient(
                hosts=os.environ["LKSCALER_ZK_HOSTS"].split(","),
                session_timeout_sec=self.config.zk_session_timeout_sec,
            )
            kazoo_client.start()
            self._closer = kazoo_client
            zk_store = ZooKeeperStateStore(namespace=self.namespace, client=kazoo_client)
            return zk_store, zk_store
        if self.backend == "redis":
            from lkscaler_core.redis import RedisClientAdapter, RedisStateStore

            adapter = RedisClientAdapter(url=os.environ["LKSCALER_REDIS_URL"])
            adapter.connect()
            self._closer = adapter
            redis_store = RedisStateStore(
                namespace=self.namespace,
                client=adapter,
                pod_state_ttl_sec=_env_int("LKSCALER_POD_STATE_TTL_SEC", 5),
            )
            return redis_store, redis_store
        return InMemoryReservationStore(), None

    def _prune_locked(self) -> None:
        moment = datetime.now(UTC)
        for job_id, record in list(self._jobs.items()):
            if record.is_expired(now=moment):
                del self._jobs[job_id]

    def _occupancy_locked(self) -> PodOccupancy:
        self._prune_locked()
        return PodOccupancy(active_rooms=len(self._active), reservations=len(self._jobs))

    def get_local_occupancy(self) -> PodOccupancy:
        with self._lock:
            return self._occupancy_locked()

    def get_cluster_free_slots(self) -> dict[str, int]:
        return self.cluster_free_slots()

    def cluster_free_slots(self) -> dict[str, int]:
        if self._cluster_store is None:
            local = self.get_local_occupancy().free_slots(room_target_n=self.config.room_target_n)
            return {self.pod_id: local}
        return self._cluster_store.free_slots_by_pod()

    def publish(self) -> None:
        if self._cluster_store is None:
            return
        occupancy = self.get_local_occupancy()
        self._cluster_store.publish_pod_state(
            PodState(
                pod_id=self.pod_id,
                free_slots=occupancy.free_slots(room_target_n=self.config.room_target_n),
                active_rooms=occupancy.active_rooms,
                reservations=occupancy.reservations,
                updated_at=datetime.now(UTC),
            )
        )

    def request_job(self, job_id: str) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._lock:
            occupancy = self._occupancy_locked()
        result = reserve_for_admission(
            store=self.store,
            occupancy=occupancy,
            pod_id=self.pod_id,
            job_id=job_id,
            room_target_n=self.config.room_target_n,
            overflow_margin=self.config.overflow_margin,
            reservation_ttl_sec=self.config.reservation_ttl_sec,
            now=now,
        )
        if result.accepted:
            with self._lock:
                self._jobs[job_id] = ReservationRecord(
                    pod_id=self.pod_id,
                    job_id=job_id,
                    created_at=now,
                    expires_at=now + timedelta(seconds=self.config.reservation_ttl_sec),
                )
        self.publish()
        return {"accepted": result.accepted, "reason": result.reason}

    def complete_job(self, job_id: str) -> bool:
        with self._lock:
            reserved = self._jobs.pop(job_id, None)
            if reserved is None:
                return False
            self._active[job_id] = datetime.now(UTC)
        self.store.delete(pod_id=self.pod_id, job_id=job_id)
        self.publish()
        return True

    def release_job(self, job_id: str) -> bool:
        with self._lock:
            reserved = self._jobs.pop(job_id, None)
        self.store.delete(pod_id=self.pod_id, job_id=job_id)
        self.publish()
        return reserved is not None

    def reset(self) -> None:
        with self._lock:
            job_ids = list(self._jobs)
            self._jobs.clear()
            self._active.clear()
        for job_id in job_ids:
            self.store.delete(pod_id=self.pod_id, job_id=job_id)
        self.publish()

    def load_value(self) -> float:
        return float(self._load_fnc())

    def occupancy(self) -> dict[str, Any]:
        occupancy = self.get_local_occupancy()
        return {
            "pod_id": self.pod_id,
            "backend": self.backend,
            "active_rooms": occupancy.active_rooms,
            "reservations": occupancy.reservations,
            "free_slots": occupancy.free_slots(room_target_n=self.config.room_target_n),
            "room_target_n": self.config.room_target_n,
            "overflow_margin": self.config.overflow_margin,
        }

    def sync_loop(self) -> None:
        interval = self.config.sync_interval_ms / 1000
        while _running:
            self.publish()
            self.store.remove_expired(now=datetime.now(UTC))
            time.sleep(interval)

    def build_http(self, port: int) -> None:
        agent = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: Any) -> None:
                logger.info("http %s", fmt % args)

            def _send(self, payload: dict[str, Any], status: int = 200) -> None:
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _body(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length else b"{}"
                parsed: Any = json.loads(raw or b"{}")
                return parsed if isinstance(parsed, dict) else {}

            def do_GET(self) -> None:
                if self.path == "/health":
                    self._send({"ok": True, "backend": agent.backend, "pod_id": agent.pod_id})
                elif self.path == "/load":
                    self._send({"load": agent.load_value()})
                elif self.path == "/occupancy":
                    self._send(agent.occupancy())
                elif self.path == "/cluster":
                    self._send({"free_slots_by_pod": agent.cluster_free_slots()})
                else:
                    self._send({"error": "not found"}, 404)

            def do_POST(self) -> None:
                job_id = str(self._body().get("job_id", ""))
                if self.path == "/request":
                    self._send(agent.request_job(job_id))
                elif self.path == "/complete":
                    self._send({"ok": agent.complete_job(job_id)})
                elif self.path == "/release":
                    self._send({"ok": agent.release_job(job_id)})
                elif self.path == "/reset":
                    agent.reset()
                    self._send({"ok": True})
                else:
                    self._send({"error": "not found"}, 404)

        self._httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)

    def serve(self) -> None:
        if self._httpd is None:
            raise RuntimeError("HTTP server was not built")
        self._httpd.serve_forever()

    def close(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._closer is not None:
            self._closer.close()
            self._closer = None


def _stop(*_args: object) -> None:
    global _running
    _running = False


def main() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    agent = PackedAgent()
    port = _env_int("LKSCALER_HTTP_PORT", 8090)
    logger.info(
        "packed agent starting pod=%s backend=%s namespace=%s port=%s",
        agent.pod_id,
        agent.backend,
        agent.namespace,
        port,
    )
    agent.publish()
    threading.Thread(target=agent.sync_loop, daemon=True).start()
    agent.build_http(port)
    threading.Thread(target=agent.serve, daemon=True).start()
    try:
        while _running:
            time.sleep(0.2)
    finally:
        agent.close()
        logger.info("packed agent stopping pod=%s", agent.pod_id)


if __name__ == "__main__":
    main()
