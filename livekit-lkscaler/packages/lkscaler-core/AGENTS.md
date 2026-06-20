# AGENTS.md

Scope: lkscaler-core package.

- Preserve public API exports in src/lkscaler_core/__init__.py unless explicitly changing API surface.
- Core modules should remain SDK-agnostic and focused on admission/load logic.
- Any behavior change should include/adjust unit tests in tests/unit.
- Integration checks for core flows belong in tests/integration.
- Keep overflow guard and reservation timeout semantics consistent with design spec.
- Avoid adding network/runtime side effects in pure domain code.
- Maintain deterministic tests; avoid flaky time dependencies.
