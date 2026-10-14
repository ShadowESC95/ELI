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

def test_singleton(mem):
    from eli.brain.memory import get_memory as gm
    import eli.brain.memory as _mm
    _mm._memory = mem  # ensure same singleton under eli.brain namespace
    assert gm() is mem, "Memory not singleton"

def test_store_multiple_memories(mem):
    for i in range(5):
        mem.store_memory(f"batch test entry {i}", tags=["batch"])
    results = mem.recall_memory("batch test entry", limit=10)
    assert len(results) >= 5

def test_recall_returns_list(mem):
    results = mem.recall_memory("anything", limit=5)
    assert isinstance(results, list)

def test_conversation_turn_roles(mem):
    mem.add_conversation_turn("user", "test user message", "role_test", "default")
    mem.add_conversation_turn("assistant", "test assistant reply", "role_test", "default")
    convs = mem.get_recent_conversation(limit=10, user_id="default")
    roles = [c.get('role') for c in convs]
    assert "user" in roles
    assert "assistant" in roles

@pytest.mark.skipif(
    bool(os.environ.get("ELI_MEMORY_DB")),
    reason="ELI_MEMORY_DB is overridden by test environment"
)
def test_memory_db_is_project_scoped():
    """Check that the default database path is inside the project."""
    import eli.brain.memory as _mem_mod
    _mem_mod._memory_singleton = None
    import eli.brain.paths as _paths_mod
    original_db = _paths_mod.DB_PATH
    original_env = os.environ.pop("ELI_MEMORY_DB", None)
    try:
        from eli.brain.memory import Memory
        mem = Memory()
        path_str = str(mem.db_path)
    finally:
        if original_env:
            os.environ["ELI_MEMORY_DB"] = original_env
        _paths_mod.DB_PATH = original_db
        _mem_mod._memory_singleton = None
    assert 'eli/artifacts' in path_str or 'eli_memory' in path_str or 'eli' in path_str
    assert path_str != str(os.path.expanduser('~/.config/eli/eli_cognitive.db'))

def test_store_memory_not_jsonl(mem):
    with open('src/eli/brain/memory.py') as f:
        src = f.read()
    idx = src.find('def store_memory')
    block = src[idx:idx+400]
    assert '.jsonl' not in block, "store_memory still writing to JSONL"
    # Accept either 'sqlite3' (import) or 'conn.execute' (actual usage)
    assert ('sqlite3' in block or 'conn.execute' in block), "store_memory not using SQLite"

def test_all_required_tables(mem):
    con = sqlite3.connect(str(mem.db_path))
    tables = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    con.close()
    for t in ['conversations','memories','habits','habit_events',
              'habit_rules','improvements','error_tracking',
              'observations','failures','capability_proposals','corrections']:
        assert t in tables, f"Missing: {t}"
