"""Milestone 9: KEDA scales a real agent Deployment from the LKScaler placement signal.

The stack is a kind cluster (see `e2e/kind/`) with a production-mode LiveKit server, one
real `livekit-agents` worker, ZooKeeper, and the external scaler from `packages/lkscaler-keda`.
Replicas are read from the Deployment; rooms are created through the LiveKit API.

The scaler reports `required_workers = ceil((used_slots + minFreeSlots) / slotsPerWorker)`,
and the ScaledObject asks for `minFreeSlots=2` with `slotsPerWorker=3`, so the expected
replica counts below follow from how many rooms the pool is actually holding.

Run with `scripts/run_keda_scale_e2e.sh`.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import time
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

import aiohttp
import pytest
import pytest_asyncio
from livekit import api
from lkscaler_core.zookeeper import KazooNodeClient, ZooKeeperStateStore

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]

SERVER_HTTP = os.environ.get("LKSCALER_E2E_SERVER_HTTP", "http://127.0.0.1:17880")
API_KEY = "devkey"
API_SECRET = "devsecretdevsecretdevsecretdevsecret"
AGENT_NAME = "m9real"
NAMESPACE = "livekit-system"
DEPLOYMENT = "livekit-agents"
ROOM_TARGET_N = 2
OVERFLOW_MARGIN = 1
MIN_FREE_SLOTS = 2
API_TIMEOUT_SEC = 15.0
POLL_INTERVAL_SEC = 2.0
ZK_HOSTS = os.environ.get("LKSCALER_E2E_ZK_HOSTS", "127.0.0.1:2181")
STORE_NAMESPACE = "livekit-lkscaler"
# LiveKit drops a job that no registered worker claims, so a dispatch is re-offered at this cadence.
DISPATCH_ATTEMPT_SEC = 8.0


def _require_cluster() -> None:
    if os.environ.get("KEDA_SCALE_E2E") != "1":
        pytest.skip("KEDA scale checks run only via scripts/run_keda_scale_e2e.sh")


def _expected_replicas(used_slots: int) -> int:
    slots_per_worker = ROOM_TARGET_N + OVERFLOW_MARGIN
    return math.ceil(max(used_slots + MIN_FREE_SLOTS, 1) / slots_per_worker)


def _replicas() -> int:
    result = subprocess.run(
        [
            "kubectl",
            "get",
            "deployment",
            DEPLOYMENT,
            "-n",
            NAMESPACE,
            "-o",
            "jsonpath={.spec.replicas}",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return int(result.stdout.strip() or "0")


def _ready_replicas() -> int:
    result = subprocess.run(
        [
            "kubectl",
            "get",
            "deployment",
            DEPLOYMENT,
            "-n",
            NAMESPACE,
            "-o",
            "jsonpath={.status.readyReplicas}",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return int(result.stdout.strip() or "0")


async def _poll(check: Callable[[], Any], *, describe: str, timeout: float) -> Any:
    deadline = time.monotonic() + timeout
    last: Any = None
    while time.monotonic() < deadline:
        last = check()
        if last:
            return last
        await _async_sleep()
    pytest.fail(f"timed out after {timeout}s waiting for {describe} (last observed: {last!r})")


async def _async_sleep() -> None:
    import asyncio

    await asyncio.sleep(POLL_INTERVAL_SEC)


@pytest.fixture(scope="module")
def store() -> Iterator[ZooKeeperStateStore]:
    """The same store the workers publish to and the scaler reads."""
    _require_cluster()
    zk_client = KazooNodeClient(hosts=[ZK_HOSTS])
    zk_client.start()
    try:
        yield ZooKeeperStateStore(namespace=STORE_NAMESPACE, client=zk_client)
    finally:
        zk_client.close()


def _used_slots(store: ZooKeeperStateStore) -> int:
    return sum(
        state.active_rooms + state.reservations for state in store.read_pod_states().values()
    )


async def _dispatch(client: api.LiveKitAPI, rooms: list[str], room_name: str) -> None:
    await client.room.create_room(api.CreateRoomRequest(name=room_name))
    if room_name not in rooms:
        rooms.append(room_name)
    await client.agent_dispatch.create_dispatch(
        api.CreateAgentDispatchRequest(agent_name=AGENT_NAME, room=room_name)
    )


async def _dispatch_until_booked(
    client: api.LiveKitAPI,
    store: ZooKeeperStateStore,
    rooms: list[str],
    room_name: str,
    *,
    timeout: float,
) -> None:
    """Offer one room until the worker pool books it, as the placement proof requires.

    The worker registers with LiveKit a moment after its pod turns ready, and LiveKit refuses a
    dispatch while no worker is registered. Recreating the room clears the dropped dispatch so a
    retry cannot double-book the slot.
    """
    baseline = _used_slots(store)
    deadline = time.monotonic() + timeout
    while True:
        await _dispatch(client, rooms, room_name)
        attempt_end = min(deadline, time.monotonic() + DISPATCH_ATTEMPT_SEC)
        while time.monotonic() < attempt_end:
            if _used_slots(store) > baseline:
                return
            await _async_sleep()
        if time.monotonic() >= deadline:
            pytest.fail(f"{room_name} was never accepted by the worker pool within {timeout}s")
        await _release_rooms(client, rooms)


async def _release_rooms(client: api.LiveKitAPI, rooms: list[str]) -> None:
    for room_name in list(rooms):
        try:
            await client.room.delete_room(api.DeleteRoomRequest(room=room_name))
        except api.TwirpError as exc:
            if exc.code != "not_found":
                raise
        rooms.remove(room_name)


async def _poll_replicas(
    store: ZooKeeperStateStore, expected: int, *, describe: str, timeout: float
) -> None:
    """Wait for ready replicas, failing with the evidence a diagnosis needs."""
    deadline = time.monotonic() + timeout
    last = 0
    while time.monotonic() < deadline:
        last = _ready_replicas()
        if last >= expected:
            return
        await _async_sleep()
    pytest.fail(
        f"timed out after {timeout}s waiting for {describe}; "
        f"ready replicas={last}, used slots={_used_slots(store)}, "
        f"deployment={_describe_deployment()}"
    )


def _describe_deployment() -> dict[str, object]:
    result = subprocess.run(
        ["kubectl", "get", "deployment", DEPLOYMENT, "-n", NAMESPACE, "-o", "json"],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    payload: dict[str, object] = json.loads(result.stdout)
    return payload


@pytest_asyncio.fixture
async def client() -> AsyncIterator[tuple[api.LiveKitAPI, list[str]]]:
    _require_cluster()
    rooms: list[str] = []
    async with api.LiveKitAPI(
        SERVER_HTTP, API_KEY, API_SECRET, timeout=aiohttp.ClientTimeout(total=API_TIMEOUT_SEC)
    ) as api_client:
        try:
            yield api_client, rooms
        finally:
            await _release_rooms(api_client, rooms)


async def test_keda_scales_the_worker_deployment_up_and_back_down(
    client: tuple[api.LiveKitAPI, list[str]],
    store: ZooKeeperStateStore,
) -> None:
    api_client, rooms = client

    await _poll(
        lambda: _ready_replicas() == _expected_replicas(0) or None,
        describe=f"{_expected_replicas(0)} ready worker at rest",
        timeout=180,
    )

    for index in range(1, ROOM_TARGET_N + 1):
        await _dispatch_until_booked(
            api_client, store, rooms, f"m9-scale-{index}", timeout=180
        )
    used_one_worker = ROOM_TARGET_N
    assert _used_slots(store) == used_one_worker, (
        f"the pool should hold {used_one_worker} slots before the scale assertion, "
        f"saw {_used_slots(store)}"
    )
    await _poll_replicas(
        store,
        _expected_replicas(used_one_worker),
        describe=(
            f"replicas to reach {_expected_replicas(used_one_worker)} with {used_one_worker} rooms"
        ),
        timeout=240,
    )
    scaled_to = _replicas()
    assert scaled_to >= _expected_replicas(used_one_worker), (
        f"expected at least {_expected_replicas(used_one_worker)} replicas, saw {scaled_to}: "
        f"{_describe_deployment()}"
    )

    await _release_rooms(api_client, rooms)
    await _poll(
        lambda: _used_slots(store) == 0 or None,
        describe="the pool to report no used slots after the rooms are gone",
        timeout=60,
    )
    await _poll(
        lambda: _ready_replicas() <= _expected_replicas(0) or None,
        describe=f"replicas to fall back to {_expected_replicas(0)} once the rooms are gone",
        timeout=240,
    )
