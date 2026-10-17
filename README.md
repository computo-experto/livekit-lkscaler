# LKScaler Repository

LKScaler makes self-hosted LiveKit Agents fleets cheaper to run.

LiveKit spreads incoming jobs across every worker that reports itself available. LKScaler changes that: it bin-packs jobs so workers fill toward a capacity target before spillover, which concentrates load and leaves other workers genuinely idle. Because a worker that is full-but-under-target can advertise itself as busy, the cluster can scale down sooner instead of paying for capacity it is not using. That is the whole point of the project: faster scale-down, lower cost, same placement quality.

It does not require a particular autoscaler or coordination service:

- **Scaling.** Use Kubernetes HPA or KEDA if your cluster has them, or any replica manager that reacts to the load signal a LiveKit Agent worker reports. Nothing in the placement path needs KEDA.
- **Shared state.** Reservations and cluster occupancy have to live somewhere all workers can read. ZooKeeper is the designed backend. Any store you already run works too, as long as it implements the reservation store contract in `lkscaler-core`. Today the shipped packages bundle only an in-memory store, which is single-process: running a real fleet means supplying the shared store, and a ZooKeeper-backed implementation is still to be written.

## What Is Here

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