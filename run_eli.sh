#!/usr/bin/env bash
# Starts the ELI window from this folder (uses ./.venv when it is there).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export ELI_PROJECT_ROOT="$ROOT"
export ELI_ROOT="$ROOT/src/eli"
export ELI_MEMORY_DB="${ELI_MEMORY_DB:-${XDG_DATA_HOME:-$HOME/.local/share}/eli/eli_memory.sqlite3}"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

PY="${PYTHON:-python3}"
[ -x "$ROOT/.venv/bin/python" ] && PY="$ROOT/.venv/bin/python"
exec "$PY" -m eli.gui.app "$@"
