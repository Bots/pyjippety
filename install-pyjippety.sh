#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_HOME="${XDG_DATA_HOME:-$HOME/.local/share}/pyjippety"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}/pyjippety"
BIN_DIR="${HOME}/.local/bin"
DESKTOP_DIR="${HOME}/.local/share/applications"
VENV_DIR="${APP_HOME}/venv"
CONFIG_FILE="${CONFIG_HOME}/.env"
WRAPPER_PATH="${BIN_DIR}/pyjippety-ui"
DESKTOP_PATH="${DESKTOP_DIR}/pyjippety.desktop"
ICON_PATH="${APP_HOME}/pyjippety-logo.svg"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required but was not found." >&2
  exit 1
fi

mkdir -p "${APP_HOME}" "${CONFIG_HOME}" "${BIN_DIR}" "${DESKTOP_DIR}"

if ! python3 -c "import tkinter" >/dev/null 2>&1; then
  echo "Tkinter is missing. Install python3-tk with your package manager and rerun this installer." >&2
  exit 1
fi

python3 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/python" -m pip install --upgrade pip setuptools wheel
"${VENV_DIR}/bin/python" -m pip install "${PROJECT_DIR}"

if [ ! -f "${CONFIG_FILE}" ]; then
  cp "${PROJECT_DIR}/.env.example" "${CONFIG_FILE}"
fi

cp "${PROJECT_DIR}/assets/pyjippety-logo.svg" "${ICON_PATH}"

cat > "${WRAPPER_PATH}" <<EOF
#!/usr/bin/env bash
set -euo pipefail
export PYJIPPETY_ENV_FILE="${CONFIG_FILE}"
exec "${VENV_DIR}/bin/pyjippety-ui" "\$@"
EOF
chmod +x "${WRAPPER_PATH}"

cat > "${DESKTOP_PATH}" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=PyJippety
Comment=Desktop voice assistant
Exec=${WRAPPER_PATH}
Icon=${ICON_PATH}
Terminal=false
Categories=Utility;
EOF

echo
echo "PyJippety is installed."
echo "Launcher: ${WRAPPER_PATH}"
echo "Desktop entry: ${DESKTOP_PATH}"
echo "Icon: ${ICON_PATH}"
echo "Config file: ${CONFIG_FILE}"
echo
echo "Next steps:"
echo "1. Launch PyJippety from your applications menu or by running: ${WRAPPER_PATH}"
echo "2. Open the Settings tab and add your OpenAI and Picovoice keys."
