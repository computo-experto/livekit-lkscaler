"""End-to-end coordination tests against a real backend.

Two backend-wired agents (`packed-agent1`, `packed-agent2`) share one namespace and one
backend, selected by LKSCALER_E2E_BACKEND (`zookeeper` | `redis`), and expose the real
placement functions over HTTP. These tests drive load through them and assert on the
cluster view that comes back from the backend — never on container logs.

Run with `make test-e2e-backends`, which brings the stack up once per backend.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

import pytest

pytestmark = pytest.mark.e2e

AGENT1 = "http://127.0.0.1:18090"
AGENT2 = "http://127.0.0.1:18091"
COMPOSE_FILE = Path(__file__).resolve().parents[1] / "compose.yaml"
RESERVATION_TTL_SEC = 5


def _require_stack() -> None:
    if os.environ.get("E2E_STACK_RUNNING") != "1":
        pytest.skip("E2E stack not running. Use scripts/run_e2e_backends.sh")
    for agent in (AGENT1, AGENT2):
        try:
            _get(f"{agent}/health")
        except URLError:
            pytest.skip("backend-wired agents are not running; start the `backends` profile")


def _backend() -> str:
    return os.environ.get("LKSCALER_E2E_BACKEND", "zookeeper")


def _get(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=5) as response:  # noqa: S310
        parsed: Any = json.loads(response.read())
    return parsed if isinstance(parsed, dict) else {}


def _post(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = Request(url, data=json.dumps(payload).encode(), method="POST")  # noqa: S310
    request.add_header("Content-Type", "application/json")
    with urlopen(request, timeout=5) as response:
        parsed: Any = json.loads(response.read())
    return parsed if isinstance(parsed, dict) else {}


def _wait_for(check: Callable[[], Any], *, describe: str, timeout: float = 25.0) -> Any:
    deadline = time.monotonic() + timeout
    last: Any = None
    while time.monotonic() < deadline:
        try:
            last = check()
        except OSError as exc:
            last = f"{type(exc).__name__}: {exc}"
        else:
            if last:
                return last
        time.sleep(0.2)
    pytest.fail(f"timed out after {timeout}s waiting for {describe} (last observed: {last!r})")


def _occupancy(agent: str) -> dict[str, Any]:
    return _get(f"{agent}/occupancy")


def _load(agent: str) -> float:
    return float(_get(f"{agent}/load")["load"])


def _cluster(agent: str) -> dict[str, int]:
    raw: Any = _get(f"{agent}/cluster")["free_slots_by_pod"]
    return {str(pod_id): int(free_slots) for pod_id, free_slots in raw.items()}


def _compose(*args: str) -> None:
    subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "--profile", "backends", *args],
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture(autouse=True)
def clean_workers() -> Iterator[None]:
    _require_stack()
    for agent in (AGENT1, AGENT2):
        _post(f"{agent}/reset", {})
    _wait_for(
        lambda: _occupancy(AGENT1)["reservations"] == 0 and _occupancy(AGENT2)["reservations"] == 0,
        describe="both workers to start clean",
    )
    yield


def test_workers_report_the_configured_backend() -> None:
    for agent in (AGENT1, AGENT2):
        health = _get(f"{agent}/health")
        assert health["ok"] is True

        occupancy = _occupancy(agent)
        assert occupancy["backend"] == _backend()
        assert occupancy["room_target_n"] == 2
        assert occupancy["overflow_margin"] == 1


def test_winner_keeps_winning_until_it_reaches_its_target() -> None:
    assert _post(f"{AGENT1}/request", {"job_id": "job-1"})["accepted"] is True

    _wait_for(
        lambda: _load(AGENT1) == 0.0 and _load(AGENT2) == 1.0,
        describe="the worker holding a claim to advertise itself as the winner",
    )

    assert _post(f"{AGENT1}/request", {"job_id": "job-2"})["accepted"] is True
    assert _post(f"{AGENT1}/complete", {"job_id": "job-1"})["ok"] is True

    _wait_for(
        lambda: _load(AGENT1) == 1.0 and _load(AGENT2) == 0.0,
        describe="spillover once the first worker reached its target",
    )

    assert _post(f"{AGENT2}/request", {"job_id": "job-3"})["accepted"] is True


def test_overflow_guard_bounds_each_worker() -> None:
    for index in range(2):
        job_id = f"fill-{index}"
        assert _post(f"{AGENT1}/request", {"job_id": job_id})["accepted"] is True
        assert _post(f"{AGENT1}/complete", {"job_id": job_id})["ok"] is True

    within_margin = _post(f"{AGENT1}/request", {"job_id": "margin"})
    over_bound = _post(f"{AGENT1}/request", {"job_id": "beyond-margin"})

    assert within_margin["accepted"] is True
    assert over_bound["accepted"] is False
    assert over_bound["reason"] == "overflow_guard"

    occupancy = _occupancy(AGENT1)
    assert occupancy["active_rooms"] + occupancy["reservations"] <= 3


def test_releasing_a_claim_frees_the_slot() -> None:
    assert _post(f"{AGENT1}/request", {"job_id": "job-1"})["accepted"] is True
    _wait_for(lambda: _occupancy(AGENT1)["reservations"] == 1, describe="the claim to be recorded")

    assert _post(f"{AGENT1}/release", {"job_id": "job-1"})["ok"] is True

    _wait_for(lambda: _occupancy(AGENT1)["reservations"] == 0, describe="the claim to be released")
    assert _post(f"{AGENT1}/request", {"job_id": "job-2"})["accepted"] is True


def test_a_claim_that_is_never_completed_expires() -> None:
    assert _post(f"{AGENT1}/request", {"job_id": "abandoned"})["accepted"] is True
    _wait_for(lambda: _occupancy(AGENT1)["reservations"] == 1, describe="the claim to be recorded")

    _wait_for(
        lambda: _occupancy(AGENT1)["reservations"] == 0,
        describe=f"the abandoned claim to expire after {RESERVATION_TTL_SEC}s",
        timeout=RESERVATION_TTL_SEC * 4,
    )


def test_a_dead_worker_leaves_the_cluster_view() -> None:
    assert _post(f"{AGENT2}/request", {"job_id": "job-1"})["accepted"] is True
    _wait_for(
        lambda: len(_cluster(AGENT1)) == 2,
        describe="both workers to be visible in the cluster view",
    )

    _compose("stop", "packed-agent2")
    try:
        _wait_for(
            lambda: "packed-agent2" not in _cluster(AGENT1),
            describe="the stopped worker to leave the cluster view",
            timeout=25.0,
        )
    finally:
        _compose("start", "packed-agent2")
        _wait_for(
            lambda: _get(f"{AGENT2}/health")["ok"] is True,
            describe="the restarted worker to become healthy again",
        )
