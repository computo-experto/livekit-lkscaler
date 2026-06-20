# Quickstart

For integrating `livekit-lkscaler` into an existing LiveKit Agent worker, start with the [Library User Guide](library-users.md).

This page stays as a short repository-local example.

## Install the workspace

```bash
uv sync --all-packages --group dev
```

For package consumers outside this repository:

```bash
pip install livekit-lkscaler
```

## Minimal example

```python
from lkscaler_core import BinpackConfig, InMemoryReservationStore, PodOccupancy
from lkscaler_livekit import build_load_fnc, build_on_request_handler


class Tracker:
	def get_local_occupancy(self) -> PodOccupancy:
		return PodOccupancy(active_rooms=0, reservations=0)

	def get_cluster_free_slots(self) -> dict[str, int]:
		return {"pod-a": 2, "pod-b": 0}


config = BinpackConfig(
	namespace="livekit-lkscaler",
	pod_id="pod-a",
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

## Wire the hooks

Pass `on_request` and `load_fnc` to your LiveKit worker/server setup according to your SDK entrypoint.

For the consumer-focused setup, prerequisites, and configuration walk-through, see [Library User Guide](library-users.md).
