# LiveKit Bin-Pack Scaler (Python) - Design Specification

**Date:** 2026-06-19
**Status:** Approved for planning
**Scope:** Python library for self-hosted LiveKit Agents that provides bin-pack-oriented custom `on_request` and `load_fnc` behavior using self-hosted ZooKeeper (`kazoo`).

## 1. Goal

Build a reusable Python library that LiveKit agent users can include to improve room placement with a bin-pack strategy for homogeneous pods.

Design target:

- Pack up to `N` rooms per pod before opening capacity on less-loaded pods.
- Use room-count capacity, not CPU utilization.
- Keep per-room observability in ZooKeeper.
- Minimize dispatch latency by avoiding avoidable reassignments.

## 2. Non-goals (v1)

- Heterogeneous capacity weighting.
- Cross-region placement policy.

## 3. Assumptions

- Agent pods are homogeneous.
- Users configure library with Python objects (Pydantic models).
- ZooKeeper is self-hosted and available via `kazoo`.
- LiveKit Agents are self-hosted (not LiveKit Cloud hosted agents).
- LiveKit dispatch respects worker-reported load/availability and calls `on_request` for selected workers.
- `pod_id` is unique per worker instance (recommended: hostname + short UUID suffix).

## 4. Public library surface

### 4.1 Configuration

`BinpackConfig` (Pydantic):

- `namespace: str`
- `pod_id: str`
- `room_target_n: int`
- `overflow_margin: int = 1`
- `reservation_ttl_sec: int`
- `zk_session_timeout_sec: int`
- `sync_interval_ms: int`
- `fail_mode: Literal["accept_if_local_below_n"]` (v1 default/only behavior)

### 4.2 Factory APIs

- `build_on_request_handler(config, store, tracker) -> Callable`
- `build_load_fnc(config, store, tracker) -> Callable`

These are drop-in custom hooks for LiveKit Python Agent SDK `on_request` and `load_fnc`.

For compatibility, the library may also expose legacy aliases (`build_request_func`, `build_load_func`) that call the new APIs.

### 4.3 Core components

- `ZooKeeperStateStore` (kazoo-backed)
- `RoomLifecycleTracker`
- `ClusterSnapshotCache` (watch + periodic resync)

## 5. ZooKeeper data model

Base path: `/livekit-binpack/{namespace}`

- Pod ephemeral node (parent process session): `/pods/{pod_id}`
  - data includes:
    - `free_slots`
    - `active_rooms`
    - `reservations`
    - `updated_at`
- Room ephemeral nodes (created by job process session, separate subtree):
  - `/rooms/{room_id}`
  - data includes at least `pod_id`, `job_id`, `started_at`
- Reservation nodes (parent process, separate subtree):
  - `/reservations/{pod_id}/{job_id}`
  - ephemeral nodes owned by the parent process ZooKeeper session
  - parent-managed timeout cleanup (not ZooKeeper TTL nodes)
  - data includes at least `created_at`, `expires_at`

## 6. Bin-pack behavior

### 6.1 Placement signal logic (`load_fnc`)

Each pod evaluates the cluster snapshot to decide whether to advertise availability.

1. Compute local `free_slots = N - active_rooms - reservations`.
2. Read peers' `free_slots` from cached ZooKeeper snapshot.
3. The winner is the single pod with the fewest free slots above zero, pod id breaking
   ties so every worker reading the same view picks the same pod.
4. Report `0.0` for that pod and `1.0` for every other pod.
5. Otherwise report `1.0` (busy), even if local pod has spare capacity.

This intentionally reports busy for non-winning pods so LiveKit tends to dispatch to the fullest eligible pod(s), promoting bin-packing.

Notes:

- Any winner value below the server `load_threshold` is valid; v1 standardizes winner to `0.0`.
- Loser `1.0` guarantees it is considered full under normal thresholds.
- For current self-hosted LiveKit Python defaults, production `load_threshold` is `0.7` and development mode disables load shedding (`inf`).

### 6.2 Admission logic (`on_request`)

- Fast-path accept, but only after reservation is persisted.
- Evaluate hard overflow guard first:
  - reject if `active_rooms + reservations >= N + overflow_margin`.
- Create reservation node for `job_id` with `expires_at = now + reservation_ttl_sec`.
- Call `job_req.accept(...)` only after reservation creation succeeds.
- Reject if reservation creation fails.
- If accept does not lead to assignment/job start (timeout, cancellation, or error), remove the reservation immediately.

Rationale: if pod was advertised available, request should usually be accepted to avoid costly reassignment.

### 6.3 Parent/child responsibility boundary

- Parent process:
  - creates reservation on accept.
  - reports reservation count as occupied slots in `/pods/{pod_id}` data.
  - removes expired reservations when child room node is not observed before `reservation_ttl_sec`.
- Job process handling room:
  - creates room ephemeral node under `/rooms/{room_id}` when session starts.
- Parent process reconciliation:
  - consumes/removes reservation once the corresponding room node is established.
  - removes reservation immediately if assignment fails before room start.

This is required because real room liveness belongs to the job process, while dispatch admission occurs in the parent process.

## 7. Failure handling

- **ZooKeeper unavailable/disconnected:** fallback to local rule:
  - accept only if local `active_rooms + reservations < N`;
  - otherwise reject.
- **Snapshot staleness/races:** bounded by overflow guard (`N + overflow_margin`).
- **Parent crash after reservation:** reservation nodes are ephemeral for the parent session and are removed by ZooKeeper on session expiration; startup hygiene reconciliation is not required.
- **Job process crash:** room ephemeral node removed on session end.

## 8. Data flow

1. Pod startup registers ephemeral pod node.
2. Snapshot cache starts (watch + periodic resync).
3. `load_fnc` exposes only locally winning pod(s) (least free slots above zero).
4. `on_request` creates reservation, then accepts.
5. Job process starts, creates room node under `/rooms/{room_id}`.
6. Parent reconciles reservation-to-room transition and clears reservation.
7. Room ends, room node removed; counts/free slots converge.

## 9. Testing strategy

### 9.1 Unit tests

- Winning/non-winning `load_fnc` decisions from synthetic cluster states.
- Busy-reporting (`1.0`) for non-winning pods.
- Overflow guard behavior.
- Reservation creation before accept behavior.
- Reservation removal when accept does not result in assignment/job start.
- Parent timeout cleanup when room node never appears.
- Fallback behavior when ZooKeeper is unavailable.

### 9.2 Integration tests

- Multi-pod simulation with kazoo test server.
- Verify packing trend: one pod fills near `N` before spreading (except ties/races).
- Reservation-to-room transition correctness.
- Assignment failure path removes reservation promptly.
- Separate-subtree reconciliation (`/reservations/...` with `/rooms/...`).
- Crash/disconnect recovery convergence.

## 10. Acceptance criteria

- Python library provides working hooks for `on_request` and `load_fnc`.
- Room nodes are created by the job process under `/rooms/*` and visible in ZooKeeper.
- Bin-pack behavior is observable from dispatch outcomes under homogeneous pods.
- Per-pod occupancy never exceeds `N + overflow_margin`.
- Reservation timeout cleanup is parent-managed and bounded/safe.
- ZooKeeper outage fallback uses local capacity rule and remains bounded/safe.

## 11. Deployment constraints (v1)

- Supported target is self-hosted LiveKit Agents workers.
- ZooKeeper is assumed self-hosted and reachable by all worker pods.
- This design does not target LiveKit Cloud hosted agents where custom load handling may be restricted.

## 12. Future extension points (post-v1)

- Weighted capacity for heterogeneous pods.
- Strategy plugins beyond strict bin-pack.
