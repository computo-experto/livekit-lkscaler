# Testing Guide

This project uses layered tests.

## Test layers

- Unit tests: deterministic logic in core and livekit adapter.
- Integration tests: package-level integration behavior.
- E2E tests: compose-backed stack checks in `e2e/tests`.
- KEDA E2E tests: kind-based autoscaling harness in `e2e/tests/test_keda_e2e.py`.

## Common commands

```bash
make test-unit
make test-integration
make test-coverage
make test-e2e
make test-keda-e2e
```

Run all local quality gates for milestones:

```bash
make milestone-gate
```

Release packaging smoke test:

```bash
make release-verify
```

## E2E test suite reference

### Overview

E2E tests validate:
1. **Stack topology and health** — all services (ZooKeeper 3-node, LiveKit, agents) are running and healthy.
2. **Agent integration** — LiveKit agents start and connect with lkscaler hooks.
3. **Bin-pack behavior** — rooms are placed according to bin-pack strategy (fill one agent to target before spillover).
4. **Occupancy bounds** — active rooms + reservations never exceed `N + overflow_margin`.
5. **Room lifecycle** — creation, termination, and re-packing work correctly.
6. **Artifact validation** — startup signals and crash detection from compose logs.

### Test files

#### `test_compose_contract.py`
Basic contract validation that compose.yaml declares required services.

**Tests:**
- `test_compose_declares_required_services()` — verifies all 6 services (zk1, zk2, zk3, livekit, agent1, agent2) are declared in compose.yaml.

#### `test_e2e_stack.py`
Stack connectivity and readiness checks.

**Tests:**
- `test_e2e_stack_ports_reachable()` — verifies ZooKeeper (port 12181) and LiveKit (port 7880) are accessible.
- `test_e2e_livekit_http_readiness_probe()` — verifies LiveKit HTTP endpoint responds.
- `test_e2e_agent_instances_declared()` — verifies at least 2 agent services are part of the stack.

#### `test_e2e_smoke.py`
Minimal smoke test to ensure test framework is functional.

**Tests:**
- `test_e2e_smoke()` — trivial test that always passes (baseline).

#### `test_proof_gate_artifacts.py`
Validates compose artifacts (output from `docker compose ps` and logs) meet quantitative thresholds.

**Tests:**
- `test_proof_artifacts_exist_and_non_empty()` — verifies artifact files exist and are non-empty.
- `test_compose_ps_has_required_services_and_health()` — verifies all 6 services appear in compose ps output with health status.
- `test_compose_ps_quantitative_thresholds()` — verifies:
  - Exactly 6 services declared/running.
  - At least 4 services are healthy (typically zk1, zk2, zk3, livekit).
  - Each healthy service has uptime >= 5 seconds.
- `test_compose_logs_have_no_critical_crash_signatures()` — verifies logs don't contain crash indicators (traceback, segmentation fault, panic).
- `test_compose_logs_quantitative_startup_signals()` — verifies logs contain:
  - >= 80 lines.
  - >= 3 ZooKeeper startup signals ("Starting quorum peer").
  - >= 1 LiveKit startup signal ("starting LiveKit server").

#### `test_e2e_binpack.py`
Core bin-packing behavior validation with real LiveKit rooms and agents.

**Configuration:**
- Both agents configured with `room_target_n=3` and `overflow_margin=1`.
- Each agent accepts up to 4 rooms (3 target + 1 overflow).

**Tests:**

1. **`test_e2e_livekit_api_readiness()`** — sanity check that LiveKit API is accessible.

2. **`test_e2e_binpack_agent1_fills_first()`** — verifies agent1 packs rooms before spillover.
   - **Scenario:** Create 3 rooms.
   - **Expected:** All 3 rooms placed on agent1 (room_target_n=3).
   - **Validates:** Winner selection (agent1 has lowest free_slots >= 0).

3. **`test_e2e_binpack_agent2_receives_overflow()`** — verifies spillover to agent2 when agent1 is full.
   - **Scenario:** Create 6 rooms sequentially with 0.5s pauses.
   - **Expected:** 
     - Rooms 1-3 → agent1 (full at 3/3).
     - Rooms 4-6 → agent2 (now winner with free slots).
   - **Validates:** Load balancing once winner pod changes.

4. **`test_e2e_binpack_room_termination_repacks()`** — verifies rooms repacked on freed agent.
   - **Scenario:**
     1. Create 6 rooms (3 on each agent).
     2. Delete room from agent1 (frees 1 slot).
     3. Create 1 new room.
   - **Expected:** New room goes to agent1 (now winner with free slots).
   - **Validates:** Dynamic repacking as occupancy changes.

5. **`test_e2e_binpack_overflow_guard_enforced()`** — verifies overflow safety bounds.
   - **Scenario:** Create 9 rooms (exceeds 2 agents × 3 target).
   - **Expected:** No crashes; rooms distributed with occupancy <= 4 per agent.
   - **Validates:** Hard overflow guard prevents unbounded admission.

6. **`test_e2e_binpack_sequential_creation_trend()`** — verifies bin-pack trend over time.
   - **Scenario:** Create 6 rooms with 1s pauses between each.
   - **Expected:** Predictable packing trend (agent1 fills first).
   - **Validates:** Load function convergence and winner stability.

### Running E2E tests

#### All together
```bash
make test-e2e
```

#### Just proof gate (artifact validation)
```bash
make proof-gate
```

#### Stack setup and tests
```bash
scripts/run_e2e.sh
```

### KEDA kind harness

The KEDA path uses a real kind cluster, installs KEDA, deploys `livekit-server`, and runs a lightweight long-running agent Deployment so replica scaling can be exercised without depending on application-specific agent logic.

#### Run the KEDA harness
```bash
scripts/run_keda_e2e.sh
```

#### What it validates

- KEDA operator installation succeeds in kind.
- `ScaledObject` and RBAC templates render and apply.
- LiveKit server and the agent simulator Deployment become healthy.
- Replica count can move from 2 -> 3 -> 2 while policy conditions are asserted in code.

#### Prerequisites

- Docker
- kind
- kubectl
- envsubst

#### Manual stack management
```bash
# Start compose stack
docker compose -f livekit-lkscaler/e2e/compose.yaml up -d

# Run tests
cd livekit-lkscaler
E2E_STACK_RUNNING=1 pytest e2e/tests/test_e2e_*.py -v

# Inspect logs/status
docker compose -f e2e/compose.yaml ps
docker compose -f e2e/compose.yaml logs livekit

# Clean up
docker compose -f e2e/compose.yaml down
```

### Notes

- E2E tests requiring a running stack are gated by `E2E_STACK_RUNNING`.
- KEDA kind tests are gated by `KEDA_E2E_RUNNING` and are launched by `scripts/run_keda_e2e.sh`.
- Compose diagnostics are written to `e2e/artifacts/` on failures.
- kind/KEDA diagnostics are also written to `e2e/artifacts/` on failures.
- Coverage gate is enforced on unit+integration tests with `COVERAGE_MIN` (default `90`).
- Bin-pack tests use 0.5-1.0s pauses between room creation to allow time for load_fnc evaluation and winner/loser decisions to stabilize.
