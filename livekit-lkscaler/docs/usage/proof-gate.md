# Proof Gate Guide (Milestone 9)

This guide defines the real-world integration proof gate required before PyPI publish.

## Scenario matrix

Every scenario below is either enforced by a command `make proof-gate` runs, or listed as out of scope by an owner decision recorded in this file. There is no third state: nothing here is "planned" for the 1.0 gate.

1. Steady load placement trend - enforced by the compose E2E and the real-agent scenarios (`make test-e2e`, `make test-real-agent-scenarios`).
2. Burst load is **out of scope by decision**: absorbing a burst depends on headroom the operator
   provisions, not on the placement path. See `operations.md` for the measured behaviour and the
   recommendation to keep free capacity sized to the burst pattern.
3. Assignment failure cleanup - enforced by the proof assertions in `make test-proof`.
4. Backend outage and reconnect is **out of scope by decision**: ZooKeeper runs as an ensemble and Redis
   as a central store, so a total outage is not a failure mode to engineer against. The behaviour is
   KEDA's `fallback` block plus the store TTL for stale pods, documented in the scaler's README.
5. Parent/job restart behavior for reservation-room reconciliation - **out of scope by decision**: a worker restart is a new LiveKit job that the server schedules, and the recovery path that matters for placement is reservation TTL expiry, which scenario 3 asserts.
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

Out of scope for the 1.0 gate, by owner decision:

- Burst absorption: a burst fails when the fleet cannot scale fast enough, so headroom is an operator capacity
  policy, not library behaviour. `operations.md` records the measured numbers and the recommendation.
- Backend outage and reconnect: ZooKeeper runs as an ensemble and Redis as a central store, so a total outage
  is not a failure mode to engineer against. KEDA's `fallback` block and the pod-state TTL cover the degraded
  path and are documented in the scaler's README.
- Soak with repeated churn: the scenario suite already runs every scenario from a clean server slate, and
  churn beyond that measures the operator's capacity planning rather than placement correctness.
- Fault injection and bounded-safety fuzzing: no observed defect class justifies the harness cost before the
  1.0 gate; revisit on community reports.
- Real dispatch lifecycle telemetry: the real-agent scenarios observe accepted rooms, occupancy and the
  resulting replica count, which is the telemetry an operator acts on.

## Release policy link

`make proof-gate` is the gate this document describes, and the Publish workflow runs exactly that command in a
`proof-gate` job: `publish-testpypi` declares `needs: [build-and-verify, proof-gate]` and only runs when the gate
job succeeded, so no release reaches an index while any enforced scenario fails. The job installs `kind` and
`kubectl` itself, because the gate spans unit and integration tests, the compose E2E suite, the real-agent
scenario suite, the proof assertions and the KEDA scale proof in kind.
