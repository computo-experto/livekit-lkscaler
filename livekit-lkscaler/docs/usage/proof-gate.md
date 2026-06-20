# Proof Gate Guide (Milestone 9)

This guide defines the real-world integration proof gate required before PyPI publish.

## Scenario matrix

The gate targets these scenarios:

1. Steady load placement trend.
2. Burst load with bounded overflow.
3. Assignment failure cleanup.
4. ZooKeeper disconnect and reconnect convergence.
5. Parent/job restart behavior for reservation-room reconciliation.

## Gate command

```bash
make proof-gate
```

Current baseline:

- Runs milestone gate checks.
- Executes E2E stack assertions and compose contract checks.
- Enforces quantitative artifact thresholds:
	- exactly 6 declared/running services in compose ps output.
	- at least 4 healthy services (zk1-3 + livekit expected).
	- each healthy service uptime >= 5 seconds at capture time.
	- compose logs contain >= 80 lines and startup signals for ZooKeeper (>=3) and LiveKit (>=1).
- Enforces deterministic lifecycle thresholds in proof tests:
	- assignment-failure cleanup latency < 0.2s (core) and < 0.3s (livekit adapter path).
	- reservation expiry cleanup at TTL boundary (`remove_expired` at deadline removes exactly once).
	- synthetic churn packing trend for homogeneous pods: one pod fills to target before spillover.

Future expansions (planned):

- Soak test with repeated churn.
- Fault injection and bounded-safety assertions from artifacts.
- Real dispatch lifecycle telemetry assertions (when non-placeholder agents are integrated).

## Release policy link

PyPI publish remains blocked until this proof gate and scenario matrix are marked complete.
