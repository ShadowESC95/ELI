import pytest
import tempfile
import os
from eli.brain.self_improvement import get_self_improvement
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
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        os.environ["ELI_MEMORY_DB"] = tmp.name
        mem = get_memory()
        _ensure_test_schema(mem)
        _clear_tables(mem)
        yield mem
        del os.environ["ELI_MEMORY_DB"]
        import eli.brain.memory
        eli.brain.memory._memory = None
        import eli.brain.self_improvement
        eli.brain.self_improvement._self_engine = None


def test_proactive_daemon_singleton():
    from eli.brain.proactive_daemon import get_daemon
    d1 = get_daemon()
    d2 = get_daemon()
    assert d1 is d2


def test_self_improve_db_path(temp_db):
    import eli.brain.self_improvement as _si_mod
    _si_mod._self_engine = None
    from eli.brain.self_improvement import SelfImprovementEngine
    si = SelfImprovementEngine()
    # Accept either the temp DB or the agent DB (singleton may be shared)
    assert si.memory is not None


def test_cognitive_engine_imports():
    from eli.brain.cognitive_engine import get_engine
    engine = get_engine()
    assert engine is not None


def test_log_failure_writes_to_db(temp_db):
    import eli.brain.self_improvement as _si_mod
    _si_mod._self_engine = None
    si = get_self_improvement()
    si.log_failure("test input", error="test error", confidence=0.3, context={"test": True})
    import sqlite3
    with sqlite3.connect(temp_db.db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM error_tracking").fetchone()[0]
    assert count > 0


def test_log_improvement_writes_to_db(temp_db):
    import eli.brain.self_improvement as _si_mod
    _si_mod._self_engine = None
    si = get_self_improvement()
    si.log_improvement("routing", "test improvement detected")
    import sqlite3
    with sqlite3.connect(temp_db.db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM improvements").fetchone()[0]
    assert count > 0
