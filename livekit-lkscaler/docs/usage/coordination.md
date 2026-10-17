# Coordination backends

Placement needs two things beyond a single worker: a shared answer to *who holds a
slot*, and a shared view of *how much room every worker has left*. LKScaler keeps both
behind small contracts in `lkscaler_core` so the placement math never learns which
backend you run.

## Contracts

| Contract | Methods | Purpose |
| --- | --- | --- |
| `ReservationStore` | `create`, `delete`, `get` | Claim a slot before accepting a job. `create` returns `False` when the reservation already exists, so the losing worker backs off. |
| `ExpiringReservationStore` | the above plus `remove_expired(now=...)` | Drop reservations whose TTL has passed. |
| `ClusterStateStore` | `publish_pod_state`, `read_pod_states`, `free_slots_by_pod` | Publish this worker's occupancy and read the cluster's. |

`create` must be atomic: two workers racing for the same `(pod_id, job_id)` must not both
win. Every backend below gets that from its own primitive — a ZooKeeper znode create, a
Redis `SET NX`, a Kubernetes API object create.

## Backends

| Backend | Status | Install | Shared state lives in |
| --- | --- | --- | --- |
| `InMemoryReservationStore` | ships today, **single process only** | base package | process memory (tests, one worker) |
| ZooKeeper | implemented, integration-tested against a real ensemble | `pip install "lkscaler-core[zookeeper]"` | znodes under `/livekit-binpack/{namespace}` |
| Redis | planned | `pip install "lkscaler-core[redis]"` (extra declared, implementation pending) | keys and hashes per namespace |
| Kubernetes / KEDA-native | design pending | — | Kubernetes API, no external store |

The in-memory store exists for tests and single-worker experiments. It coordinates
nothing across processes, so two workers using it can both believe they own the same
slot. Use a real backend for a real fleet.

## ZooKeeper

```bash
pip install "lkscaler-core[zookeeper]"
```

```python
from lkscaler_core.zookeeper import KazooNodeClient, ZooKeeperStateStore

client = KazooNodeClient(hosts=["zk-0.zk:2181", "zk-1.zk:2181", "zk-2.zk:2181"], session_timeout_sec=10)
client.start()
store = ZooKeeperStateStore(namespace="livekit-lkscaler", client=client)
```

`store` satisfies `ReservationStore`, `ExpiringReservationStore`, and `ClusterStateStore`,
so it can be handed straight to `build_on_request_handler` and `build_load_fnc`:

```python
from lkscaler_livekit import build_load_fnc, build_on_request_handler

on_request = build_on_request_handler(config=config, store=store, tracker=tracker)
load_fnc = build_load_fnc(config=config, store=store, tracker=tracker)
```

Node layout, from the design spec:

- `/livekit-binpack/{namespace}/pods/{pod_id}` — this worker's occupancy
  (`free_slots`, `active_rooms`, `reservations`, `updated_at`), ephemeral to the session.
- `/livekit-binpack/{namespace}/rooms/{room_id}` — a live room
  (`pod_id`, `job_id`, `started_at`), ephemeral to the session.
- `/livekit-binpack/{namespace}/reservations/{pod_id}/{job_id}` — a claim
  (`created_at`, `expires_at`), ephemeral to the session.

Operational notes:

- Reservations are ephemeral, so a worker that dies releases its claims immediately; the
  `expires_at` field covers a worker that stays alive without completing an accept.
- TTL cleanup is parent-managed, not a ZooKeeper TTL node: call
  `store.remove_expired(now=...)` on an interval.
- Republishing a pod state updates the existing node, so a tracker can call
  `publish_pod_state` every `sync_interval_ms` without growing the tree.
- Namespaces are isolated, so one ensemble can host several pools: give each pool its own
  `namespace` and only that pool's workers read it.

## Testing a backend locally

```bash
make test-integration-zookeeper
```

This starts a single-node ZooKeeper on port 22181 (not 2181, so a local ensemble is left
alone), runs the integration tests against it, and removes the container afterwards. The
same tests skip cleanly when `LKSCALER_ZK_HOSTS` is unset, which keeps the default
`make test-integration` hermetic.
