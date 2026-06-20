# AGENTS.md

Scope: helper scripts.

- Keep scripts POSIX-shell compatible unless bash-only features are required.
- Use `set -euo pipefail` for robustness.
- Favor clear logging and explicit failure messages.
- Preserve cleanup traps for docker compose lifecycle scripts.
- Any script behavior change should be reflected in CI/local usage docs.
- Keep artifact paths stable for workflow uploads.
