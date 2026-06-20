"""Test agent for E2E bin-packing verification.

This agent:
- Connects to LiveKit with custom on_request and load_fnc hooks
- Tracks active rooms and reservations
- Reports cluster state to ZooKeeper
- Verifies bin-pack placement behavior
"""

import asyncio
import logging
import os
from datetime import UTC, datetime

from livekit import agents
from livekit.agents import JobContext, JobRequest, WorkerOptions
from livekit.agents.llm import ChatMessage, ChatMessageRoleEnum

from lkscaler_core import BinpackConfig, ClusterSnapshotCache, InMemoryReservationStore, PodOccupancy
from lkscaler_livekit import build_load_fnc, build_on_request_handler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SimpleRoomTracker:
    """Tracks active rooms and reservations for a single pod."""

    def __init__(self) -> None:
        self.active_rooms: set[str] = set()
        self.reservations: dict[str, str] = {}  # job_id -> pod_id

    def add_room(self, room_id: str) -> None:
        self.active_rooms.add(room_id)
        logger.info(f"Room started: {room_id}, total active: {len(self.active_rooms)}")

    def remove_room(self, room_id: str) -> None:
        self.active_rooms.discard(room_id)
        logger.info(f"Room ended: {room_id}, total active: {len(self.active_rooms)}")

    def add_reservation(self, job_id: str) -> None:
        self.reservations[job_id] = job_id
        logger.info(f"Reservation added: {job_id}, total: {len(self.reservations)}")

    def remove_reservation(self, job_id: str) -> None:
        self.reservations.pop(job_id, None)
        logger.info(f"Reservation removed: {job_id}, total: {len(self.reservations)}")

    def get_local_occupancy(self) -> PodOccupancy:
        return PodOccupancy(
            active_rooms=len(self.active_rooms),
            reservations=len(self.reservations),
        )

    def get_cluster_free_slots(self) -> dict[str, int]:
        """Stub: return empty for now; will integrate with snapshot cache."""
        return {}


def setup(ctx: JobContext) -> None:
    """Setup agent with lkscaler hooks."""
    # Configuration
    config = BinpackConfig(
        namespace=os.getenv("LKSCALER_NAMESPACE", "livekit-lkscaler"),
        pod_id=os.getenv("LKSCALER_POD_ID", "agent-unknown"),
        room_target_n=int(os.getenv("LKSCALER_ROOM_TARGET_N", "3")),
        overflow_margin=int(os.getenv("LKSCALER_OVERFLOW_MARGIN", "1")),
        reservation_ttl_sec=int(os.getenv("LKSCALER_RESERVATION_TTL_SEC", "30")),
        zk_session_timeout_sec=int(os.getenv("LKSCALER_ZK_SESSION_TIMEOUT_SEC", "10")),
        sync_interval_ms=int(os.getenv("LKSCALER_SYNC_INTERVAL_MS", "250")),
    )

    logger.info(f"Agent {config.pod_id} starting with room_target_n={config.room_target_n}")

    # Storage and tracking
    store = InMemoryReservationStore()
    tracker = SimpleRoomTracker()

    # Build hooks
    on_request = build_on_request_handler(config=config, store=store, tracker=tracker)
    load_fnc = build_load_fnc(config=config, store=store, tracker=tracker)

    # Setup agent handlers
    ctx.on_job_request(on_request)

    @ctx.on_room_started
    async def on_room_started() -> None:
        """Track new room."""
        logger.info(f"Room started: {ctx.room.name}")
        tracker.add_room(ctx.room.name)

    @ctx.on_room_finished
    async def on_room_finished() -> None:
        """Track room termination."""
        logger.info(f"Room finished: {ctx.room.name}")
        tracker.remove_room(ctx.room.name)

    # Set load function
    ctx.set_load_fnc(load_fnc)

    logger.info(f"Agent {config.pod_id} setup complete")


if __name__ == "__main__":
    # Get configuration from environment
    api_key = os.getenv("LIVEKIT_API_KEY", "devkey")
    api_secret = os.getenv("LIVEKIT_API_SECRET", "secret")
    ws_url = os.getenv("LIVEKIT_URL", "ws://livekit:7880")

    logger.info(f"Connecting to LiveKit at {ws_url}")

    worker_options = WorkerOptions(api_key=api_key, api_secret=api_secret)

    agents.run_app(setup=setup, opts=worker_options)
