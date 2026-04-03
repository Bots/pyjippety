#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${PROJECT_DIR}/.venv"

if [ ! -x "${VENV_DIR}/bin/python" ]; then
  echo "Expected a virtual environment at ${VENV_DIR}. Create it first, then rerun." >&2
  exit 1
fi

"${VENV_DIR}/bin/python" -m pip install --upgrade pyinstaller

"${VENV_DIR}/bin/pyinstaller" \
  --noconfirm \
  --clean \
  --windowed \
  --onedir \
  --name pyjippety \
  --paths "${PROJECT_DIR}/src" \
  --add-data "${PROJECT_DIR}/assets:assets" \
  "${PROJECT_DIR}/src/pyjippety/gui.py"

echo
echo "Bundle created in ${PROJECT_DIR}/dist/pyjippety"
