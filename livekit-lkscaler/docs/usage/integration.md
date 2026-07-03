# Integration Guide

This guide shows how to integrate LKScaler hooks into a LiveKit worker.

If you are embedding the library into application code, the [Library User Guide](library-users.md) is the best starting point.

## Hook construction

Use `build_on_request_handler` and `build_load_fnc` from `livekit-lkscaler`:

```python
from lkscaler_core import BinpackConfig, InMemoryReservationStore
from lkscaler_livekit import build_load_fnc, build_on_request_handler

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
tracker = ...  # your tracker implementation

on_request = build_on_request_handler(config=config, store=store, tracker=tracker)
load_fnc = build_load_fnc(config=config, store=store, tracker=tracker)
```

## Behavioral contract

- `load_fnc` returns `0.0` for current winner and `1.0` for non-winners.
- `on_request` creates reservation before accept.
- If accept fails, reservation is cleaned up.
- Overflow admission is bounded by `room_target_n + overflow_margin`.

## KEDA integration surface

The repository also ships a Kubernetes autoscaling package, `lkscaler-keda`, for clusters that want bin-pack placement plus replica scaling.

Use `KedaAutoscalerConfig` to define the cluster-wide free-slot threshold and scale-down behavior:

```python
from lkscaler_keda import KedaAutoscalerConfig

config = KedaAutoscalerConfig(
    namespace="livekit-system",
    deployment_name="livekit-agents",
    zookeeper_hosts=["zk-0.zk:2181", "zk-1.zk:2181", "zk-2.zk:2181"],
    min_cluster_free_slots=4,
    scale_down_dwell_sec=900,
    poll_interval_sec=15,
    idle_pod_deletion_cost=0,
    busy_pod_deletion_cost=100,
    fail_closed_on_stale_snapshot=True,
)
```

Operational behavior:

- scale up when `cluster_free_slots < min_cluster_free_slots`
- only allow scale down after the dwell window has elapsed
- prefer deleting totally idle pods by applying `controller.kubernetes.io/pod-deletion-cost`

Manifest templates are provided in:

- `packages/lkscaler-keda/src/lkscaler_keda/manifests/scaledobject.yaml`
- `packages/lkscaler-keda/src/lkscaler_keda/manifests/rbac.yaml`

They are intended to be rendered with `envsubst` or another simple template mechanism before `kubectl apply`.
