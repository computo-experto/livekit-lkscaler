# AGENTS.md

Scope: lkscaler-livekit adapter package.

- Keep adapter aligned with current LiveKit hook names: on_request and load_fnc.
- Preserve separation: this package adapts core logic, not re-implementing it.
- Add/maintain unit tests in tests/unit for hook behavior and cleanup semantics.
- Add integration tests in tests/integration for wiring-level confidence.
- Keep call signatures stable where tests and typing depend on keyword names.
- When uncertain on SDK semantics, prefer explicit tests over assumptions.
