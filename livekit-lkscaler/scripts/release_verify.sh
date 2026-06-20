#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${ROOT_DIR}/dist"
VERIFY_VENV="${ROOT_DIR}/.venv-release-verify"

rm -rf "${DIST_DIR}" "${VERIFY_VENV}"
mkdir -p "${DIST_DIR}/core" "${DIST_DIR}/livekit"

uv build "${ROOT_DIR}/packages/lkscaler-core" --out-dir "${DIST_DIR}/core"
uv build "${ROOT_DIR}/packages/lkscaler-livekit" --out-dir "${DIST_DIR}/livekit"

uv run --python 3.12 python -m venv "${VERIFY_VENV}"
"${VERIFY_VENV}/bin/python" -m pip install --upgrade pip
"${VERIFY_VENV}/bin/pip" install "${DIST_DIR}/core"/*.whl
"${VERIFY_VENV}/bin/pip" install "${DIST_DIR}/livekit"/*.whl
"${VERIFY_VENV}/bin/python" - <<'PY'
import lkscaler_core
import lkscaler_livekit

print("release-smoke-ok", lkscaler_core.__name__, lkscaler_livekit.__name__)
PY
