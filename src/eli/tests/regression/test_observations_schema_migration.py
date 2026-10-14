import sqlite3

def test_observations_schema_adds_source(tmp_path):
    db = tmp_path / "eli_memory.sqlite3"
    conn = sqlite3.connect(db)
    try:
        conn.execute("CREATE TABLE observations (id INTEGER PRIMARY KEY, ts REAL, kind TEXT, content TEXT)")
        conn.commit()
    finally:
        conn.close()

    # Adjust import to your actual module path
    from eli.proactive.proactive_daemon import _ensure_observations_schema
    _ensure_observations_schema(db)

    conn = sqlite3.connect(db)
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(observations)").fetchall()]
        assert "source" in cols
    finally:
        conn.close()
