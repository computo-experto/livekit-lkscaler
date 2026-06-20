# AGENTS.md

Scope: repository CI and automation under .github.

- Keep CI jobs explicit and readable: separate steps for lint, typecheck, unit, integration, and e2e.
- CI currently runs with working-directory set to livekit-lkscaler.
- Prefer Makefile targets in CI steps to keep local and CI behavior aligned.
- Preserve artifact upload on failure for E2E diagnostics.
- Avoid introducing hidden shell complexity in workflow steps.
- When changing test commands, ensure pyproject testpaths and directory layout still match.
