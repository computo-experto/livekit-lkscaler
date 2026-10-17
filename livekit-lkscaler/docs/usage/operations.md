# Operations

This guide summarizes runtime behavior, failure handling, and local troubleshooting.

For library setup and configuration, see [Library User Guide](library-users.md). This page only covers runtime behavior after deployment.

## Runtime model

- `load_fnc` advertises availability (`0.0` winner, `1.0` loser) using cluster free-slot view.
- `on_request` applies overflow guard, creates reservation, then accepts.
- Reservations are cleaned up on accept failure or timeout.

## Known failure modes

- Coordination store unavailable:
	- the shipped helpers implement no fallback; your tracker decides what the worker reports and accepts.
	- `fail_mode` records the intended policy (`accept_if_local_below_n`) but nothing reads it yet.
- Stale reservations:
	- bounded by `reservation_ttl_sec` and timeout cleanup.
- Slow convergence:
	- tune `sync_interval_ms` and validate watcher health.

## Capacity, bursts, and scale policy

How much spare capacity to carry is your decision, not the library's: a dispatching burst is absorbed only by
workers that exist and are still admitting, so size the fleet for the burst pattern you actually expect and
let the scale policy provision it ahead of time.

Measured on a 3-worker pool configured with `room_target_n=2` and `overflow_margin=1` (nine slots in total),
against a burst of five dispatched rooms:

- the pool accepted three rooms, filling one worker to its hard bound;
- the two remaining rooms stayed queued for the whole 30-second sample, even though a second worker was
  advertising itself available;
- the worker already at its bound received all ten of the server's dispatch attempts, the idle worker none.

So a room offered to a worker which then declines it (the admission handler rejects so the room is not
terminated) waits for that worker rather than moving to an idle peer. Plan headroom for bursts and treat
scale-up latency as a capacity budget; per-room redistribution during a burst is not something to rely on.

## Local runbooks

On E2E failure, inspect:

- `e2e/artifacts/compose-ps.txt`
- `e2e/artifacts/compose-logs.txt`
