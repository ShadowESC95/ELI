def status():
    return {"ok": True, "module": "identity_guard", "mode": "stub"}

# Lock management functions
import json
from pathlib import Path

def _get_lock_path():
    """Get the path to the lock file."""
    lock_dir = Path.home() / ".local" / "share" / "eli"
    lock_dir.mkdir(parents=True, exist_ok=True)
    return lock_dir / "persona_lock.json"

def get_lock_state():
    """Get the current persona lock state."""
    lock_path = _get_lock_path()
    if not lock_path.exists():
        return {"locked": False, "expected_model": None}
    
    try:
        with open(lock_path, 'r') as f:
            return json.load(f)
    except Exception:
        return {"locked": False, "expected_model": None, "error": "Failed to read lock"}

def clear_lock():
    """Clear the persona lock."""
    lock_path = _get_lock_path()
    if lock_path.exists():
        lock_path.unlink()
        print(f"✅ Lock file removed: {lock_path}")
    else:
        print("ℹ️ No lock file found")
    
    # Also try to clear any in-memory state
    try:
        from eli.brain.state import get_state
        state = get_state()
        if hasattr(state, 'locked_model'):
            state.locked_model = None
        if hasattr(state, 'persona_lock'):
            state.persona_lock = None
    except Exception:
        pass
    
    return True

def set_lock(expected_model: str):
    """Set a persona lock."""
    lock_path = _get_lock_path()
    lock_data = {
        "locked": True,
        "expected_model": expected_model,
        "timestamp": __import__('time').time()
    }
    with open(lock_path, 'w') as f:
        json.dump(lock_data, f, indent=2)
    return lock_data

__all__ = ['get_lock_state', 'clear_lock', 'set_lock']
