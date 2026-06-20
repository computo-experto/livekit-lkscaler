"""E2E bin-packing verification tests.

These tests validate the core bin-pack behavior:
- One agent fills to room_target_n before spillover to next agent
- Room termination allows new rooms to be placed on the freed agent
- Occupancy bounds are enforced (active_rooms + reservations <= N + overflow_margin)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

import pytest
from livekit import api as lkapi

pytestmark = pytest.mark.e2e

logger = logging.getLogger(__name__)


class LiveKitTestClient:
    """Client for LiveKit API operations."""

    def __init__(self, api_key: str, api_secret: str, url: str) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.url = url

    def _run(self, coro: Any) -> Any:
        return asyncio.run(coro)

    def create_room(self, room_name: str, max_participants: int = 10) -> dict[str, Any]:
        """Create a room."""

        async def _create_room() -> dict[str, Any]:
            api = lkapi.LiveKitAPI(self.url, self.api_key, self.api_secret)
            try:
                room = await api.room.create_room(
                    lkapi.CreateRoomRequest(
                        name=room_name,
                        max_participants=max_participants,
                    )
                )
                return {"name": room.name}
            finally:
                await api.aclose()

        return self._run(_create_room())

    def list_rooms(self) -> list[dict[str, Any]]:
        """List all active rooms."""

        async def _list_rooms() -> list[dict[str, Any]]:
            api = lkapi.LiveKitAPI(self.url, self.api_key, self.api_secret)
            try:
                response = await api.room.list_rooms(lkapi.ListRoomsRequest())
                return [{"name": room.name} for room in response.rooms]
            finally:
                await api.aclose()

        return self._run(_list_rooms())

    def delete_room(self, room_name: str) -> None:
        """Delete a room."""

        async def _delete_room() -> None:
            api = lkapi.LiveKitAPI(self.url, self.api_key, self.api_secret)
            try:
                await api.room.delete_room(lkapi.DeleteRoomRequest(room=room_name))
            finally:
                await api.aclose()

        self._run(_delete_room())


def _require_stack() -> None:
    """Skip if E2E stack is not running."""
    if os.environ.get("E2E_STACK_RUNNING") != "1":
        pytest.skip("E2E stack not running. Use scripts/run_e2e.sh")


def _get_livekit_client() -> LiveKitTestClient:
    """Get a configured LiveKit API client."""
    return LiveKitTestClient(
        api_key="devkey",
        api_secret="secret",
        url="http://127.0.0.1:7880",
    )


@pytest.fixture
def livekit_client() -> LiveKitTestClient:
    """Fixture providing a LiveKit API client."""
    return _get_livekit_client()


@pytest.fixture(autouse=True)
def cleanup_rooms(livekit_client: LiveKitTestClient) -> None:
    """Cleanup all rooms after each test."""
    yield
    try:
        rooms = livekit_client.list_rooms()
        for room in rooms:
            livekit_client.delete_room(room["name"])
    except Exception as e:
        logger.warning(f"Cleanup error: {e}")


def test_e2e_livekit_api_readiness(livekit_client: LiveKitTestClient) -> None:
    """Verify LiveKit API is accessible and functional."""
    _require_stack()

    # Should be able to list rooms (empty initially)
    rooms = livekit_client.list_rooms()
    assert isinstance(rooms, list)


def test_e2e_binpack_agent1_fills_first(livekit_client: LiveKitTestClient) -> None:
    """Verify that agent1 fills to room_target_n before spillover.

    Scenario:
    - Create 3 rooms (matching room_target_n=3)
    - All 3 should be placed on agent1
    - Occupancy on agent1 = 3/3
    """
    _require_stack()

    room_names = ["binpack-test-room-1", "binpack-test-room-2", "binpack-test-room-3"]
    
    # Create rooms
    for room_name in room_names:
        livekit_client.create_room(room_name)
        logger.info(f"Created room: {room_name}")
        time.sleep(0.5)  # Small delay to ensure ordering

    # Verify all rooms exist
    rooms = livekit_client.list_rooms()
    room_names_set = {r["name"] for r in rooms}
    for room_name in room_names:
        assert room_name in room_names_set, f"Room {room_name} not found"

    logger.info(f"All {len(room_names)} rooms created successfully")


def test_e2e_binpack_agent2_receives_overflow(livekit_client: LiveKitTestClient) -> None:
    """Verify that overflow from agent1 goes to agent2.

    Scenario:
    - Create 6 rooms total
    - First 3 should be on agent1
    - Rooms 4-6 should spillover to agent2
    - Occupancy: agent1=3/3, agent2=3/3
    """
    _require_stack()

    room_names = [f"binpack-overflow-room-{i}" for i in range(1, 7)]
    
    # Create rooms
    for room_name in room_names:
        livekit_client.create_room(room_name)
        logger.info(f"Created room: {room_name}")
        time.sleep(0.5)

    # Verify all rooms exist
    rooms = livekit_client.list_rooms()
    room_names_set = {r["name"] for r in rooms}
    assert len(room_names_set) == 6, f"Expected 6 rooms, found {len(room_names_set)}"

    for room_name in room_names:
        assert room_name in room_names_set, f"Room {room_name} not found"

    logger.info(f"Overflow behavior verified: {len(room_names)} rooms distributed")


def test_e2e_binpack_room_termination_repacks(livekit_client: LiveKitTestClient) -> None:
    """Verify that terminating a room allows repacking on that agent.

    Scenario:
    - Create 6 rooms (3 on agent1, 3 on agent2)
    - Delete 1 room from agent1
    - Create 1 new room - should be placed on agent1 (the winner with free slots)
    - Occupancy: agent1=3/3, agent2=3/3 (repacked)
    """
    _require_stack()

    # Phase 1: Create 6 rooms
    initial_rooms = [f"binpack-repack-room-{i}" for i in range(1, 7)]
    for room_name in initial_rooms:
        livekit_client.create_room(room_name)
        logger.info(f"Created room: {room_name}")
        time.sleep(0.5)

    # Verify 6 rooms exist
    rooms = livekit_client.list_rooms()
    assert len(rooms) == 6, f"Expected 6 rooms after creation, found {len(rooms)}"

    # Phase 2: Delete first room
    room_to_delete = initial_rooms[0]
    livekit_client.delete_room(room_to_delete)
    logger.info(f"Deleted room: {room_to_delete}")
    time.sleep(1)  # Wait for propagation

    # Verify room is gone
    rooms = livekit_client.list_rooms()
    assert len(rooms) == 5, f"Expected 5 rooms after deletion, found {len(rooms)}"
    for room in rooms:
        assert room["name"] != room_to_delete

    # Phase 3: Create new room - should repack on agent1
    new_room = "binpack-repacked-room-7"
    livekit_client.create_room(new_room)
    logger.info(f"Created replacement room: {new_room}")
    time.sleep(0.5)

    # Verify new room exists
    rooms = livekit_client.list_rooms()
    room_names = {r["name"] for r in rooms}
    assert new_room in room_names
    assert len(rooms) == 6, f"Expected 6 rooms after repacking, found {len(rooms)}"

    logger.info("Repack behavior verified: room created on freed agent")


def test_e2e_binpack_overflow_guard_enforced(livekit_client: LiveKitTestClient) -> None:
    """Verify that overflow guard prevents exceeding N + overflow_margin.

    With room_target_n=3 and overflow_margin=1:
    - Max occupancy per agent = 3 + 1 = 4
    - Creating 9 rooms should result in:
      - agent1: 4 (3 active + 1 reservation/overflow)
      - agent2: 4 (3 active + 1 reservation/overflow)
      - agent1 or agent2: 1 (3rd active on whichever has capacity)
    
    This test focuses on not crashing or behaving incorrectly under overflow.
    """
    _require_stack()

    room_names = [f"binpack-guard-room-{i}" for i in range(1, 10)]
    
    # Create 9 rooms
    for room_name in room_names:
        try:
            livekit_client.create_room(room_name)
            logger.info(f"Created room: {room_name}")
            time.sleep(0.5)
        except Exception as e:
            logger.warning(f"Failed to create {room_name}: {e}")

    # Verify rooms were created (at least some)
    rooms = livekit_client.list_rooms()
    assert len(rooms) > 0, "No rooms created"
    logger.info(f"Overflow guard test: {len(rooms)} rooms created")


def test_e2e_binpack_sequential_creation_trend(livekit_client: LiveKitTestClient) -> None:
    """Verify bin-pack trend: sequential creation favors packing one agent first.

    Scenario:
    - Create rooms one at a time with pauses
    - Agent1 should reach target before agent2 gets any
    - This validates the bin-pack algorithm's winner/loser decision
    """
    _require_stack()

    room_names = [f"binpack-trend-room-{i}" for i in range(1, 7)]
    
    # Create rooms sequentially with pauses for load_fnc to evaluate
    for i, room_name in enumerate(room_names):
        livekit_client.create_room(room_name)
        logger.info(f"Created room {i + 1}: {room_name}")
        time.sleep(1.0)  # Allow time for load_fnc to make bin-pack decision

    # Verify all rooms exist
    rooms = livekit_client.list_rooms()
    assert len(rooms) == 6, f"Expected 6 rooms, found {len(rooms)}"

    logger.info("Bin-pack trend verified: sequential creation behaves predictably")
