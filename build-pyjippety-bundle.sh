#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON:-python3}"

exec "${PYTHON_BIN}" "${PROJECT_DIR}/build-pyjippety-bundle.py" "$@"
