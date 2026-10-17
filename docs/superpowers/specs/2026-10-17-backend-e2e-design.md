# Backend E2E Design Specification

**Date:** 2026-10-17
**Status:** Approved for implementation
**Scope:** Cross-process E2E coverage for the coordination backends (`lkscaler-core` ZooKeeper and Redis).

## 1. Goal

Prove, against real infrastructure, that two workers sharing a backend coordinate the way
the placement logic assumes: one fills toward its target before spillover, the overflow
bound holds, claims are released, and a worker that dies stops occupying cluster
capacity. Unit tests cannot show this, because they run both workers inside one process
with a fake client.

## 2. What this proves, and what it does not

The E2E agents are long-running simulators, not LiveKit SDK workers: they expose the same
`on_request`/`load_fnc` behaviour through a small control API instead of a real dispatch
window. So these tests prove **coordination across processes against a real backend**.
They do not prove LiveKit's dispatch path end to end; that remains a Milestone 9 item and
must not be claimed from a green run of this suite.

## 3. Topology

Existing compose stack: `zk1`, `zk2`, `zk3`, `livekit`, `agent1`, `agent2`.

Add:

- `redis` — `redis:7`, healthchecked with `redis-cli ping`, host port 16379 so a local
  Redis is untouched.

Both backends stay running; the agents select one through `LKSCALER_BACKEND`
(`zookeeper` | `redis`). The suite runs once per backend, tearing the stack down in
between with `down -v`, so a run never inherits the previous backend's keys or znodes.

## 4. Agent control API

The simulator (`e2e/fixtures/test_agent.py`) grows a HTTP surface on `:8090`, keeping the
existing heartbeat logging so current readiness checks keep working:

| Endpoint | Behaviour |
| --- | --- |
| `GET /health` | `{"ok": true, "backend": "...", "pod_id": "..."}` |
| `GET /load` | the `load_fnc` value for this worker right now (`0.0` winner, `1.0` otherwise) |
| `GET /occupancy` | `active_rooms`, `reservations`, `free_slots` for this worker |
| `POST /request` | body `{"job_id": "..."}` → runs the admission path (`reserve_for_admission` through the configured store) and returns `{"accepted": bool, "reason": "..."}` |
| `POST /complete` | body `{"job_id": "..."}` → marks the job as assigned: converts the reservation into `active_rooms` |
| `POST /release` | body `{"job_id": "..."}` → drops the reservation without assigning it |
| `POST /reset` | clears local counters, for test isolation |

The worker publishes its pod state to the backend every `sync_interval_ms` and on every
state change, so peers and the autoscaler see fresh numbers.

Configuration (all via env): `LKSCALER_BACKEND`, `LKSCALER_NAMESPACE`, `LKSCALER_POD_ID`,
`LKSCALER_ZK_HOSTS`, `LKSCALER_REDIS_URL`, `LKSCALER_ROOM_TARGET_N`,
`LKSCALER_OVERFLOW_MARGIN`, `LKSCALER_RESERVATION_TTL_SEC`.

## 5. Assertions per backend

1. **Fill before spillover.** With two workers at `room_target_n = 2`, create jobs through
   `agent1` until it holds its target; while it is below target, `agent1`'s `/load` is
   `0.0` and `agent2`'s is `1.0`. This is the bin-pack trend: the same worker keeps
   winning until it fills.
2. **Overflow bound.** Keep sending to `agent1` until it holds `room_target_n +
   overflow_margin`; the next request is rejected with `reason="overflow_guard"`. Its
   occupancy never exceeds the bound.
3. **Cross-worker visibility.** After `agent1` fills, `agent2` observes `agent1`'s
   occupancy through the backend and, once `agent1` is at its hard bound, becomes the
   winner (`0.0`).
4. **Claim release.** A `/request` followed by `/release` frees the slot: `/occupancy`
   drops the reservation and the next request is accepted again. A request that is never
   completed or released disappears on its own once `LKSCALER_RESERVATION_TTL_SEC`
   passes.
5. **Failure reclaims capacity.** Stop `agent2` and assert its pod state leaves the
   cluster view — the ZooKeeper session closing drops its ephemeral nodes, and Redis
   drops its keys at TTL. Then `agent1`'s `/load` reaction and a fresh request confirm the
   cluster recomputed without the dead worker.

## 6. Runner and gates

- `scripts/run_e2e_backends.sh` runs the stack once per backend and executes the suite,
  capturing artifacts per backend under `e2e/artifacts/backends/<backend>/`.
- `make test-e2e-backends` wraps it; CI gains one explicit step for it, after the existing
  E2E steps.
- Assertions read only state that comes from the backend or from endpoint responses, never
  from container logs, and no test may sleep waiting for a state change: each waits on an
  observed value with a bounded timeout.

## 7. Risks

- **Simulator drift.** The control API mirrors the placement path rather than running it,
  so it can drift from `build_on_request_handler`. Mitigation: the simulator calls the
  real `reserve_for_admission` and `build_load_fnc` with a real backend store; it does not
  reimplement them.
- **Timing.** Ephemeral/TTL reclamation is time-based; the wait is bounded and asserted on
  the *observed* cluster view, with the backend's own TTL and session timeouts chosen small
  enough for the suite and documented in the compose file.
