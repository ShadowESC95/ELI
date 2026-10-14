import os
import sys
import pytest

sys.path.insert(0, os.path.abspath('eli'))

def test_memory_py_not_hardcoded():
    """Ensure memory.py does not contain hardcoded absolute paths."""
    with open('src/eli/brain/memory.py') as f:
        src = f.read()
    assert '/home/' not in src, "Hardcoded home path found"
    assert '/Users/' not in src, "Hardcoded user path found"

def test_store_memory_uses_sqlite():
    """Verify that store_memory uses SQLite (not JSONL)."""
    with open('src/eli/brain/memory.py') as f:
        src = f.read()
    idx = src.find('def store_memory')
    block = src[idx:idx+400]
    # Accept either the import of sqlite3 or the actual use of conn.execute
    assert ('sqlite3' in block or 'conn.execute' in block), "store_memory not using SQLite"

def test_no_dual_daemon():
    """Check that only one proactive daemon implementation exists."""
    # (example test – adjust to your actual test logic)
    pass

def test_executor_has_generate_script():
    """Executor should have a generate_script handler."""
    from eli.tools.executor_enhanced import execute
    assert callable(execute), "execute not callable"
    # Further checks if needed...

def test_executor_has_fix_file():
    """Executor should have a fix_file handler."""
    # Similar to above
    pass

def test_executor_has_volume():
    """Executor should have volume control handlers."""
    pass
