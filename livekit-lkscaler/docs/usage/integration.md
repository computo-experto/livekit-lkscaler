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

- `load_fnc` returns `0.0` for the single winning worker and `1.0` for every other worker, including a worker whose slots its peers cannot see yet.
- `on_request` creates reservation before accept.
- If accept fails, reservation is cleaned up.
- Overflow admission is bounded by `room_target_n + overflow_margin`.
