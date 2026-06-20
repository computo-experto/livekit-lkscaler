# livekit-lkscaler

Monorepo for LiveKit LKScaler libraries and validation suites.

## Workspace layout

- `packages/lkscaler-core`: core bin-packing and reservation lifecycle logic.
- `packages/lkscaler-livekit`: LiveKit Agent SDK hooks built on top of core.
- `e2e`: Docker Compose stack and end-to-end tests.
- `scripts`: helper scripts for integration, e2e, and release verification.

## Requirements

- Python 3.12+
- `uv`
- Docker (for E2E)

## Local setup

```bash
uv sync --all-packages --group dev
```

## Quality gates

Run per milestone:

```bash
make milestone-gate
```

Run release smoke verification locally:

```bash
make release-verify
```

## Documentation

- `docs/usage/quickstart.md`
- `docs/usage/configuration.md`
- `docs/usage/operations.md`
- `docs/usage/integration.md`
- `docs/usage/testing.md`
- `docs/usage/release.md`
- `docs/usage/proof-gate.md`

## Publishing

Publishing is handled by `.github/workflows/publish.yml` via OIDC trusted publishing.
Choose package (`lkscaler-core` or `livekit-lkscaler`) and target (`testpypi`, `pypi`, or `both`) from workflow dispatch.
