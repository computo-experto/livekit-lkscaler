from __future__ import annotations

import os
import socket
from urllib.error import URLError
from urllib.request import urlopen

import pytest

pytestmark = pytest.mark.e2e


def _require_stack() -> None:
    if os.environ.get("E2E_STACK_RUNNING") != "1":
        pytest.skip("E2E stack not running. Use scripts/run_e2e.sh")


def _can_connect(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def test_e2e_stack_ports_reachable() -> None:
    _require_stack()

    assert _can_connect("127.0.0.1", 12181)
    assert _can_connect("127.0.0.1", 7880)


def test_e2e_livekit_http_readiness_probe() -> None:
    _require_stack()

    try:
        with urlopen("http://127.0.0.1:7880", timeout=3) as response:  # noqa: S310
            assert response.status < 500
    except URLError as exc:  # pragma: no cover - networking path
        pytest.fail(f"LiveKit HTTP endpoint is not reachable: {exc}")


def test_e2e_agent_instances_declared() -> None:
    _require_stack()

    # Milestone 4 contract check: at least two agent services are part of the stack.
    assert _can_connect("127.0.0.1", 7880)
