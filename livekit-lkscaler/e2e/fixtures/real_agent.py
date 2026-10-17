"""Real LiveKit Agents worker wired with the LKScaler placement hooks.

This is the Milestone 9 counterpart to `packed_agent.py`: it is an actual
`livekit-agents` worker, so jobs arrive through a real dispatch, and the SDK's own
`AgentServer.active_jobs` is what counts this worker's occupancy.

Wiring, verified against the installed SDK (1.6.2):

- `WorkerOptions.request_fnc` is passed through to `AgentServer.rtc_session` as
  `on_request`, whose object exposes `id`, `accept(*, name, identity, ...)` and
  `reject(*, terminate=True)` -- exactly what `build_on_request_handler` calls.
- `WorkerOptions.load_fnc` accepts a one-argument callable and hands it the server,
  which is how this worker learns its own active job count. `load_threshold` must be
  below 1 in production mode, so the placement signal actually gates dispatch.
- The entrypoint holds the job open (no media pipeline) because placement only needs
  the job to occupy a slot.
- The SDK spawns one process per job and pickles these callables to get there, so the
  entrypoint, request and load functions are module-level and reach their state
  through the module-level runtime set by `build_worker`. A closure would fail with
  "Can't get local object 'build_worker.<locals>.entrypoint'".

Environment: LKSCALER_BACKEND, LKSCALER_NAMESPACE, LKSCALER_POD_ID, LKSCALER_ZK_HOSTS,
LKSCALER_REDIS_URL, LKSCALER_ROOM_TARGET_N, LKSCALER_OVERFLOW_MARGIN,
LKSCALER_RESERVATION_TTL_SEC, LKSCALER_SYNC_INTERVAL_MS, LKSCALER_LOAD_THRESHOLD,
LKSCALER_POD_STATE_TTL_SEC, LKSCALER_AGENT_NAME, plus the SDK's own LIVEKIT_URL /
LIVEKIT_API_KEY / LIVEKIT_API_SECRET.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Protocol, cast

from livekit.agents import AgentServer, JobContext, JobRequest, WorkerOptions, cli
from lkscaler_core import BinpackConfig, PodOccupancy, ReservationRecord
from lkscaler_core.reservations import ReservationStore
from lkscaler_core.state import PodState
from lkscaler_livekit import build_load_fnc, build_on_request_handler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("real-agent")

_running = True


def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, str(default)))


class ClusterCapableStore(Protocol):
    def publish_pod_state(self, state: PodState) -> None: ...

    def free_slots_by_pod(self) -> dict[str, int]: ...

    def remove_expired(self, *, now: datetime) -> int: ...


class WorkerTracker:
    """Local occupancy from the SDK plus cluster occupancy from the backend."""

    def __init__(
        self,
        *,
        store: ReservationStore,
        cluster_store: ClusterCapableStore | None,
        pod_id: str,
    ) -> None:
        self._store = store
        self._cluster_store = cluster_store
        self._pod_id = pod_id
        self._lock = threading.Lock()
        self._pending: dict[str, ReservationRecord] = {}
        self._server: AgentServer | None = None

    def attach(self, server: AgentServer) -> None:
        self._server = server

    def note_reservation(self, job_id: str, record: ReservationRecord) -> None:
        with self._lock:
            self._pending[job_id] = record

    def release_reservation(self, job_id: str) -> None:
        with self._lock:
            self._pending.pop(job_id, None)

    def _prune_locked(self) -> None:
        moment = datetime.now(UTC)
        for job_id, record in list(self._pending.items()):
            if record.is_expired(now=moment):
                del self._pending[job_id]

    def get_local_occupancy(self) -> PodOccupancy:
        active = len(self._server.active_jobs) if self._server is not None else 0
        with self._lock:
            self._prune_locked()
            return PodOccupancy(active_rooms=active, reservations=len(self._pending))

    def get_cluster_free_slots(self) -> dict[str, int]:
        if self._cluster_store is None:
            return {}
        return self._cluster_store.free_slots_by_pod()


class NotifyingReservationStore(ReservationStore):
    """Delegates to the real store while telling the tracker about its own reservations."""

    def __init__(self, *, inner: ReservationStore, tracker: WorkerTracker) -> None:
        self._inner = inner
        self._tracker = tracker

    def create(self, reservation: ReservationRecord) -> bool:
        created = self._inner.create(reservation)
        if created:
            self._tracker.note_reservation(reservation.job_id, reservation)
        return created

    def delete(self, *, pod_id: str, job_id: str) -> None:
        self._inner.delete(pod_id=pod_id, job_id=job_id)
        self._tracker.release_reservation(job_id)

    def get(self, *, pod_id: str, job_id: str) -> ReservationRecord | None:
        return self._inner.get(pod_id=pod_id, job_id=job_id)

    def remove_expired(self, *, now: datetime) -> int:
        return self._inner.remove_expired(now=now)


@dataclass
class Runtime:
    config: BinpackConfig
    store: ReservationStore
    tracker: WorkerTracker
    cluster_store: ClusterCapableStore | None
    closer: Any
    load_base: Callable[[], float]
    on_request: Callable[[Any], Awaitable[None]]

    def release(self, job_id: str) -> None:
        self.store.delete(pod_id=self.config.pod_id, job_id=job_id)
        self.tracker.release_reservation(job_id)

    def close(self) -> None:
        if self.closer is not None:
            self.closer.close()


_runtime: Runtime | None = None
_last_report: tuple[float, float] | None = None


def _build_runtime(
    backend: tuple[ReservationStore, ClusterCapableStore | None, Any] | None = None,
) -> Runtime:
    config = _config_from_env()
    store, cluster_store, closer = backend if backend is not None else _build_backend()
    tracker = WorkerTracker(store=store, cluster_store=cluster_store, pod_id=config.pod_id)
    notifying = NotifyingReservationStore(inner=store, tracker=tracker)
    return Runtime(
        config=config,
        store=store,
        tracker=tracker,
        cluster_store=cluster_store,
        closer=closer,
        load_base=build_load_fnc(config=config, store=notifying, tracker=tracker),
        on_request=build_on_request_handler(config=config, store=notifying, tracker=tracker),
    )


def _ensure_runtime() -> Runtime:
    """The SDK imports this module anew in every job process, so each process builds
    its own runtime rather than inheriting the parent's."""
    global _runtime
    if _runtime is None:
        _runtime = _build_runtime()
    return _runtime


def publish(runtime: Runtime) -> None:
    if runtime.cluster_store is None:
        return
    occupancy = runtime.tracker.get_local_occupancy()
    runtime.cluster_store.publish_pod_state(
        PodState(
            pod_id=runtime.config.pod_id,
            free_slots=occupancy.free_slots(room_target_n=runtime.config.room_target_n),
            active_rooms=occupancy.active_rooms,
            reservations=occupancy.reservations,
            updated_at=datetime.now(UTC),
        )
    )


async def entrypoint(ctx: JobContext) -> None:
    owns_runtime = _runtime is None
    runtime = _ensure_runtime()
    job_id = ctx.job.id
    runtime.release(job_id)
    logger.info("job assigned pod=%s job=%s", runtime.config.pod_id, job_id)
    await ctx.connect()
    closed = asyncio.Event()
    ctx.room.on("disconnected", lambda *_: closed.set())
    try:
        await closed.wait()
    finally:
        logger.info("job finished pod=%s job=%s", runtime.config.pod_id, job_id)
        if owns_runtime:
            runtime.close()


def load_fnc(server: AgentServer) -> float:
    global _last_report
    runtime = _ensure_runtime()
    runtime.tracker.attach(server)
    value = float(runtime.load_base())
    _last_report = (value, time.monotonic())
    return value


def reported_load() -> dict[str, Any]:
    """What this worker last told the server, and how long ago."""
    if _last_report is None:
        return {"reported": None, "reported_age_ms": None}
    value, at = _last_report
    return {"reported": value, "reported_age_ms": round((time.monotonic() - at) * 1000)}


async def request_fnc(job_req: JobRequest) -> None:
    await _ensure_runtime().on_request(job_req)


def _build_backend() -> tuple[ReservationStore, ClusterCapableStore | None, Any]:
    backend = os.environ.get("LKSCALER_BACKEND", "zookeeper")
    namespace = os.environ.get("LKSCALER_NAMESPACE", "livekit-lkscaler")
    store: ReservationStore
    if backend == "zookeeper":
        from lkscaler_core.zookeeper import KazooNodeClient, ZooKeeperStateStore

        client = KazooNodeClient(
            hosts=os.environ["LKSCALER_ZK_HOSTS"].split(","),
            session_timeout_sec=_env_int("LKSCALER_ZK_SESSION_TIMEOUT_SEC", 10),
        )
        client.start()
        store = ZooKeeperStateStore(namespace=namespace, client=client)
        return store, store, client
    if backend == "redis":
        from lkscaler_core.redis import RedisClientAdapter, RedisStateStore

        adapter = RedisClientAdapter(url=os.environ["LKSCALER_REDIS_URL"])
        adapter.connect()
        store = RedisStateStore(
            namespace=namespace,
            client=adapter,
            pod_state_ttl_sec=_env_int("LKSCALER_POD_STATE_TTL_SEC", 30),
        )
        return store, store, adapter
    raise SystemExit(f"unsupported LKSCALER_BACKEND: {backend}")


def _config_from_env() -> BinpackConfig:
    return BinpackConfig(
        namespace=os.environ.get("LKSCALER_NAMESPACE", "livekit-lkscaler"),
        pod_id=os.environ.get("LKSCALER_POD_ID", "real-agent"),
        room_target_n=_env_int("LKSCALER_ROOM_TARGET_N", 2),
        overflow_margin=_env_int("LKSCALER_OVERFLOW_MARGIN", 1),
        reservation_ttl_sec=_env_int("LKSCALER_RESERVATION_TTL_SEC", 30),
        zk_session_timeout_sec=_env_int("LKSCALER_ZK_SESSION_TIMEOUT_SEC", 10),
        sync_interval_ms=_env_int("LKSCALER_SYNC_INTERVAL_MS", 500),
    )


def build_worker(
    backend: tuple[ReservationStore, ClusterCapableStore | None, Any] | None = None,
) -> tuple[WorkerOptions, WorkerTracker, ClusterCapableStore | None, Any]:
    """Build the real worker: SDK options plus the LKScaler hooks and tracker."""
    global _runtime

    _runtime = _build_runtime(backend)

    options = WorkerOptions(
        entrypoint_fnc=entrypoint,
        request_fnc=cast("Callable[[JobRequest], Awaitable[None]]", request_fnc),
        load_fnc=load_fnc,
        load_threshold=float(os.environ.get("LKSCALER_LOAD_THRESHOLD", "0.7")),
        agent_name=os.environ.get("LKSCALER_AGENT_NAME", ""),
    )
    return options, _runtime.tracker, _runtime.cluster_store, _runtime.closer


def build_http(port: int) -> ThreadingHTTPServer:
    """Serve this worker's placement inputs so E2E can observe what it reports."""
    runtime = _ensure_runtime()

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

        def do_GET(self) -> None:
            occupancy = runtime.tracker.get_local_occupancy()
            if self.path == "/health":
                self._send({"ok": True, "pod_id": runtime.config.pod_id})
            elif self.path == "/load":
                self._send(
                    {
                        "load": float(runtime.load_base()),
                        "pod_id": runtime.config.pod_id,
                        **reported_load(),
                    }
                )
            elif self.path == "/occupancy":
                self._send(
                    {
                        "pod_id": runtime.config.pod_id,
                        "active_rooms": occupancy.active_rooms,
                        "reservations": occupancy.reservations,
                        "free_slots": occupancy.free_slots(
                            room_target_n=runtime.config.room_target_n
                        ),
                    }
                )
            elif self.path == "/cluster":
                self._send({"free_slots_by_pod": runtime.tracker.get_cluster_free_slots()})
            else:
                self._send({"error": "not found"}, 404)

    return ThreadingHTTPServer(("0.0.0.0", port), Handler)


def main() -> None:
    global _running

    options, tracker, cluster_store, closer = build_worker()
    runtime = _ensure_runtime()

    def sync_loop() -> None:
        interval = runtime.config.sync_interval_ms / 1000
        while _running:
            publish(runtime)
            if cluster_store is not None:
                cluster_store.remove_expired(now=datetime.now(UTC))
            time.sleep(interval)

    publish(runtime)
    threading.Thread(target=sync_loop, daemon=True).start()
    port = _env_int("LKSCALER_HTTP_PORT", 8090)
    if port > 0:
        httpd = build_http(port)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
    logger.info(
        "real agent starting pod=%s backend=%s namespace=%s port=%s threshold=%s",
        runtime.config.pod_id,
        os.environ.get("LKSCALER_BACKEND", "zookeeper"),
        runtime.config.namespace,
        port,
        options.load_threshold,
    )
    try:
        cli.run_app(options)
    finally:
        _running = False
        if closer is not None:
            closer.close()


if __name__ == "__main__":
    main()
