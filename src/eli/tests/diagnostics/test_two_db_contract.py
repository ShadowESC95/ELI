from pathlib import Path
import os
import sqlite3

def _tables(db_path: Path):
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    return [r[0] for r in rows]

def test_two_db_paths_are_distinct(tmp_path, monkeypatch):
    user_db = tmp_path / "user.sqlite3"
    agent_db = tmp_path / "agent.sqlite3"

    monkeypatch.setenv("ELI_USER_DB_PATH", str(user_db))
    monkeypatch.setenv("ELI_AGENT_DB_PATH", str(agent_db))

    from eli.brain.stores import get_stores
    stores = get_stores()

    assert Path(stores.user.db_path) == user_db
    assert Path(stores.agent.db_path) == agent_db
    assert Path(stores.user.db_path) != Path(stores.agent.db_path)

def test_writes_go_to_correct_db(tmp_path, monkeypatch):
    user_db = tmp_path / "user.sqlite3"
    agent_db = tmp_path / "agent.sqlite3"

    monkeypatch.setenv("ELI_USER_DB_PATH", str(user_db))
    monkeypatch.setenv("ELI_AGENT_DB_PATH", str(agent_db))

    from eli.brain.stores import get_stores
    stores = get_stores()

    # User DB: store_memory
    stores.user.store_memory("User likes bananas", tags=["pref"])

    # Agent DB: log_failure (or any internal table write)
    stores.agent.log_failure("internal test", error="X", confidence=0.1, context={"k":"v"})

    user_tables = _tables(user_db)
    agent_tables = _tables(agent_db)

    assert "memories" in user_tables
    assert "failures" in agent_tables

    # Ensure the agent failure did not land in user DB
    assert "failures" not in user_tables or True  # allow shared schema, but check content later

    # Content check:
    with sqlite3.connect(str(user_db)) as conn:
        failures = conn.execute("SELECT COUNT(*) FROM failures").fetchone()[0] if "failures" in user_tables else 0
    assert failures == 0
