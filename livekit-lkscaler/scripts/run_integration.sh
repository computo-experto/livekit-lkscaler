#!/usr/bin/env bash
set -euo pipefail

uv run pytest packages/lkscaler-core/tests/integration packages/lkscaler-livekit/tests/integration
