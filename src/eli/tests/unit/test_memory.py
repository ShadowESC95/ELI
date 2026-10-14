import pytest
import tempfile
import os
from eli.brain.memory import get_memory


def _ensure_test_schema(mem):
    """Add missing columns to test database (idempotent)."""
    import sqlite3
    with sqlite3.connect(mem.db_path) as conn:
        alterations = [
            "ALTER TABLE memories ADD COLUMN weight REAL DEFAULT 1.0",
            "ALTER TABLE improvements ADD COLUMN priority INTEGER DEFAULT 2",
            "ALTER TABLE improvements ADD COLUMN created_at REAL",
            "ALTER TABLE improvements ADD COLUMN category TEXT",
            "ALTER TABLE improvements ADD COLUMN description TEXT",
            "ALTER TABLE improvements ADD COLUMN status TEXT DEFAULT 'pending'",
            "ALTER TABLE habits ADD COLUMN hour INTEGER",
            "ALTER TABLE habits ADD COLUMN minute INTEGER",
            "ALTER TABLE habit_rules ADD COLUMN hour INTEGER",
            "ALTER TABLE habit_rules ADD COLUMN minute INTEGER",
            "ALTER TABLE error_tracking ADD COLUMN occurrence_count INTEGER DEFAULT 1",
            "ALTER TABLE error_tracking ADD COLUMN first_seen REAL",
            "ALTER TABLE error_tracking ADD COLUMN last_seen REAL",
            "ALTER TABLE error_tracking ADD COLUMN resolved INTEGER DEFAULT 0",
            "ALTER TABLE error_tracking ADD COLUMN error_type TEXT",
            "ALTER TABLE error_tracking ADD COLUMN error_message TEXT",
            "ALTER TABLE error_tracking ADD COLUMN context TEXT",
        ]
        for sql in alterations:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError:
                pass
        conn.commit()


def _clear_tables(mem):
    """Delete all records from test tables to ensure isolation."""
    import sqlite3
    with sqlite3.connect(mem.db_path) as conn:
        tables = [
            'memories', 'conversations', 'habit_events', 'improvements',
            'error_tracking', 'failures', 'observations', 'corrections',
            'capability_proposals', 'habits', 'habit_rules', 'user_patterns',
            'recall_log',
        ]
        for table in tables:
            try:
                conn.execute(f"DELETE FROM {table}")
            except sqlite3.OperationalError:
                pass
        conn.commit()


@pytest.fixture
def temp_memory():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        os.environ["ELI_MEMORY_DB"] = tmp.name
        from eli.brain.memory import get_memory
        mem = get_memory()
        _ensure_test_schema(mem)
        _clear_tables(mem)
        yield mem
        del os.environ["ELI_MEMORY_DB"]
        import eli.brain.memory
        eli.brain.memory._memory = None


def test_store_and_recall(temp_memory):
    mem = temp_memory
    mem.store_memory("test data", tags=["unit", "test"])
    results = mem.recall_memory("test", limit=10)
    assert len(results) >= 1
    assert results[0]["text"] == "test data"
    assert "unit" in results[0]["tags"]


def test_conversation_turns(temp_memory):
    mem = temp_memory
    mem.add_conversation_turn("user", "hello", "sess1", "user1")
    mem.add_conversation_turn("assistant", "hi", "sess1", "user1")
    recent = mem.get_recent_conversation(limit=10, user_id="user1")
    assert len(recent) == 2
    assert recent[-1]["role"] == "user"
    assert recent[-1]["content"] == "hello"


def test_habit_events(temp_memory):
    mem = temp_memory
    mem.log_habit_event("app_launch", {"app": "spotify"})
    events = mem.get_habit_events(event_type="app_launch", days=1)
    assert len(events) == 1
    assert events[0]["details"]["app"] == "spotify"


def test_self_improvement_tables(temp_memory):
    from eli.brain.self_improvement import SelfImprovementEngine
    mem = temp_memory
    si = SelfImprovementEngine()
    si.log_failure("test input", error="fail", context={"foo": "bar"})
    si.log_improvement("test", "improve something")
    import sqlite3
    with sqlite3.connect(mem.db_path) as conn:
        err_count = conn.execute("SELECT COUNT(*) FROM error_tracking").fetchone()[0]
        imp_count = conn.execute("SELECT COUNT(*) FROM improvements").fetchone()[0]
    assert err_count > 0
    assert imp_count > 0
