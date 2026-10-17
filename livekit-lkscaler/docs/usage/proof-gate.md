# Proof Gate Guide (Milestone 9)

This guide defines the real-world integration proof gate required before PyPI publish.

## Scenario matrix

The gate targets these scenarios. Scenarios 1-3 are asserted today by the compose-backed tests; scenarios 4 and 5 are still planned, not enforced:

1. Steady load placement trend.
2. Burst load is **out of scope by decision**: absorbing a burst depends on headroom the operator
   provisions, not on the placement path. See `operations.md` for the measured behaviour and the
   recommendation to keep free capacity sized to the burst pattern.
3. Assignment failure cleanup.
4. Backend outage and reconnect is **out of scope by decision**: ZooKeeper runs as an ensemble and Redis
   as a central store, so a total outage is not a failure mode to engineer against. The behaviour is
   KEDA's `fallback` block plus the store TTL for stale pods, documented in the scaler's README.
5. Parent/job restart behavior for reservation-room reconciliation.
6. KEDA scale up **and** back down on a real Deployment in kind (`make test-keda-scale-e2e`).

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
- ZooKeeper disconnect and reconnect convergence: no worker connects to ZooKeeper today, so the scenario cannot be exercised yet.
- Parent/job restart reconciliation: the E2E agents are long-running simulators, not real job processes.
- Real dispatch lifecycle telemetry assertions (when non-placeholder agents are integrated).

## Release policy link

The proof gate is the documented real-world integration gate for this project, but it is not yet enforced by
workflow automation: the Publish workflow does not run `make proof-gate`, and the soak, fault-injection, and
real-agent telemetry scenarios above are still planned (Milestone 9 in progress). Until the gate is wired
into the workflow, publishing both packages is an explicit owner decision that must not be described as
proof-gated.
