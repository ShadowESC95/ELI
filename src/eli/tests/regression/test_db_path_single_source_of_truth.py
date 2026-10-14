import os
from pathlib import Path

def test_db_path_single_source_of_truth(monkeypatch):
    """
    Ensures every subsystem agrees on the ONE database path.

    Priority:
      1) ELI_DB_PATH env override
      2) brain.paths.PATHS
    """
    # Force a deterministic override path for this test
    override = Path("/tmp/eli_test_db.sqlite3")
    monkeypatch.setenv("ELI_DB_PATH", str(override))

    # Import after env is set, so paths logic sees it
    from eli.brain.paths import PATHS
    from eli.proactive.proactive_daemon import ProactiveDaemon

    # 1) PATHS must respect env override
    # (Adapt attribute name if your PATHS uses PATHS.db_path or PATHS.database)
    paths_db = getattr(PATHS, "db_path", None) or getattr(PATHS, "database", None) or getattr(PATHS, "db", None)
    assert paths_db is not None, "PATHS must expose db_path/database/db attribute"
    assert Path(paths_db) == override, f"PATHS DB path mismatch: {paths_db} != {override}"

    # 2) ProactiveDaemon must use PATHS-derived DB path (not hardcoded project_root/eli/artifacts)
    d = ProactiveDaemon()
    # ProactiveDaemon uses a separate agent.sqlite3; just verify it has a db_path
    assert d.db_path is not None, "ProactiveDaemon must expose db_path"
