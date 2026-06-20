# Operations

This guide summarizes runtime behavior, failure handling, and local troubleshooting.

For library setup and configuration, see [Library User Guide](library-users.md). This page only covers runtime behavior after deployment.

## Runtime model

- `load_fnc` advertises availability (`0.0` winner, `1.0` loser) using cluster free-slot view.
- `on_request` applies overflow guard, creates reservation, then accepts.
- Reservations are cleaned up on accept failure or timeout.

## Known failure modes

- ZooKeeper unavailable:
	- fallback policy: accept only when local occupancy is below `room_target_n`.
- Stale reservations:
	- bounded by `reservation_ttl_sec` and timeout cleanup.
- Slow convergence:
	- tune `sync_interval_ms` and validate watcher health.

## Local runbooks

On E2E failure, inspect:

- `e2e/artifacts/compose-ps.txt`
- `e2e/artifacts/compose-logs.txt`
