# LKScaler Repository

This repository contains the planning and implementation workspace for the LiveKit LKScaler project.

## System Overview

The implementation lives in [livekit-lkscaler](livekit-lkscaler), a Python monorepo with:

- [livekit-lkscaler/packages/lkscaler-core](livekit-lkscaler/packages/lkscaler-core): core admission, bin-packing, reservation, and snapshot logic.
- [livekit-lkscaler/packages/lkscaler-livekit](livekit-lkscaler/packages/lkscaler-livekit): LiveKit Agent SDK integration hooks.
- [livekit-lkscaler/e2e](livekit-lkscaler/e2e): Docker Compose stack and end-to-end validation tests.
- [livekit-lkscaler/scripts](livekit-lkscaler/scripts): release and proof-gate helper scripts.

Supporting design and plan material is in [docs/superpowers/specs](docs/superpowers/specs) and [docs/superpowers/plans](docs/superpowers/plans).

## Build And Test

Requirements:

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Docker (for E2E)

From repository root:

```bash
cd livekit-lkscaler
uv sync --all-packages --group dev
```

Common quality commands:

```bash
cd livekit-lkscaler
make lint-check
make typecheck
make test-unit
make test-integration
make test-coverage
make test-e2e
```

Full milestone gate:

```bash
cd livekit-lkscaler
make milestone-gate
```

## Using livekit-lkscaler

Usage documentation exists under [livekit-lkscaler/docs/usage](livekit-lkscaler/docs/usage):

- [Library user guide](livekit-lkscaler/docs/usage/library-users.md)
- [Quickstart](livekit-lkscaler/docs/usage/quickstart.md)
- [Configuration](livekit-lkscaler/docs/usage/configuration.md)
- [Operations](livekit-lkscaler/docs/usage/operations.md)
- [Integration](livekit-lkscaler/docs/usage/integration.md)
- [Testing](livekit-lkscaler/docs/usage/testing.md)
- [Release](livekit-lkscaler/docs/usage/release.md)
- [Proof gate](livekit-lkscaler/docs/usage/proof-gate.md)

## Contributing

Contribution guidelines are in [CONTRIBUTING.md](CONTRIBUTING.md).