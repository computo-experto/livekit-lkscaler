# livekit-lkscaler

Monorepo for LiveKit LKScaler libraries and validation suites.

## Workspace layout

- `packages/lkscaler-core`: core bin-packing and reservation lifecycle logic.
- `packages/lkscaler-livekit`: LiveKit Agent SDK hooks built on top of core.
- `packages/lkscaler-keda`: KEDA autoscaler policy, scaler, manifests, and Kubernetes reconciliation helpers.
- `e2e`: Docker Compose stack and end-to-end tests.
- `scripts`: helper scripts for integration, e2e, and release verification.

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

Publishing is handled by `.github/workflows/publish.yml` via OIDC trusted publishing.
Choose package (`lkscaler-core` or `livekit-lkscaler`) and target (`testpypi`, `pypi`, or `both`) from workflow dispatch.
