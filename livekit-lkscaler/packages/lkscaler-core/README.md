# lkscaler-core

Placement and reservation primitives that make a self-hosted LiveKit Agents fleet cheaper to run: jobs are bin-packed onto workers that fill toward a room target before spillover, so the workers left idle can be scaled down sooner instead of being paid for.

The package is SDK-agnostic. It contains no LiveKit dependency, no network I/O, and no process-global state. It is the placement math and reservation lifecycle that the [`livekit-lkscaler`](https://pypi.org/project/livekit-lkscaler/) adapter wires into a LiveKit worker, and it needs no autoscaler and no coordination service of its own: scaling is driven by the load signal it computes, and shared state is whatever `ReservationStore` you supply.

Requires Python 3.12+.

## Install

```bash
pip install lkscaler-core
```

Most users do not install this directly: `livekit-lkscaler` depends on it.

## Concepts

### Slots

Worker load is counted in slots:

```python
from lkscaler_core import PodOccupancy

occupancy = PodOccupancy(active_rooms=2, reservations=1)
assert occupancy.occupied_slots() == 3
assert occupancy.free_slots(room_target_n=4) == 1
```

`room_target_n` is how many concurrent rooms a worker should fill before spillover. `overflow_margin` is a small buffer that absorbs race windows between workers, so a worker's hard bound is `room_target_n + overflow_margin`.

### Reservations

`reserve_for_admission` claims a slot *before* the job is accepted, which is what stops two workers from accepting work into the same last free slot:

- it rejects when `occupied_slots() >= room_target_n + overflow_margin` with `reason="overflow_guard"`,
- it rejects when the store already holds that `(pod_id, job_id)` pair with `reason="reservation_create_failed"`,
- otherwise it stores a reservation bounded by `reservation_ttl_sec` and reports `reason="reserved"`.

`cleanup_unassigned_reservation` removes a reservation when the accept path does not lead to an assignment, and stores drop reservations whose TTL has elapsed.

### Load signal

LiveKit asks each worker for a load value; exactly one worker is the winner — the one holding the fewest free slots above zero, with the worker id breaking ties so every worker reading the same view agrees:

```python
from lkscaler_core import choose_load_signal, pick_winner_pod

cluster_free_slots = {"worker-a": 2, "worker-b": 1, "worker-c": 0}
assert pick_winner_pod(cluster_free_slots) == "worker-b"
assert choose_load_signal(local_pod_id="worker-b", free_slots_by_pod=cluster_free_slots) == 0.0
assert choose_load_signal(local_pod_id="worker-a", free_slots_by_pod=cluster_free_slots) == 1.0
```

A worker with no free slots, a worker missing from the cluster view, or a cluster with no free slots at all reports `1.0`.

### Coordination paths

`ZkPaths` renders the shared data model used to publish occupancy and reservations:

```python
from lkscaler_core import ZkPaths

paths = ZkPaths(namespace="livekit-lkscaler")
assert paths.pod_node("worker-a") == "/livekit-binpack/livekit-lkscaler/pods/worker-a"
assert paths.room_node("room-1") == "/livekit-binpack/livekit-lkscaler/rooms/room-1"
assert (
    paths.reservation_node("worker-a", "job-1")
    == "/livekit-binpack/livekit-lkscaler/reservations/worker-a/job-1"
)
```

Namespaces, pod ids, room ids, and job ids must be non-empty and must not contain `/`.

## Quickstart

```python
from datetime import UTC, datetime, timedelta

from lkscaler_core import BinpackConfig, InMemoryReservationStore, PodOccupancy, reserve_for_admission

config = BinpackConfig(
    namespace="livekit-lkscaler",
    pod_id="worker-a",
    room_target_n=2,
    overflow_margin=1,
    reservation_ttl_sec=30,
    zk_session_timeout_sec=10,
    sync_interval_ms=250,
)

store = InMemoryReservationStore()
now = datetime.now(UTC)

decision = reserve_for_admission(
    store=store,
    occupancy=PodOccupancy(active_rooms=1, reservations=0),
    pod_id=config.pod_id,
    job_id="job-1",
    room_target_n=config.room_target_n,
    overflow_margin=config.overflow_margin,
    reservation_ttl_sec=config.reservation_ttl_sec,
    now=now,
)
assert decision.accepted
assert decision.reason == "reserved"

# A second reservation for the same job is refused by the store.
duplicate = store.create_with_ttl(pod_id="worker-a", job_id="job-1", ttl_sec=30, now=now)
assert duplicate is False

# Reservations expire: cleanup is explicit.
assert store.remove_expired(now=now + timedelta(seconds=31)) == 1
assert store.get(pod_id="worker-a", job_id="job-1") is None
```

Cluster summaries for autoscaling decisions:

```python
from lkscaler_core.snapshot import PodSnapshot, summarize_cluster_snapshot

summary = summarize_cluster_snapshot(
    pods=[
        PodSnapshot(pod_id="worker-a", active_rooms=2, reservations=1, room_target_n=4),
        PodSnapshot(pod_id="worker-b", active_rooms=0, reservations=0, room_target_n=4),
    ],
    snapshot_at=1_700_000_000,
    observed_at=1_700_000_030,
)
assert summary.cluster_free_slots == 5
assert summary.idle_pod_count == 1
assert summary.smallest_idle_pod_free_slots == 4
assert summary.snapshot_age_sec == 30
```

## API

| Symbol | Purpose |
| --- | --- |
| `BinpackConfig` | Placement configuration: namespace, pod id, target, margin, reservation TTL, coordination hints. |
| `PodOccupancy` | Slot arithmetic: `occupied_slots()`, `free_slots(room_target_n=...)`. |
| `ReservationRecord`, `RoomRecord` | Reservation and room state records. |
| `ReservationStore` | Store interface: `create`, `delete`, `get`. |
| `InMemoryReservationStore` | Single-process store, plus `remove_expired(now=...)` and `create_with_ttl(...)`. |
| `reserve_for_admission`, `cleanup_unassigned_reservation`, `AdmissionResult` | Reservation-first admission decision and cleanup. |
| `pick_winner_pod`, `choose_load_signal` | Unique winner selection and the `0.0` / `1.0` load value. |
| `min_positive_free_slots` | Smallest free-slot count above zero, for summaries. |
| `ZkPaths` | Path helper for the shared coordination data model. |
| `ClusterSnapshot`, `ClusterSnapshotCache` | Lock-protected view of free slots per worker. |
| `lkscaler_core.snapshot.summarize_cluster_snapshot`, `PodSnapshot`, `ClusterSnapshotSummary` | Cluster totals, idle-worker count, smallest idle-worker free slots, snapshot age. |

## Coordination backends

`InMemoryReservationStore` coordinates nothing across processes; it exists for single-worker use and tests. For a real fleet, use a shared backend:

```bash
pip install "lkscaler-core[zookeeper]"
```

```python
from lkscaler_core.zookeeper import KazooNodeClient, ZooKeeperStateStore

client = KazooNodeClient(hosts=["zk-0.zk:2181", "zk-1.zk:2181"], session_timeout_sec=10)
store = ZooKeeperStateStore(namespace="livekit-lkscaler", client=client)
```

Constructing either one opens nothing: `client.start()` opens the session before first use, and
`client.close()` releases it — which is what drops this worker's ephemeral nodes when it shuts down.

`ZooKeeperStateStore` and `RedisStateStore` satisfy the reservation, expiry, and cluster-state contracts, so either drops straight into `build_on_request_handler` and `build_load_fnc`. See [Coordination backends](https://github.com/computo-experto/livekit-lkscaler/blob/main/livekit-lkscaler/docs/usage/coordination.md) for key layouts, cleanup, and backend trade-offs.

Any other store works too, as long as it keeps the contract:

- `create(reservation) -> bool` must be atomic and return `False` when the reservation already exists, so the losing worker backs off,
- `delete(*, pod_id, job_id)` must be idempotent,
- `get(*, pod_id, job_id)` returns `None` when there is no reservation.

`ClusterStateStore` is the other half: `publish_pod_state` and `free_slots_by_pod`, which is exactly what [`livekit-lkscaler`](https://pypi.org/project/livekit-lkscaler/) reads.

## What this package does not do

- It assumes no autoscaler: the load signal it computes is what a replica manager (Kubernetes HPA, KEDA, or LiveKit's own scaling) reacts to.
- `BinpackConfig.zk_session_timeout_sec`, `BinpackConfig.sync_interval_ms`, and `BinpackConfig.fail_mode` are declarations for your coordination layer; the placement helpers do not read them.
- The base install has no network dependency at all: kazoo arrives only with the `zookeeper` extra and redis-py only with the `redis` extra. No background threads beyond the store and cache locks, no LiveKit dependency.

## Links

- KEDA external scaler: [`lkscaler-keda`](https://pypi.org/project/lkscaler-keda/) (same repository)
- License: Apache-2.0 (`LICENSE` ships with every release)
- Source, design specs, and usage guides: <https://github.com/computo-experto/livekit-lkscaler>
- Changelog: <https://github.com/computo-experto/livekit-lkscaler/blob/main/livekit-lkscaler/CHANGELOG.md>
