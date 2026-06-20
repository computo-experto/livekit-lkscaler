# Testing Guide

This project uses layered tests.

## Test layers

- Unit tests: deterministic logic in core and livekit adapter.
- Integration tests: package-level integration behavior.
- E2E tests: compose-backed stack checks in `e2e/tests`.

## Common commands

```bash
make test-unit
make test-integration
make test-coverage
make test-e2e
```

Run all local quality gates for milestones:

```bash
make milestone-gate
```

Release packaging smoke test:

```bash
make release-verify
```

## Notes

- E2E tests requiring a running stack are gated by `E2E_STACK_RUNNING`.
- Compose diagnostics are written to `e2e/artifacts/` on failures.
- Coverage gate is enforced on unit+integration tests with `COVERAGE_MIN` (default `90`).
