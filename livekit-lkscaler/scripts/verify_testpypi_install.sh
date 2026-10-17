#!/usr/bin/env bash
set -euo pipefail

PACKAGE="${1:-}"
VERSION="${2:-}"

if [[ -z "${PACKAGE}" || -z "${VERSION}" ]]; then
  echo "Usage: $0 <package-name> <version>" >&2
  echo "Example: $0 lkscaler-core 1.0.0" >&2
  exit 2
fi

if [[ "${PACKAGE}" != "lkscaler-core" && "${PACKAGE}" != "livekit-lkscaler" ]]; then
  echo "Unsupported package: ${PACKAGE}" >&2
  echo "Allowed values: lkscaler-core | livekit-lkscaler" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv-testpypi-verify"

rm -rf "${VENV_DIR}"
uv run --python 3.12 python -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/python" -m pip install --upgrade pip

"${VENV_DIR}/bin/pip" install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  "${PACKAGE}==${VERSION}"

if [[ "${PACKAGE}" == "lkscaler-core" ]]; then
  "${VENV_DIR}/bin/python" -c "import lkscaler_core; print('testpypi-install-ok', lkscaler_core.__name__)"
else
  "${VENV_DIR}/bin/python" -c "import lkscaler_livekit; print('testpypi-install-ok', lkscaler_livekit.__name__)"
fi
