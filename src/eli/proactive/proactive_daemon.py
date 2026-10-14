# src/eli/proactive/proactive_daemon.py
"""
Compatibility wrapper.

Canonical implementation lives in:
  eli.brain.proactive_daemon

This module exists because older code/tests import:
  eli.proactive.proactive_daemon
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Union

# Re-export canonical daemon/singleton
from eli.brain.proactive_daemon import ProactiveDaemon, get_daemon, start_daemon  # noqa: F401


def _ensure_observations_schema(conn_or_path: Union[sqlite3.Connection, str, Path]) -> None:
    """
    Ensure observations table has expected columns.

    Regression tests call this with a PATH (not a connection), so accept both.
    Also ensures 'source' column exists.
    """
    if isinstance(conn_or_path, (str, Path)):
        db = Path(conn_or_path).expanduser().resolve()
        with sqlite3.connect(str(db)) as conn:
            _ensure_observations_schema(conn)
        return

    conn: sqlite3.Connection = conn_or_path
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            observation TEXT,
            content TEXT,
            timestamp REAL DEFAULT (strftime('%s','now')),
            ts REAL,
            source TEXT
        )
        """
    )
    cols = [r[1] for r in conn.execute("PRAGMA table_info(observations)").fetchall()]
    if "category" not in cols:
        conn.execute("ALTER TABLE observations ADD COLUMN category TEXT")
    if "observation" not in cols:
        conn.execute("ALTER TABLE observations ADD COLUMN observation TEXT")
    if "content" not in cols:
        conn.execute("ALTER TABLE observations ADD COLUMN content TEXT")
    if "timestamp" not in cols:
        conn.execute("ALTER TABLE observations ADD COLUMN timestamp REAL")
    if "ts" not in cols:
        conn.execute("ALTER TABLE observations ADD COLUMN ts REAL")
    if "source" not in cols:
        conn.execute("ALTER TABLE observations ADD COLUMN source TEXT")
    conn.commit()


__all__ = ["ProactiveDaemon", "get_daemon", "start_daemon", "_ensure_observations_schema"]
