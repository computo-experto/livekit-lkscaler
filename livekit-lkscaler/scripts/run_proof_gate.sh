#!/usr/bin/env bash
set -euo pipefail

# Milestone 9 proof gate entrypoint.
# Current baseline executes compose-backed E2E checks through the existing runner.
# Future iterations should add soak/fault-injection scenarios and assertions from artifacts.

scripts/run_e2e.sh
PROOF_GATE_ARTIFACTS=1 uv run pytest -m proof \
	packages/lkscaler-core/tests/integration/test_core_proof_gate.py \
	packages/lkscaler-livekit/tests/integration/test_livekit_proof_gate.py \
	e2e/tests/test_proof_gate_artifacts.py
