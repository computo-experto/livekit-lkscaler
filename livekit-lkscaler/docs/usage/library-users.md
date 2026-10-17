# Library User Guide

This guide is for teams embedding `livekit-lkscaler` into an existing LiveKit Agent worker.
It focuses on what you need to run the library in production: prerequisites, integration, and configuration.

## Prerequisites

Before integrating the library, make sure you have:

- A working LiveKit Agent worker application.
- A shared store for reservations and cluster occupancy, so workers can see each other's slots. ZooKeeper is available as an optional extra (`pip install "lkscaler-core[zookeeper]"`); Redis and a Kubernetes-native backend are in progress. The base install carries an in-memory store only, which is single-process and therefore not enough for a multi-worker fleet.
- A unique `pod_id` for each worker instance.
- A cluster namespace shared by the workers that should participate in the same scaling pool.

No autoscaler is required: the placement path only needs the two hooks below, and the `load_fnc` value is what a replica manager reacts to.

Shared reservation and cluster-state coordination run through the store you provide. If that store is unavailable, the library itself applies no fallback; your tracker decides what a worker should report and accept.

## Install

Install the package in your worker environment:

```bash
pip install livekit-lkscaler
```

## Integrate With Your LiveKit Agent Code

The library exposes two hooks:

- `build_on_request_handler(...)` for admission decisions.
- `build_load_fnc(...)` for worker load signaling.

Both hooks need the same three inputs:

- `BinpackConfig`
- a reservation store
- a tracker object that reports local occupancy and cluster free slots

Example:

```python
from lkscaler_core import BinpackConfig, InMemoryReservationStore, PodOccupancy
from lkscaler_livekit import build_load_fnc, build_on_request_handler


class Tracker:
    def get_local_occupancy(self) -> PodOccupancy:
        return PodOccupancy(active_rooms=0, reservations=0)

    def get_cluster_free_slots(self) -> dict[str, int]:
        return {"worker-a": 2, "worker-b": 1}


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
```

Wire `on_request` and `load_fnc` into your LiveKit worker entrypoint using the callback fields provided by your LiveKit Agent SDK version.

## Configure The Library

The key settings are:

- `namespace`: shared logical scope for the worker group.
- `pod_id`: unique identifier for the current worker.
- `room_target_n`: expected safe room concurrency per worker.
- `overflow_margin`: small buffer for race windows during admission.
- `reservation_ttl_sec`: how long reservations remain valid.
- `zk_session_timeout_sec`: session timeout for the coordination layer you implement.
- `sync_interval_ms`: how often you refresh cluster state.
- `fail_mode`: fallback admission behavior when cluster coordination is not available.

Recommended starting values:

```python
BinpackConfig(
    namespace="livekit-lkscaler",
    pod_id="worker-1",
    room_target_n=2,
    overflow_margin=1,
    reservation_ttl_sec=30,
    zk_session_timeout_sec=10,
    sync_interval_ms=250,
)
```

For field-by-field details, see [Configuration](configuration.md).

## What To Expect At Runtime

- `on_request` creates a reservation before the worker accepts the job.
- If a reservation cannot be created, the request is rejected.
- If acceptance fails after reservation creation, the reservation is cleaned up.
- `load_fnc` reports `0.0` for the single winning worker and `1.0` for every other worker.

For operational behavior and failure handling, see [Operations](operations.md).