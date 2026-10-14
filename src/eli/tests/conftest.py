"""
conftest.py — ELI test suite root configuration.

Placed at: src/eli/tests/conftest.py
(or project root conftest.py)

Ensures:
- ELI_MEMORY_DB points to a temp file per-session
- Memory singleton is reset between tests
- No Ollama / GPU required
"""

import os
import sys
import pytest
from pathlib import Path

# Make sure src/ is on the path when running from project root
_SRC = Path(__file__).resolve().parent.parent.parent  # -> src/
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


@pytest.fixture(scope="session", autouse=True)
def _set_pytest_env():
    """Mark as pytest environment so config.py skips disk writes."""
    os.environ.setdefault("PYTEST_CURRENT_TEST", "yes")
    yield


@pytest.fixture(autouse=True)
def _isolate_memory_db(tmp_path, monkeypatch):
    """Every test gets its own SQLite DB and a reset singleton."""
    db = tmp_path / "eli_test.sqlite3"
    monkeypatch.setenv("ELI_MEMORY_DB", str(db))
    monkeypatch.setenv("ELI_MEMORY_DB_PATH", str(db))

    # Reset memory singleton so it picks up the new DB path
    try:
        import eli.brain.memory as mem_mod
        mem_mod._memory_singleton = None
    except Exception:
        pass

    yield

    # Cleanup singleton after test
    try:
        import eli.brain.memory as mem_mod
        mem_mod._memory_singleton = None
    except Exception:
        pass
    try:
        import eli.brain.self_improvement as si
        si._self_engine = None
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _no_gpu(monkeypatch):
    """Prevent accidental GPU usage in tests."""
    monkeypatch.setenv("ELI_N_GPU_LAYERS", "0")
    monkeypatch.setenv("ELI_GGUF_N_CTX", "512")
    yield
