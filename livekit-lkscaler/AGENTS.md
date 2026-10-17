# AGENTS.md

Scope: livekit-lkscaler workspace.

- Use uv for dependency and command execution.
- Canonical quality gates:
  - `make format`
  - `make lint-check`
  - `make typecheck`
  - `make test`
- Full milestone gate: `make milestone-gate`.
- `make help` lists every target with its description; every target carries a `## <description>` comment and `help` is the default goal, so keep both current when targets change.
- Unit tests are required for new Java code changes per user preference; this repo is Python, keep same rigor for Python unit coverage.
- Keep ruff/mypy strictness intact; fix violations rather than relaxing rules.
- Prefer small, targeted patches over broad refactors.
- Keep documentation and test naming unique to avoid duplicate test module issues.
