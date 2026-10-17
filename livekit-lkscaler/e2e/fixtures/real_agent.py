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

Environment: LKSCALER_BACKEND, LKSCALER_NAMESPACE, LKSCALER_POD_ID, LKSCALER_ZK_HOSTS,
LKSCALER_REDIS_URL, LKSCALER_ROOM_TARGET_N, LKSCALER_OVERFLOW_MARGIN,
LKSCALER_RESERVATION_TTL_SEC, LKSCALER_SYNC_INTERVAL_MS, LKSCALER_LOAD_THRESHOLD,
LKSCALER_POD_STATE_TTL_SEC, plus the SDK's own LIVEKIT_URL / LIVEKIT_API_KEY /
LKSCALER_API_SECRET-equivalent LIVEKIT_API_SECRET.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
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


def _publish(
    cluster_store: ClusterCapableStore,
    *,
    pod_id: str,
    occupancy: PodOccupancy,
    room_target_n: int,
) -> None:
    cluster_store.publish_pod_state(
        PodState(
            pod_id=pod_id,
            free_slots=occupancy.free_slots(room_target_n=room_target_n),
            active_rooms=occupancy.active_rooms,
            reservations=occupancy.reservations,
            updated_at=datetime.now(UTC),
        )
    )


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
    config = _config_from_env()
    store, cluster_store, closer = backend if backend is not None else _build_backend()
    tracker = WorkerTracker(store=store, cluster_store=cluster_store, pod_id=config.pod_id)
    notifying = NotifyingReservationStore(inner=store, tracker=tracker)
    base_load = build_load_fnc(config=config, store=notifying, tracker=tracker)
    on_request = build_on_request_handler(config=config, store=notifying, tracker=tracker)

    def load_fnc(server: AgentServer) -> float:
        tracker.attach(server)
        return float(base_load())

    async def entrypoint(ctx: JobContext) -> None:
        job_id = ctx.job.id
        tracker.release_reservation(job_id)
        if cluster_store is not None:
            _publish(
                cluster_store,
                pod_id=config.pod_id,
                occupancy=tracker.get_local_occupancy(),
                room_target_n=config.room_target_n,
            )
        logger.info("job assigned pod=%s job=%s", config.pod_id, job_id)
        await ctx.connect()
        try:
            await asyncio.Event().wait()
        finally:
            logger.info("job finished pod=%s job=%s", config.pod_id, job_id)

    options = WorkerOptions(
        entrypoint_fnc=entrypoint,
        # the hook is duck-typed on purpose (it works across SDK versions); the runtime
        # contract -- id, accept keywords, reject(terminate=...) -- matches JobRequest.
        request_fnc=cast("Callable[[JobRequest], Awaitable[None]]", on_request),
        load_fnc=load_fnc,
        load_threshold=float(os.environ.get("LKSCALER_LOAD_THRESHOLD", "0.7")),
        agent_name=os.environ.get("LKSCALER_AGENT_NAME", ""),
    )
    return options, tracker, cluster_store, closer


def main() -> None:
    global _running

    options, tracker, cluster_store, closer = build_worker()
    namespace = os.environ.get("LKSCALER_NAMESPACE", "livekit-lkscaler")
    pod_id = os.environ.get("LKSCALER_POD_ID", "real-agent")
    room_target_n = _env_int("LKSCALER_ROOM_TARGET_N", 2)
    sync_interval_ms = _env_int("LKSCALER_SYNC_INTERVAL_MS", 500)

    def publish() -> None:
        if cluster_store is not None:
            _publish(
                cluster_store,
                pod_id=pod_id,
                occupancy=tracker.get_local_occupancy(),
                room_target_n=room_target_n,
            )

    def sync_loop() -> None:
        interval = sync_interval_ms / 1000
        while _running:
            publish()
            if cluster_store is not None:
                cluster_store.remove_expired(now=datetime.now(UTC))
            time.sleep(interval)

    publish()
    threading.Thread(target=sync_loop, daemon=True).start()
    logger.info(
        "real agent starting pod=%s backend=%s namespace=%s threshold=%s",
        pod_id,
        os.environ.get("LKSCALER_BACKEND", "zookeeper"),
        namespace,
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
