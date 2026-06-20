# AGENTS.md

Scope: E2E stack and tests.

- Compose stack is the source of truth for E2E topology.
- Ensure ZooKeeper healthchecks remain compatible with image defaults and whitelist requirements.
- Run full E2E via scripts/run_e2e.sh (or make test-e2e).
- E2E tests requiring running stack should be gated by E2E_STACK_RUNNING.
- Preserve artifact capture in e2e/artifacts for failures.
- Keep E2E tests focused on readiness/contracts and critical cross-service behavior.
