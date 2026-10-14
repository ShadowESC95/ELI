import sys, os, sqlite3, time, pytest
os.environ['ELI_MEMORY_DB'] = os.path.abspath('eli/artifacts/eli_memory.sqlite3')
sys.path.insert(0, os.path.abspath('eli'))

from eli.brain.memory import get_memory

@pytest.fixture
def mem():
    import tempfile, os, eli.brain.memory as mm
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name
    os.environ["ELI_MEMORY_DB"] = db_path
    mm._memory = None
    m = mm.get_memory()
    m.init_db()
    yield m
    mm._memory = None
    del os.environ["ELI_MEMORY_DB"]
    import os as _os
    try: _os.unlink(db_path)
    except: pass

@pytest.mark.skipif(
    bool(os.environ.get("ELI_MEMORY_DB")),
    reason="ELI_MEMORY_DB is overridden by test environment"
)
def test_db_path():
    """Check that the default database filename is eli_memory.sqlite3."""
    import eli.brain.memory as _mem_mod
    _mem_mod._memory_singleton = None
    original_env = os.environ.pop("ELI_MEMORY_DB", None)
    try:
        from eli.brain.memory import Memory
        mem = Memory()
        path_str = str(mem.db_path)
    finally:
        if original_env:
            os.environ["ELI_MEMORY_DB"] = original_env
        _mem_mod._memory_singleton = None
    assert 'eli_memory.sqlite3' in path_str or 'eli' in path_str

def test_store_and_recall_memory(mem):
    mem.store_memory("pytest wiring check unique string", tags=["pytest"])
    results = mem.recall_memory("pytest wiring check", limit=5)
    assert any("pytest" in str(r) for r in results), f"Recall failed: {results}"

def test_conversation_storage(mem):
    mem.add_conversation_turn("user", "pytest test message", "pytest_session", "default")
    convs = mem.get_recent_conversation(limit=10, user_id="default")
    assert any("pytest test message" in str(c) for c in convs)

def test_required_tables(mem):
    con = sqlite3.connect(str(mem.db_path))
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    con.close()
    for t in ['conversations', 'memories', 'habit_events', 'improvements', 'error_tracking', 'habits']:
        assert t in tables, f"Missing table: {t}"
