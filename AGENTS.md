# AGENTS.md

Scope: entire repository.

- Primary implementation workspace is livekit-lkscaler; run coding checks from there unless the task is repo-level.
- Keep CI step clarity in .github/workflows/ci.yml; do not collapse named steps into one opaque command.
- Prefer non-destructive edits and preserve user changes in unrelated files.
- Before changing files recently touched by user/tools, re-read current contents.
- For code quality gates, use Makefile targets in livekit-lkscaler.
- Every Makefile carries a self-documenting `help` target: one `## <description>` per target, `help` as the default goal, and it stays current when targets are added or renamed.
- For milestone validation, run `make milestone-gate` from livekit-lkscaler.
- If E2E fails, collect/inspect e2e/artifacts/compose-ps.txt and e2e/artifacts/compose-logs.txt.
- Keep Python baseline aligned to 3.12+ and uv workflow.
