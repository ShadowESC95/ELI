#!/usr/bin/env bash
set -euo pipefail

# Always run from repo root (this file lives in ./tests)
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

# Prefer the current venv's pytest; fall back to python -m pytest for sanity.
if command -v pytest >/dev/null 2>&1; then
  PYTEST=(pytest)
else
  PYTEST=(python -m pytest)
fi

# Ensure local src-layout is importable even without editable install.
export PYTHONPATH="$REPO/src${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONNOUSERSITE=1

python -V
python - <<'PY'
import eli, inspect, sys
print("eli:", inspect.getfile(eli))
print("sys.path[:6]:", sys.path[:6])
PY

"${PYTEST[@]}" -q
