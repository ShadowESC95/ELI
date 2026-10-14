"""
eli/tests/integration/conftest.py

Shared fixtures and startup logic for integration tests.

Why this file exists:
- pytest-7.4.4 (used in this project) does NOT discover fixtures defined inside
  test files when those fixtures are used by other fixtures in the same file.
  Moving fixtures here makes them available project-wide.

- On startup, this file invalidates stale .pyc caches for brain/memory.py so that
  a freshly edited memory.py is always compiled from source, not from a cached
  bytecode that predates the edit.
"""

import os
import sys
import importlib
import pytest
from pathlib import Path

# ---------------------------------------------------------------------------
# Auto-invalidate stale pyc for memory.py so edits take effect immediately
# ---------------------------------------------------------------------------

def _invalidate_memory_pyc():
    """
    Delete stale .pyc files for brain/memory.py and force reimport.
    This is necessary because Python caches compiled bytecode and may
    load an older compiled version instead of the updated source.
    """
    brain_dir = Path(__file__).resolve().parent.parent.parent / "brain"
    pycache = brain_dir / "__pycache__"
    if pycache.is_dir():
        for f in pycache.glob("memory.cpython-*.pyc"):
            try:
                f.unlink()
            except Exception:
                pass
    # Force reimport if already loaded
    for mod in list(sys.modules.keys()):
        if "eli.brain.memory" in mod or mod == "eli.brain.memory":
            del sys.modules[mod]


_invalidate_memory_pyc()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_memory_singleton():
    try:
        import eli.brain.memory as m
        m.Memory._instance = None
    except Exception:
        pass


def _reset_sie_singleton():
    try:
        import eli.brain.self_improvement as s
        s._self_engine = None
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fresh_mem(tmp_path):
    """
    Memory instance backed by an isolated temp DB.
    Sets ELI_MEMORY_DB so PATHS.db picks it up at call-time, and
    Memory.__init__ re-initialises because the path changed.
    Resets both Memory and SIE singletons before and after.
    """
    import sqlite3

    db_path = str(tmp_path / "test_mem.sqlite3")

    _reset_sie_singleton()
    _reset_memory_singleton()

    old_env = os.environ.get("ELI_MEMORY_DB")
    os.environ["ELI_MEMORY_DB"] = db_path

    from eli.brain.memory import get_memory
    mem = get_memory()

    yield mem

    if old_env is None:
        os.environ.pop("ELI_MEMORY_DB", None)
    else:
        os.environ["ELI_MEMORY_DB"] = old_env

    _reset_sie_singleton()
    _reset_memory_singleton()


@pytest.fixture
def fresh_sie(fresh_mem):
    """
    Real SelfImprovementEngine writing to the same isolated temp DB as fresh_mem.
    SIE.log_failure/log_improvement call get_memory() at runtime, so they pick up
    the temp DB automatically via the ELI_MEMORY_DB env var set by fresh_mem.
    """
    _reset_sie_singleton()
    from eli.brain.self_improvement import SelfImprovementEngine
    engine = SelfImprovementEngine()
    yield engine
    _reset_sie_singleton()
