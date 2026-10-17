#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${ROOT_DIR}/dist"
VERIFY_VENV="${ROOT_DIR}/.venv-release-verify"

rm -rf "${DIST_DIR}" "${VERIFY_VENV}"
mkdir -p "${DIST_DIR}/core" "${DIST_DIR}/livekit"

# Both packages ship as one coordinated release, so their versions must match.
core_version="$(uv run --python 3.12 python -c "import tomllib; print(tomllib.load(open('${ROOT_DIR}/packages/lkscaler-core/pyproject.toml', 'rb'))['project']['version'])")"
livekit_version="$(uv run --python 3.12 python -c "import tomllib; print(tomllib.load(open('${ROOT_DIR}/packages/lkscaler-livekit/pyproject.toml', 'rb'))['project']['version'])")"
if [[ "${core_version}" != "${livekit_version}" ]]; then
	echo "error: lkscaler-core (${core_version}) and livekit-lkscaler (${livekit_version}) must share one release version" >&2
	exit 1
fi

uv build "${ROOT_DIR}/packages/lkscaler-core" --out-dir "${DIST_DIR}/core"
uv build "${ROOT_DIR}/packages/lkscaler-livekit" --out-dir "${DIST_DIR}/livekit"

for entry in "lkscaler_core:core" "livekit_lkscaler:livekit"; do
	dist_name="${entry%%:*}"
	dist_dir="${DIST_DIR}/${entry##*:}"
	wheels=("${dist_dir}/${dist_name}-"*.whl)
	sdists=("${dist_dir}/${dist_name}-"*.tar.gz)
	if [[ ! -f "${wheels[0]}" || ! -f "${sdists[0]}" ]]; then
		echo "error: missing wheel or sdist for ${dist_name} in ${dist_dir}" >&2
		exit 1
	fi
done

uv run --python 3.12 python -m venv "${VERIFY_VENV}"
"${VERIFY_VENV}/bin/python" -m pip install --upgrade pip
"${VERIFY_VENV}/bin/pip" install "${DIST_DIR}/core"/*.whl
"${VERIFY_VENV}/bin/pip" install "${DIST_DIR}/livekit"/*.whl
"${VERIFY_VENV}/bin/python" - <<'PY'
import lkscaler_core
import lkscaler_livekit

print("release-smoke-ok", lkscaler_core.__name__, lkscaler_livekit.__name__)
PY
