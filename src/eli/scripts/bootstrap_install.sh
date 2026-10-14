#!/usr/bin/env bash
set -euo pipefail

# ----------------------------------------
# ELI one-click install (Ubuntu/Debian)
# - installs system deps
# - creates venv in ./ .venv
# - installs python deps
# - installs ELI as editable
# - creates desktop launcher (per-user)
# - installs a user systemd service for the daemon (only with ELI_INSTALL_DAEMON=1)
# - initializes config + persona + sqlite if needed
# ----------------------------------------

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
VENV_DIR="${PROJECT_ROOT}/.venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "[ELI] Project root: ${PROJECT_ROOT}"

echo "[ELI] Installing system dependencies (apt)..."
sudo apt-get update
sudo apt-get install -y \
  "${PYTHON_BIN}" "${PYTHON_BIN}-venv" "${PYTHON_BIN}-dev" \
  python3-pip \
  build-essential \
  pkg-config \
  libasound2-dev \
  portaudio19-dev \
  ffmpeg \
  git \
  xclip \
  sqlite3 \
  curl

# Some GUI stacks may need these depending on distro image
sudo apt-get install -y \
  libxcb-cursor0 \
  libxcb-xinerama0 \
  libegl1 \
  libgl1 || true

echo "[ELI] Creating virtual environment..."
${PYTHON_BIN} -m venv "${VENV_DIR}"

echo "[ELI] Activating venv..."
# shellcheck disable=SC1090
source "${VENV_DIR}/bin/activate"

echo "[ELI] Upgrading pip tooling..."
pip install --upgrade pip wheel setuptools

echo "[ELI] Installing Python requirements..."
pip install -r "${PROJECT_ROOT}/requirements.txt"

echo "[ELI] Installing ELI (editable)..."
pip install -e "${PROJECT_ROOT}"

echo "[ELI] Initializing config + persona + memory db..."
python -m eli.tools.manage_eli init || true

echo "[ELI] Creating per-user desktop entry..."
mkdir -p "${HOME}/.local/share/applications"
cat > "${HOME}/.local/share/applications/eli.desktop" <<EOF
[Desktop Entry]
Name=ELI
Comment=Entropic Logical Interpreter
Exec=${VENV_DIR}/bin/eli-gui
Icon=${PROJECT_ROOT}/src/eli/api/favicon.ico
Terminal=false
Type=Application
Categories=Utility;AI;
EOF

chmod +x "${HOME}/.local/share/applications/eli.desktop"
update-desktop-database "${HOME}/.local/share/applications" >/dev/null 2>&1 || true

if [ "${ELI_INSTALL_DAEMON:-0}" = "1" ]; then
echo "[ELI] Installing the background daemon as a user service (systemd --user)"
mkdir -p "${HOME}/.config/systemd/user"
cat > "${HOME}/.config/systemd/user/eli-daemon.service" <<EOF
[Unit]
Description=ELI background daemon
After=default.target

[Service]
Type=simple
WorkingDirectory=${PROJECT_ROOT}
ExecStart=${VENV_DIR}/bin/eli-daemon
Restart=always
RestartSec=2

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload || true
systemctl --user enable --now eli-daemon.service || true
fi

echo
echo "[ELI] Install complete."
echo "[ELI] Run GUI:   ${VENV_DIR}/bin/eli-gui"
echo "[ELI] Run daemon:${VENV_DIR}/bin/eli-daemon"
echo "[ELI] Check setup: ${VENV_DIR}/bin/eli-cli check"
