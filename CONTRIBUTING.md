# Contributing

Thank you for contributing to LKScaler.

## Repository Layout

- Main implementation workspace: [livekit-lkscaler](livekit-lkscaler)
- Project plans/specs: [docs/superpowers](docs/superpowers)

Most code changes should happen inside [livekit-lkscaler](livekit-lkscaler).

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Docker (required for E2E tests)

## Local Setup

```bash
cd livekit-lkscaler
uv sync --all-packages --group dev
```

## Development Workflow

1. Create a branch from `main`.
2. Make focused changes with tests.
3. Run quality gates locally.
4. Open a pull request.

Recommended local checks:

```bash
cd livekit-lkscaler
make lint-check
make typecheck
make test-unit
make test-integration
make test-coverage
```

Before requesting review for major changes, run:

```bash
cd livekit-lkscaler
make milestone-gate
```

## Testing Expectations

- Add or update tests for behavior changes.
- Prefer unit tests for isolated logic in package modules.
- Add integration or E2E tests when behavior spans service boundaries.

## Pull Request Guidelines

- Keep PRs scoped and reviewable.
- Describe motivation, approach, and validation performed.
- If E2E fails in CI, inspect artifacts from [livekit-lkscaler/e2e/artifacts](livekit-lkscaler/e2e/artifacts).
- Do not mix unrelated refactors with feature or bug-fix changes.

## Documentation

When behavior or public usage changes, update the relevant usage docs in [livekit-lkscaler/docs/usage](livekit-lkscaler/docs/usage).