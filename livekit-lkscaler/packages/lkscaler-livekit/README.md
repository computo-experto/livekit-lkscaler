# livekit-lkscaler

LiveKit agent worker hooks that make a self-hosted Agent fleet cheaper to run: jobs are bin-packed so workers fill toward a room target before spillover, which leaves the remaining workers genuinely idle so the cluster can scale down sooner. Slot reservations keep two workers from accepting the same job into the same last free slot.

The package adapts [`lkscaler-core`](https://pypi.org/project/lkscaler-core/) to the two callbacks a LiveKit agent worker needs, and adds no placement logic of its own. It does not require KEDA: the `load_fnc` value it produces is what any replica manager — Kubernetes HPA, KEDA, or LiveKit's own scaling — reacts to, and the KEDA external scaler in `lkscaler-keda` is an optional extra for clusters that run KEDA.

Reservations and cluster occupancy come from whatever backend you supply: an in-memory store ships for tests and single-worker use, and a ZooKeeper backend is available through `lkscaler-core[zookeeper]`. See [Coordination backends](https://github.com/computo-experto/livekit-lkscaler/blob/main/livekit-lkscaler/docs/usage/coordination.md).

Requires Python 3.12+ and `livekit-agents>=1.6.2` (installed as a dependency).

## Install

```bash
pip install livekit-lkscaler
```

## What it gives you

| Builder | Wired into | Behavior |
| --- | --- | --- |
| `build_on_request_handler(config, store, tracker)` | your worker's job-request callback | Applies the overflow guard, creates a reservation, then accepts. Rejects the job when the guard trips or the reservation cannot be created. Removes the reservation if accepting raises. |
| `build_load_fnc(config, store, tracker)` | your worker's load callback | Returns `0.0` for the worker that should win the next job (smallest positive free slots in the cluster) and `1.0` otherwise. |

Both builders take the same three inputs: a `BinpackConfig`, a `ReservationStore`, and a tracker object that reports this worker's occupancy and the cluster's free-slot map.

## Quickstart

```python
import asyncio

from lkscaler_core import BinpackConfig, InMemoryReservationStore, PodOccupancy
from lkscaler_livekit import build_load_fnc, build_on_request_handler


class Tracker:
    """Your worker's view of local occupancy and cluster free slots."""

    def get_local_occupancy(self) -> PodOccupancy:
        return PodOccupancy(active_rooms=0, reservations=0)

    def get_cluster_free_slots(self) -> dict[str, int]:
        return {"worker-a": 2, "worker-b": 0}


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
tracker = Tracker()

on_request = build_on_request_handler(config=config, store=store, tracker=tracker)
load_fnc = build_load_fnc(config=config, store=store, tracker=tracker)


class JobRequest:
    """Stand-in for the SDK job request object."""

    def __init__(self, job_id: str) -> None:
        self.id = job_id
        self.accepted = False

    async def accept(self, **kwargs: object) -> None:
        self.accepted = True

    async def reject(self, **kwargs: object) -> None:
        self.accepted = False


job = JobRequest("job-1")
asyncio.run(on_request(job))
assert job.accepted
assert load_fnc() == 0.0
```

## Wiring into a worker

Pass the two callbacks wherever your LiveKit Agents SDK version accepts a job-request handler and a load callback. The hooks are duck-typed: this package's code never imports the SDK, so it works with any SDK version that calls an `async` request handler object exposing `id`, `accept(**kwargs)`, and `reject(**kwargs)`, and a load callback that returns a float.

The `tracker` is the part you own. It has to answer two questions:

- `get_local_occupancy() -> PodOccupancy`: rooms and reservations currently on this worker.
- `get_cluster_free_slots() -> dict[str, int]`: free slots for every worker in the same `namespace`, including this one.

## Configuration

`BinpackConfig` fields, with the values most deployments start from:

| Field | Meaning | Example |
| --- | --- | --- |
| `namespace` | Shared logical scope of the worker pool. | `"livekit-lkscaler"` |
| `pod_id` | Unique id of this worker. | `"worker-a"` |
| `room_target_n` | Concurrent rooms a worker fills before spillover. | `2` |
| `overflow_margin` | Buffer above the target that absorbs race windows. | `1` |
| `reservation_ttl_sec` | How long a reservation stays valid. | `30` |
| `zk_session_timeout_sec` | Session timeout for your coordination layer. | `10` |
| `sync_interval_ms` | How often you refresh cluster state. | `250` |
| `fail_mode` | Intended behavior when coordination is unavailable. | `"accept_if_local_below_n"` |

`zk_session_timeout_sec`, `sync_interval_ms`, and `fail_mode` describe the coordination layer you implement; the shipped hooks do not read them.

## Behavior contract

- The overflow guard trips at `occupied_slots() >= room_target_n + overflow_margin`, so a worker never exceeds its target plus the margin.
- A reservation is created before the job is accepted. If it cannot be created, the request is rejected without accepting.
- If accepting raises, the reservation is removed before the exception propagates.
- Reservations expire after `reservation_ttl_sec` and are removed on demand by the store.
- `load_fnc` returns `0.0` for every worker whose free-slot count equals the smallest positive count in the cluster, so ties share the win; workers with no free slots, and clusters with no free slots at all, report `1.0`.

## Operational notes

- `InMemoryReservationStore` does not coordinate across processes. Deploying more than one worker requires a `ReservationStore` implementation backed by a shared service, otherwise two workers can reserve the same slot.
- Rejections are normal under load: they mean another worker owns the slot, or this worker is at its bound.
- Keep `reservation_ttl_sec` comfortably above your worst accept latency so a reservation is not dropped while a job is still being accepted.
- If jobs pile onto one worker, check that `get_cluster_free_slots()` includes all workers in the namespace and that their values are fresh.

## Links

- Placement primitives and coordination contract: [`lkscaler-core`](https://pypi.org/project/lkscaler-core/)
- KEDA autoscaling companion: `lkscaler-keda` (same repository)
- Source, design specs, and usage guides: <https://github.com/computo-experto/livekit-lkscaler>
- Changelog: <https://github.com/computo-experto/livekit-lkscaler/blob/main/livekit-lkscaler/CHANGELOG.md>
