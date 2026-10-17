"""Milestone 9: rooms dispatched to real LiveKit Agents workers placed by the LKScaler hooks.

The stack is the `real-agents` profile: a production-mode LiveKit server (so the load
signal actually gates dispatch, which `--dev` disables by setting the threshold to
infinity) and three real `livekit-agents` workers built from
`e2e/fixtures/real_agent.py`. Jobs are created by real dispatches through the LiveKit
API, and every assertion reads the coordination backend that both the workers and this
test see -- never container logs.

Run with `make test-real-agent-scenarios`.
"""

from __future__ import annotations

import asyncio
import inspect
import os
import time
from collections.abc import AsyncIterator, Callable
from functools import partial
from typing import Any

import aiohttp
import pytest
import pytest_asyncio
from livekit import api
from lkscaler_core.state import ClusterStateStore, PodState

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]

SERVER_HTTP = os.environ.get("LKSCALER_E2E_SERVER_HTTP", "http://127.0.0.1:17880")
API_KEY = "devkey"
API_SECRET = "devsecretdevsecretdevsecretdevsecret"
AGENT_NAME = "m9real"
NAMESPACE = os.environ.get("LKSCALER_E2E_REAL_NAMESPACE", "livekit-lkscaler-real")
PODS = ("real-agent1", "real-agent2", "real-agent3")
ROOM_TARGET_N = 2
OVERFLOW_MARGIN = 1
ZK_HOSTS = ["127.0.0.1:12181"]
REDIS_URL = "redis://127.0.0.1:16379/0"
API_TIMEOUT_SEC = 15.0
LOAD_THRESHOLD = 0.7
POD_HTTP = {
    "real-agent1": "http://127.0.0.1:18092",
    "real-agent2": "http://127.0.0.1:18093",
    "real-agent3": "http://127.0.0.1:18094",
}

Stack = tuple[ClusterStateStore, api.LiveKitAPI, list[str]]


def _open_store() -> tuple[Any, Any]:
    if os.environ.get("LKSCALER_E2E_BACKEND", "zookeeper") == "redis":
        from lkscaler_core.redis import RedisClientAdapter, RedisStateStore

        adapter = RedisClientAdapter(url=REDIS_URL)
        adapter.connect()
        return RedisStateStore(namespace=NAMESPACE, client=adapter, pod_state_ttl_sec=30), adapter
    from lkscaler_core.zookeeper import KazooNodeClient, ZooKeeperStateStore

    client = KazooNodeClient(hosts=ZK_HOSTS, session_timeout_sec=10)
    client.start()
    return ZooKeeperStateStore(namespace=NAMESPACE, client=client), client


def _states(store: ClusterStateStore) -> dict[str, PodState]:
    return store.read_pod_states()


def _registered_pods(store: ClusterStateStore) -> dict[str, PodState] | None:
    states = _states(store)
    return states if all(pod_id in states for pod_id in PODS) else None


def _rooms(store: ClusterStateStore, pod_id: str) -> int:
    return _states(store)[pod_id].active_rooms


def _held(store: ClusterStateStore, pod_id: str) -> int:
    state = _states(store)[pod_id]
    return state.active_rooms + state.reservations


def _rooms_at(store: ClusterStateStore, pod_id: str, count: int) -> bool | None:
    """True once `pod_id` reports exactly `count` rooms."""
    return True if _rooms(store, pod_id) == count else None


def _accepted_rooms(store: ClusterStateStore) -> int:
    """Rooms the pool is holding, across every worker."""
    return sum(state.active_rooms for state in _states(store).values())


def _all_idle(store: ClusterStateStore) -> bool | None:
    """True once no worker holds a room, so a scenario starts from a settled fleet."""
    states = _states(store)
    return True if not any(state.active_rooms for state in states.values()) else None


def _lone_holder(store: ClusterStateStore, *, expects_rooms: int) -> str | None:
    states = _states(store)
    holders = [pod_id for pod_id, state in states.items() if state.active_rooms == expects_rooms]
    return holders[0] if len(holders) == 1 else None


async def _poll(check: Callable[[], Any], *, describe: str, timeout: float = 60.0) -> Any:
    deadline = time.monotonic() + timeout
    last: Any = None
    while time.monotonic() < deadline:
        last = check()
        if inspect.isawaitable(last):
            last = await last
        if last:
            return last
        await asyncio.sleep(0.25)
    pytest.fail(f"timed out after {timeout}s waiting for {describe} (last observed: {last!r})")


async def _reported_load(pod_id: str) -> float | None:
    """The load value this worker last handed the server, not its live computation."""
    payload = await _get_json(f"{POD_HTTP[pod_id]}/load")
    reported = payload.get("reported")
    return None if reported is None else float(reported)


async def _get_json(url: str) -> dict[str, Any]:
    async with aiohttp.ClientSession() as session:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=API_TIMEOUT_SEC)
        ) as response:
            payload: Any = await response.json()
    return payload if isinstance(payload, dict) else {}


async def _dispatch(client: api.LiveKitAPI, rooms: list[str], room_name: str) -> None:
    await client.room.create_room(api.CreateRoomRequest(name=room_name))
    rooms.append(room_name)
    await client.agent_dispatch.create_dispatch(
        api.CreateAgentDispatchRequest(agent_name=AGENT_NAME, room=room_name)
    )


async def _delete_room(client: api.LiveKitAPI, room_name: str) -> None:
    try:
        await client.room.delete_room(api.DeleteRoomRequest(room=room_name))
    except api.TwirpError as exc:
        if exc.code != "not_found":
            raise


async def _room_exists(client: api.LiveKitAPI, room_name: str) -> bool | None:
    listed = await client.room.list_rooms(api.ListRoomsRequest())
    return True if any(room.name == room_name for room in listed.rooms) else None


async def _only_holder_is_eligible(holder: str, others: list[str]) -> bool | None:
    """True once every worker has reported a load that leaves the server one choice."""
    holder_load = await _reported_load(holder)
    if holder_load is None or holder_load >= LOAD_THRESHOLD:
        return None
    for pod_id in others:
        load = await _reported_load(pod_id)
        if load is None or load < LOAD_THRESHOLD:
            return None
    return True


@pytest_asyncio.fixture
async def stack() -> AsyncIterator[Stack]:
    if os.environ.get("E2E_STACK_RUNNING") != "1":
        pytest.skip("E2E stack not running. Use scripts/run_e2e_real_agents.sh")
    store, closer = _open_store()
    rooms: list[str] = []
    async with api.LiveKitAPI(
        SERVER_HTTP, API_KEY, API_SECRET, timeout=aiohttp.ClientTimeout(total=API_TIMEOUT_SEC)
    ) as client:
        await _poll(
            lambda: _registered_pods(store),
            describe=f"the real workers {PODS} to register and publish pod state",
            timeout=120,
        )
        pool = sorted(store.free_slots_by_pod())
        assert pool == sorted(PODS), (
            f"the real workers must be alone in their scaling pool, found {pool}"
        )
        # Room deletion ends a job asynchronously, so a scenario that starts while the
        # previous one is still draining sees two holders and never a lone one. Wait for
        # the pool to settle on the backend's own state instead of on a clock.
        await _poll(
            lambda: _all_idle(store),
            describe="the pool to be idle before the scenario dispatches",
            timeout=30,
        )
        try:
            yield store, client, rooms
        finally:
            for room_name in rooms:
                await _delete_room(client, room_name)
            closer.close()


async def test_dispatched_rooms_pack_onto_one_real_worker(stack: Stack) -> None:
    store, client, rooms = stack

    await _dispatch(client, rooms, "m9-pack-1")
    first_holder = await _poll(
        lambda: _lone_holder(store, expects_rooms=1),
        describe="a real worker to accept the first dispatched room",
    )

    # The server keeps packing onto the same worker only once every worker has reported
    # its load, so wait for the holder to be the only candidate left.
    others = [pod_id for pod_id in PODS if pod_id != first_holder]
    await _poll(
        lambda: _only_holder_is_eligible(first_holder, others),
        describe=f"{first_holder} to be the only worker the server can choose",
    )

    await _dispatch(client, rooms, "m9-pack-2")
    await _poll(
        lambda: _rooms(store, first_holder) >= 2 or None,
        describe=f"{first_holder} to accept the second room as well",
    )

    assert _rooms(store, first_holder) == 2
    for pod_id in PODS:
        if pod_id != first_holder:
            assert _rooms(store, pod_id) == 0, (
                f"{pod_id} took a room while {first_holder} had spare slots"
            )
        assert _held(store, pod_id) <= ROOM_TARGET_N + OVERFLOW_MARGIN

    listed = await client.agent_dispatch.list_dispatch("m9-pack-1")
    # creating the room also makes the server auto-dispatch the unnamed pool, so look for
    # our named dispatch rather than expecting to be the only entry.
    assert any(dispatch.agent_name == AGENT_NAME for dispatch in listed)


async def test_deleting_the_room_releases_the_worker_slot(stack: Stack) -> None:
    store, client, rooms = stack

    await _dispatch(client, rooms, "m9-release-1")
    holder = await _poll(
        lambda: _lone_holder(store, expects_rooms=1),
        describe="a real worker to accept the dispatched room",
    )
    await _poll(
        lambda: _room_exists(client, "m9-release-1"),
        describe="the dispatched room to exist on the server",
    )

    await _delete_room(client, "m9-release-1")
    rooms.remove("m9-release-1")

    await _poll(
        lambda: _rooms(store, holder) == 0 or None,
        describe=f"{holder} to release the slot once the room ends",
    )


async def test_steady_dispatch_packs_one_worker_to_its_target(stack: Stack) -> None:
    store, client, rooms = stack

    await _dispatch(client, rooms, "m9-steady-1")
    first = await _poll(
        lambda: _lone_holder(store, expects_rooms=1),
        describe="a real worker to accept the first room of a steady stream",
    )

    for index in range(2, ROOM_TARGET_N + 1):
        await _dispatch(client, rooms, f"m9-steady-{index}")
        await _poll(
            partial(_rooms_at, store, first, index),
            describe=f"{first} to accept room {index} of the steady stream",
        )

    assert _rooms(store, first) == ROOM_TARGET_N
    for pod_id in PODS:
        if pod_id != first:
            assert _rooms(store, pod_id) == 0, (
                f"{pod_id} took a steady room while {first} still had capacity"
            )

    # One room past the target: the full worker reports no capacity, so it spills.
    await _dispatch(client, rooms, "m9-steady-spill")
    await _poll(
        lambda: _accepted_rooms(store) == ROOM_TARGET_N + 1 or None,
        describe="the room past the target to be accepted elsewhere",
    )

    assert _rooms(store, first) == ROOM_TARGET_N, "the worker at target must not take more"
    assert _accepted_rooms(store) == ROOM_TARGET_N + 1
