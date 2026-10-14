#!/usr/bin/env bash
# Runs the tests on a throwaway database, away from your own settings.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
PY="${PYTHON:-python3}"
[ -x .venv/bin/python ] && PY=.venv/bin/python

export PYTHONPATH="$ROOT/src"
unset ELI_DB_PATH ELI_MEMORY_DB_PATH ELI_TEMP ELI_TEMPERATURE ELI_NUM_PREDICT
export ELI_DB_PATH="$(mktemp -t eli_test_db_XXXXXX.sqlite3)"
export ELI_MEMORY_DB_PATH="$ELI_DB_PATH"

exec "$PY" -m pytest -q "$@"
