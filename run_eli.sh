#!/usr/bin/env bash
# Starts the ELI window from this folder (uses ./.venv when it is there), through the same launcher
# as the AppImage: ELI keeps to its own folders (~/.local/share/eli-ai, ~/.config/eli-ai) and its own
# settings (~/.config/eli-ai/settings or ELI_AI_... variables).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

PY="${PYTHON:-python3}"
[ -x "$ROOT/.venv/bin/python" ] && PY="$ROOT/.venv/bin/python"
exec "$PY" "$ROOT/packaging/eli_app.py" "$@"
