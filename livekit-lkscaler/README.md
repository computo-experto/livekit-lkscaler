# livekit-lkscaler

LiveKit agent worker hooks and placement primitives that make self-hosted Agent fleets cheaper: jobs are bin-packed onto workers that fill toward a capacity target, so idle workers appear genuinely idle and the cluster scales down sooner.

No particular autoscaler is required. Use Kubernetes HPA or KEDA if you have them, or any replica manager that reacts to the `load_fnc` value; shared state comes from ZooKeeper or from any store you already run (see [Shared state](#shared-state)).

## Workspace layout

- `packages/lkscaler-core`: core bin-packing and reservation lifecycle logic.
- `packages/lkscaler-livekit`: LiveKit Agent SDK hooks built on top of core.
- `packages/lkscaler-keda`: optional KEDA external scaler, policy, and Kubernetes reconciliation helpers for clusters that run KEDA.
- `e2e`: Docker Compose stack and end-to-end tests.
- `scripts`: helper scripts for integration, e2e, and release verification.

## Shared state

Reservations and cluster occupancy need a store every worker can read. `InMemoryReservationStore` is what ships today and it is single-process only, so a real multi-worker fleet needs an implementation of the `ReservationStore` contract: ZooKeeper is the designed backend (a kazoo-backed store is not written yet), but etcd, Redis, or an existing service of yours work equally well.

## Requirements

- Python 3.12+
- `uv`
- Docker (for E2E)
- `kind`, `kubectl`, and `envsubst` (for KEDA kind E2E)

## Local setup

```bash
uv sync --all-packages --group dev
```

## Quality gates

Run per milestone:

```bash
make milestone-gate
```

Run the KEDA autoscaling harness only:

```bash
make test-keda-e2e
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

## KEDA autoscaling summary

The repository now includes a KEDA integration package that:

- computes cluster-wide free-slot policy decisions
- exposes an external scaler interface for KEDA
- biases scale-down toward idle pods using pod deletion cost
- validates the scaling path in kind with a lightweight agent simulator

## Publishing

Publishing is handled by `.github/workflows/publish.yml` via OIDC trusted publishing. One run publishes
both `lkscaler-core` and `livekit-lkscaler` together: build both, twine check, smoke-install both wheels in
the runner, publish both to TestPyPI, gate on installing both from TestPyPI, then publish both to PyPI when
the target is `both`.

Triggers:

- `workflow_dispatch` with target `testpypi` (rehearsal) or `both` (TestPyPI, then PyPI).
- Pushing a `release-vX.Y.Z` tag, which runs the staged flow for both packages and requires the tag to
  match the package versions.

Keep both package versions identical before releasing; the workflow and `make release-verify` reject a
mismatch.
