# livekit-lkscaler

LiveKit agent worker hooks and placement primitives that make self-hosted Agent fleets cheaper: jobs are bin-packed onto workers that fill toward a capacity target, so idle workers appear genuinely idle and the cluster scales down sooner.

No particular autoscaler is required. Use Kubernetes HPA or KEDA if you have them, or any replica manager that reacts to the `load_fnc` value; shared state comes from ZooKeeper or from any store you already run (see [Shared state](#shared-state)).

## Scope and limits

Use LKScaler when you run LiveKit Agents yourself and want placement and replica counts to come from one
shared, inspectable view of the fleet. What ships, and what stays yours:

- Shipped: the admission decision and its overflow guard, single-winner load signalling, reservation claims
  with TTL expiry, coordination over ZooKeeper or Redis, and the KEDA external scaler.
- Yours: the store connection, the tracker that publishes each worker's occupancy on a cadence, and the
  replica-manager policy. `e2e/fixtures/real_agent.py` is the reference composition; it is test code today, not
  a packaged runtime.
- The scaler never asks for zero replicas: a pool with no workers cannot accept a dispatch, so one is the floor
  (`minReplicaCount: 1`) and KEDA's scale-to-zero path is unused by design.
- A dispatch that a worker declines can stay queued on the server instead of moving to an idle peer; the
  admission handler cannot re-route it. Size free capacity to your burst pattern rather than relying on
  re-dispatch. Measurements are in [operations](docs/usage/operations.md).
- While a job process releases its reservation, the parent's local reservation is still counted until
  `reservation_ttl_sec` expires, so free capacity reads slightly low for at most that TTL.

## Workspace layout

- `packages/lkscaler-core`: core bin-packing and reservation lifecycle logic.
- `packages/lkscaler-livekit`: LiveKit Agent SDK hooks built on top of core.
- `packages/lkscaler-keda`: KEDA external scaler that turns the placement signal into a replica count.
- `e2e`: Docker Compose stack and end-to-end tests.
- `scripts`: helper scripts for integration, e2e, and release verification.

## Shared state

Reservations and cluster occupancy need a store every worker can read. What ships in the base install is `InMemoryReservationStore`, which is single-process and meant for tests; a real fleet uses a shared backend. ZooKeeper (`pip install "lkscaler-core[zookeeper]"`) and Redis (`pip install "lkscaler-core[redis]"`) are both implemented and integration-tested against real servers. Anything you already run works too, as long as it keeps the `ReservationStore` and `ClusterStateStore` contracts. See [Coordination backends](docs/usage/coordination.md).

## Requirements

- Python 3.12+
- `uv`
- Docker (for E2E)

## Local setup

```bash
uv sync --all-packages --group dev
```

## Quality gates

Every target is listed with its purpose:

```bash
make help
```

Run per milestone:

```bash
make milestone-gate
```

Run release smoke verification locally:

```bash
make release-verify
```

## Documentation

- `docs/usage/library-users.md`
- `docs/usage/quickstart.md`
- `docs/usage/configuration.md`
- `docs/usage/operations.md`
- `docs/usage/integration.md`
- `docs/usage/testing.md`
- `docs/usage/release.md`
- `docs/usage/proof-gate.md`

## License

Apache-2.0 — see `LICENSE` and `NOTICE` in the repository root.

## Publishing

Publishing is handled by `.github/workflows/publish.yml` via OIDC trusted publishing. One run publishes
all three packages together: build them, twine check, smoke-install the wheels in
the runner, publish both to TestPyPI, gate on installing both from TestPyPI, then publish both to PyPI when
the target is `both`.

Triggers:

- `workflow_dispatch` with target `testpypi` (rehearsal) or `both` (TestPyPI, then PyPI).
- Pushing a `release-vX.Y.Z` tag, which runs the staged flow for all three packages and requires the tag to
  match the package versions.

Keep all three package versions identical before releasing; the workflow and `make release-verify` reject a
mismatch.
