#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${ROOT_DIR}/dist"
VERIFY_VENV="${ROOT_DIR}/.venv-release-verify"

rm -rf "${DIST_DIR}" "${VERIFY_VENV}"
mkdir -p "${DIST_DIR}/core" "${DIST_DIR}/livekit" "${DIST_DIR}/keda"

# All three packages ship as one coordinated release, so their versions must match.
package_version() {
	uv run --python 3.12 python -c "import tomllib; print(tomllib.load(open('${ROOT_DIR}/packages/$1/pyproject.toml', 'rb'))['project']['version'])"
}

core_version="$(package_version lkscaler-core)"
livekit_version="$(package_version lkscaler-livekit)"
keda_version="$(package_version lkscaler-keda)"
if [[ "${core_version}" != "${livekit_version}" || "${core_version}" != "${keda_version}" ]]; then
	echo "error: lkscaler-core (${core_version}), livekit-lkscaler (${livekit_version}) and lkscaler-keda (${keda_version}) must share one release version" >&2
	exit 1
fi

uv build "${ROOT_DIR}/packages/lkscaler-core" --out-dir "${DIST_DIR}/core"
uv build "${ROOT_DIR}/packages/lkscaler-livekit" --out-dir "${DIST_DIR}/livekit"
uv build "${ROOT_DIR}/packages/lkscaler-keda" --out-dir "${DIST_DIR}/keda"

for entry in "lkscaler_core:core" "livekit_lkscaler:livekit" "lkscaler_keda:keda"; do
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
for dist_dir in core livekit keda; do
	"${VERIFY_VENV}/bin/pip" install "${DIST_DIR}/${dist_dir}"/*.whl
done
"${VERIFY_VENV}/bin/python" - <<'PY'
import lkscaler_core
import lkscaler_keda
import lkscaler_livekit

print("release-smoke-ok", lkscaler_core.__name__, lkscaler_livekit.__name__, lkscaler_keda.__name__)
PY
