from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.proof


def _require_artifacts_mode() -> None:
    if os.environ.get("PROOF_GATE_ARTIFACTS") != "1":
        pytest.skip("Proof artifact checks run only via scripts/run_proof_gate.sh")


def _artifact_path(name: str) -> Path:
    return Path(__file__).resolve().parents[1] / "artifacts" / name


def test_proof_artifacts_exist_and_non_empty() -> None:
    _require_artifacts_mode()

    for artifact in ["compose-ps.txt", "compose-logs.txt"]:
        path = _artifact_path(artifact)
        assert path.exists(), f"Missing artifact: {path}"
        assert path.stat().st_size > 0, f"Artifact is empty: {path}"


def test_compose_ps_has_required_services_and_health() -> None:
    _require_artifacts_mode()

    text = _artifact_path("compose-ps.txt").read_text(encoding="utf-8")

    for service in ["zk1", "zk2", "zk3", "livekit", "agent1", "agent2"]:
        assert service in text, f"Service not found in compose ps artifact: {service}"

    assert "healthy" in text, "Expected healthy services in compose ps artifact"


def _uptime_seconds(fragment: str) -> int:
    fragment = fragment.strip().lower()
    if "less than a second" in fragment:
        return 0

    seconds = re.search(r"(\d+)\s+seconds?", fragment)
    if seconds:
        return int(seconds.group(1))

    minutes = re.search(r"(\d+)\s+minutes?", fragment)
    if minutes:
        return int(minutes.group(1)) * 60

    hours = re.search(r"(\d+)\s+hours?", fragment)
    if hours:
        return int(hours.group(1)) * 3600

    return -1


def test_compose_ps_quantitative_thresholds() -> None:
    _require_artifacts_mode()

    lines = _artifact_path("compose-ps.txt").read_text(encoding="utf-8").splitlines()
    service_rows = [line for line in lines if line.startswith("e2e-")]

    assert len(service_rows) == 6, f"Expected 6 services, found {len(service_rows)}"

    healthy_rows = [line for line in service_rows if "(healthy)" in line]
    assert len(healthy_rows) >= 4, (
        f"Expected at least 4 healthy services, found {len(healthy_rows)}"
    )

    # Quantitative stability threshold: healthy services should have stayed up for >= 5s.
    for row in healthy_rows:
        up_index = row.find("Up ")
        assert up_index >= 0, f"Missing uptime segment in row: {row}"
        uptime_fragment = row[up_index + 3 :]
        uptime_sec = _uptime_seconds(uptime_fragment)
        assert uptime_sec >= 5, f"Healthy service uptime below threshold (5s): {row}"


def test_compose_logs_have_no_critical_crash_signatures() -> None:
    _require_artifacts_mode()

    logs = _artifact_path("compose-logs.txt").read_text(encoding="utf-8")
    lower_logs = logs.lower()

    forbidden_signatures = [
        "traceback (most recent call last):",
        "segmentation fault",
        "panic:",
    ]

    for signature in forbidden_signatures:
        assert signature not in lower_logs, f"Found crash signature in logs: {signature}"


def test_compose_logs_quantitative_startup_signals() -> None:
    _require_artifacts_mode()

    logs = _artifact_path("compose-logs.txt").read_text(encoding="utf-8")

    lines = logs.splitlines()
    assert len(lines) >= 80, f"Expected at least 80 log lines, found {len(lines)}"

    # Quantitative startup indicators for the current stack topology.
    assert logs.count("Starting quorum peer") >= 3
    assert logs.count("starting LiveKit server") >= 1
