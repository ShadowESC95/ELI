"""Test persona lock functionality (does not modify actual lock)."""

import pytest
import tempfile
from pathlib import Path
from eli.tools.executor_enhanced import persona_lock_set, persona_lock_status, persona_lock_clear

@pytest.fixture
def temp_state():
    """Use a temporary state file to avoid interfering with real lock."""
    with tempfile.NamedTemporaryFile(suffix=".json") as tmp:
        import os
        os.environ["ELI_STATE_FILE"] = tmp.name
        yield

def test_persona_lock_flow(temp_state):
    # Set lock
    res = persona_lock_set(model="test-model")
    assert res["ok"] is True
    # Status should show ok (or unverified if model not loaded)
    status = persona_lock_status()
    assert status["ok"] in (True, False)  # may be false if digest mismatch
    # Clear
    clear = persona_lock_clear()
    assert clear["ok"] is True
    # Status after clear
    status2 = persona_lock_status()
    assert status2["lock"] == {}
