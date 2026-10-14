import time
import tempfile
import pytest
import os
from eli.brain.memory import get_memory

def _ensure_test_schema(mem):
    """Add missing columns to test database (idempotent)."""
    import sqlite3
    with sqlite3.connect(mem.db_path) as conn:
        try:
            conn.execute("ALTER TABLE memories ADD COLUMN weight REAL DEFAULT 1.0")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE improvements ADD COLUMN priority INTEGER DEFAULT 2")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE habits ADD COLUMN hour INTEGER")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE habits ADD COLUMN minute INTEGER")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE error_tracking ADD COLUMN occurrence_count INTEGER DEFAULT 1")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE improvements ADD COLUMN created_at REAL")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE error_tracking ADD COLUMN first_seen REAL")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE error_tracking ADD COLUMN last_seen REAL")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE error_tracking ADD COLUMN resolved INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        conn.commit()

def _clear_tables(mem):
    """Delete all records from test tables to ensure isolation."""
    import sqlite3
    with sqlite3.connect(mem.db_path) as conn:
        tables = ['memories', 'conversations', 'habit_events', 'improvements',
                  'error_tracking', 'failures', 'observations', 'corrections',
                  'capability_proposals', 'habits', 'habit_rules', 'user_patterns',
                  'recall_log']
        for table in tables:
            try:
                conn.execute(f"DELETE FROM {table}")
            except sqlite3.OperationalError:
                pass  # table may not exist
        conn.commit()

@pytest.fixture
def mem():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        os.environ["ELI_MEMORY_DB"] = tmp.name
        mem = get_memory()
        _ensure_test_schema(mem)
        _clear_tables(mem)
        yield mem
        del os.environ["ELI_MEMORY_DB"]
        import eli.brain.memory
        eli.brain.memory._memory = None

def test_memory_write_speed(mem):
    start = time.time()
    for i in range(100):
        mem.store_memory(f"bench write test {i} - {time.time()}", tags=["bench"])
    elapsed = time.time() - start
    assert elapsed < 2.0

def test_memory_recall_speed(mem):
    for i in range(50):
        mem.store_memory(f"recall test {i} - {time.time()}", tags=["bench"])
    start = time.time()
    results = mem.recall_memory("recall test", limit=20)
    elapsed = time.time() - start
    assert elapsed < 1.0
    assert len(results) >= 20

def test_db_size_reasonable(mem):
    for i in range(50):
        mem.store_memory(f"size test {i}", tags=["bench"])
    size = mem.db_path.stat().st_size
    assert size < 1024 * 1024

def test_conversation_count(mem):
    for i in range(10):
        mem.add_conversation_turn("user", f"message {i}", "sess1", "user1")
    recent = mem.get_recent_conversation(limit=100, user_id="user1")
    assert len(recent) == 10
