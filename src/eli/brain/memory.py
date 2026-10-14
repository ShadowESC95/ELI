# src/eli/brain/memory.py
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .paths import get_paths


# ---------------------------------------------------------------------
# DB path resolution
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class DBPaths:
    user_db: Path
    agent_db: Path


def _resolve_project_artifacts_dir() -> Path:
    # Prefer ELI_ARTIFACTS (your ~/.bashrc uses this)
    v = os.environ.get("ELI_ARTIFACTS")
    if v:
        return Path(v).expanduser().resolve()
    # Otherwise ELI's data folder (never its own code folder, which is read-only when packaged)
    from eli.brain.paths import get_paths
    return Path(get_paths().data_dir).resolve()


def resolve_db_paths() -> DBPaths:
    """
    Canonical two-DB resolution.

    Priority rules (portable + test-safe):

      1) If explicit two-DB vars are provided, honor them:
         - ELI_USER_DB / ELI_USER_DB_PATH / ELI_USER_DB_PATH
         - ELI_AGENT_DB / ELI_AGENT_DB_PATH / ELI_AGENT_DB_PATH

      2) If running under pytest (PYTEST_CURRENT_TEST is set) and ELI_MEMORY_DB
         (or ELI_MEMORY_DB_PATH) is set, collapse to a single DB. This preserves
         older tests that expect a single temporary DB file.

      3) Otherwise:
         - user defaults to <artifacts>/user.sqlite3
         - agent defaults to <artifacts>/agent.sqlite3

    NOTE:
      ELI_MEMORY_DB is treated as the *main memory db* location (often user-facing),
      but does NOT automatically override the agent DB in normal runtime.
    """
    artifacts = _resolve_project_artifacts_dir()

    # Explicit two-db overrides (new/portable)
    user_env = (
        os.environ.get("ELI_USER_DB")
        or os.environ.get("ELI_USER_DB_PATH")
        or os.environ.get("ELI_USER_DB_PATH")
        or os.environ.get("ELI_USER_DB_PATH")
    )
    agent_env = (
        os.environ.get("ELI_AGENT_DB")
        or os.environ.get("ELI_AGENT_DB_PATH")
        or os.environ.get("ELI_AGENT_DB_PATH")
        or os.environ.get("ELI_AGENT_DB_PATH")
    )

    # Test single-db override (kept for backward compatibility)
    legacy = os.environ.get("ELI_MEMORY_DB") or os.environ.get("ELI_MEMORY_DB_PATH")
    if legacy and os.environ.get("PYTEST_CURRENT_TEST"):
        both = Path(legacy).expanduser().resolve()
        return DBPaths(user_db=both, agent_db=both)

    user_default = artifacts / "user.sqlite3"
    agent_default = artifacts / "agent.sqlite3"

    user = Path(user_env or str(user_default)).expanduser().resolve()
    agent = Path(agent_env or str(agent_default)).expanduser().resolve()
    return DBPaths(user_db=user, agent_db=agent)


# ---------------------------------------------------------------------
# Memory instances (per-db singletons)
# ---------------------------------------------------------------------

_memory_singletons: Dict[str, "Memory"] = {}
_memory_lock = threading.Lock()
# Compat: conftest does `mem_mod._memory_singleton = None` to reset cache.
_memory_singleton = None

def _clear_memory_singletons():
    """Clear all cached Memory instances (call between tests)."""
    with _memory_lock:
        _memory_singletons.clear()
    # Also clear SIE singleton so it picks up the new agent memory on next use
    try:
        import eli.brain.self_improvement as _si
        _si._self_engine = None
    except Exception:
        pass

# Hook: when conftest sets _memory_singleton = None, clear the dict too.
import sys as _sys
_this_module = _sys.modules[__name__]
class _MemoryModule(type(_this_module)):
    def __setattr__(self, name, value):
        if name == "_memory_singleton" and value is None:
            _clear_memory_singletons()
        super().__setattr__(name, value)
_this_module.__class__ = _MemoryModule


def get_memory(db_path: Union[str, Path, None] = None) -> "Memory":
    """
    Get or create a Memory instance for a specific db_path.
    If db_path is None, defaults to USER DB.
    """
    paths = resolve_db_paths()
    if db_path is None:
        db_path = paths.user_db
    db_path = Path(db_path).expanduser().resolve()
    key = str(db_path)

    with _memory_lock:
        if key not in _memory_singletons:
            _memory_singletons[key] = Memory(db_path=db_path)
        return _memory_singletons[key]


def get_agent_memory(db_path: Union[str, Path, None] = None) -> "Memory":
    """
    Get or create Memory for the AGENT DB.
    """
    paths = resolve_db_paths()
    if db_path is None:
        db_path = paths.agent_db
    return get_memory(db_path=db_path)


# ---------------------------------------------------------------------
# SQLite helpers
# ---------------------------------------------------------------------

def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}


def _cols(conn: sqlite3.Connection, table: str) -> List[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _ensure_column(conn: sqlite3.Connection, table: str, col: str, ddl: str) -> None:
    cols = _cols(conn, table)
    if col not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


# ---------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------

class _MemoryMeta(type):
    """Metaclass that intercepts Memory._instance = None to clear singleton cache.

    The integration conftest does: m.Memory._instance = None
    This must trigger a full reset of the dict-based singleton cache.
    """
    def __setattr__(cls, name, value):
        if name == "_instance" and value is None:
            _clear_memory_singletons()
            return
        super().__setattr__(name, value)


class Memory(metaclass=_MemoryMeta):
    """
    SQLite-backed memory store.

    - Memory() must work with no args (tests rely on this).
    - Schema must be created + migrated automatically.
    """

    def __init__(self, db_path: Union[str, Path, None] = None):
        if db_path is None:
            db_path = resolve_db_paths().user_db
        self.db_path: Path = Path(db_path).expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_tables()

    # -----------------------------
    # compat helpers (tests call)
    # -----------------------------

    def init_db(self) -> None:
        """Compat alias (older tests call this)."""
        self._ensure_tables()

    def init_self_improvement_tables(self) -> None:
        """Compat no-op wrapper."""
        self._ensure_tables()

    # -----------------------------
    # connection
    # -----------------------------

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    # -----------------------------
    # schema
    # -----------------------------

    def _ensure_tables(self) -> None:
        conn = self._get_connection()
        try:
            # Core memory table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL,
                    timestamp REAL,
                    kind TEXT,
                    text TEXT,
                    tags TEXT,
                    source TEXT,
                    confidence REAL DEFAULT 1.0,
                    weight REAL DEFAULT 1.0
                )
            """)

            # Full-text search (FTS5)
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
                USING fts5(text, tags, content='memories', content_rowid='id')
            """)

            # Conversations (legacy + pipeline tables)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    session_id TEXT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp REAL DEFAULT (strftime('%s','now')),
                    ts REAL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversation_turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    session_id TEXT,
                    user_id TEXT,
                    role TEXT,
                    content TEXT,
                    ts REAL
                )
            """)

            # Recall log
            conn.execute("""
                CREATE TABLE IF NOT EXISTS recall_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL,
                    timestamp REAL,
                    query TEXT,
                    results_count INTEGER,
                    memory_id INTEGER
                )
            """)

            # Habit events
            conn.execute("""
                CREATE TABLE IF NOT EXISTS habit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT,
                    details TEXT,
                    timestamp REAL,
                    ts REAL
                )
            """)

            # Habit rules
            conn.execute("""
                CREATE TABLE IF NOT EXISTS habit_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    command TEXT,
                    hour INTEGER,
                    minute INTEGER,
                    days TEXT,
                    enabled INTEGER DEFAULT 1,
                    timestamp REAL,
                    ts REAL
                )
            """)

            # Habits (scheduler)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS habits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    command TEXT,
                    hour INTEGER,
                    minute INTEGER,
                    enabled INTEGER DEFAULT 1,
                    timestamp REAL,
                    ts REAL
                )
            """)

            # Corrections
            conn.execute("""
                CREATE TABLE IF NOT EXISTS corrections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original TEXT,
                    corrected TEXT,
                    timestamp REAL,
                    ts REAL
                )
            """)

            # Failures
            conn.execute("""
                CREATE TABLE IF NOT EXISTS failures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_input TEXT,
                    command TEXT,
                    error TEXT,
                    confidence REAL,
                    low_confidence INTEGER DEFAULT 0,
                    context TEXT,
                    context_json TEXT,
                    occurrence_count INTEGER DEFAULT 1,
                    timestamp REAL,
                    ts REAL
                )
            """)

            # Improvements (tests require 'area')
            conn.execute("""
                CREATE TABLE IF NOT EXISTS improvements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT,
                    area TEXT,
                    description TEXT,
                    priority INTEGER DEFAULT 1,
                    status TEXT DEFAULT 'pending',
                    timestamp REAL,
                    created_at REAL
                )
            """)

            # Error tracking (tests require error_type + details + timestamps)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS error_tracking (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    error_type TEXT,
                    details TEXT,
                    timestamp REAL,
                    occurrence_count INTEGER DEFAULT 1,
                    first_seen REAL,
                    last_seen REAL
                )
            """)

            # Observations
            conn.execute("""
                CREATE TABLE IF NOT EXISTS observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT,
                    observation TEXT,
                    content TEXT,
                    timestamp REAL DEFAULT (strftime('%s','now')),
                    ts REAL,
                    source TEXT
                )
            """)

            # Capability proposals
            conn.execute("""
                CREATE TABLE IF NOT EXISTS capability_proposals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    proposed_name TEXT,
                    capability TEXT,
                    description TEXT,
                    examples TEXT,
                    plugin_code TEXT,
                    reasoning TEXT,
                    status TEXT DEFAULT 'pending',
                    timestamp REAL
                )
            """)

            # user_patterns (used by store_app_cmd)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern_type TEXT,
                    pattern_data TEXT,
                    timestamp REAL,
                    ts REAL
                )
            """)

            conn.commit()

            # ---- Migrations / ensure columns exist on older DBs ----
            tables = _table_names(conn)

            if "memories" in tables:
                _ensure_column(conn, "memories", "ts", "ts REAL")
                _ensure_column(conn, "memories", "timestamp", "timestamp REAL")
                _ensure_column(conn, "memories", "weight", "weight REAL DEFAULT 1.0")
                _ensure_column(conn, "memories", "confidence", "confidence REAL DEFAULT 1.0")

            if "recall_log" in tables:
                _ensure_column(conn, "recall_log", "ts", "ts REAL")
                _ensure_column(conn, "recall_log", "memory_id", "memory_id INTEGER")
                _ensure_column(conn, "recall_log", "results_count", "results_count INTEGER")

            if "habit_rules" in tables:
                _ensure_column(conn, "habit_rules", "ts", "ts REAL")
                _ensure_column(conn, "habit_rules", "enabled", "enabled INTEGER DEFAULT 1")

            if "habit_events" in tables:
                _ensure_column(conn, "habit_events", "details", "details TEXT")
                _ensure_column(conn, "habit_events", "ts", "ts REAL")

            if "user_patterns" in tables:
                _ensure_column(conn, "user_patterns", "ts", "ts REAL")

            if "corrections" in tables:
                _ensure_column(conn, "corrections", "ts", "ts REAL")

            if "improvements" in tables:
                _ensure_column(conn, "improvements", "area", "area TEXT")
                _ensure_column(conn, "improvements", "status", "status TEXT")
                _ensure_column(conn, "improvements", "created_at", "created_at REAL")

            if "error_tracking" in tables:
                # Older schema in your repo used command/error
                cols = _cols(conn, "error_tracking")
                if "error_type" not in cols:
                    _ensure_column(conn, "error_tracking", "error_type", "error_type TEXT")
                if "details" not in cols:
                    _ensure_column(conn, "error_tracking", "details", "details TEXT")
                if "timestamp" not in cols:
                    _ensure_column(conn, "error_tracking", "timestamp", "timestamp REAL")
                if "occurrence_count" not in cols:
                    _ensure_column(conn, "error_tracking", "occurrence_count", "occurrence_count INTEGER DEFAULT 1")
                if "first_seen" not in cols:
                    _ensure_column(conn, "error_tracking", "first_seen", "first_seen REAL")
                if "last_seen" not in cols:
                    _ensure_column(conn, "error_tracking", "last_seen", "last_seen REAL")

            if "observations" in tables:
                _ensure_column(conn, "observations", "source", "source TEXT")

            if "conversations" in tables:
                _ensure_column(conn, "conversations", "ts", "ts REAL")

            if "conversation_turns" in tables:
                _ensure_column(conn, "conversation_turns", "ts", "ts REAL")

            conn.commit()

            # Keep FTS in sync if DB existed before FTS creation.
            # Best-effort rebuild: safe for tests + small DBs.
            try:
                conn.execute("INSERT INTO memories_fts(memories_fts) VALUES('rebuild');")
                conn.commit()
            except Exception:
                pass

        finally:
            conn.close()

    # -----------------------------------------------------------------
    # Memory CRUD
    # -----------------------------------------------------------------

    def store_memory(
        self,
        text: str,
        tags: Optional[List[str]] = None,
        source: str = "user",
        kind: str = "memory",
        confidence: float = 1.0,
    ) -> Dict[str, Any]:
        # uses conn.execute(...) (tests check for this string early)
        t = (text or "").strip()
        if not t:
            return {"ok": False, "error": "empty_text"}

        tag_blob = ",".join([x.strip() for x in (tags or []) if isinstance(x, str) and x.strip()])
        now = time.time()
        conn = self._get_connection()
        try:
            cur = conn.execute(
                "INSERT INTO memories (ts, timestamp, kind, text, tags, source, confidence, weight) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (now, now, kind, t, tag_blob, source, float(confidence), 1.0),
            )
            rowid = cur.lastrowid
            # update FTS
            try:
                conn.execute(
                    "INSERT INTO memories_fts(rowid, text, tags) VALUES (?, ?, ?)",
                    (rowid, t, tag_blob),
                )
            except Exception:
                pass
            conn.commit()
            return {"ok": True, "id": rowid}
        finally:
            conn.close()

    # Compat alias
    def add_memory(self, text: str, tags: Union[str, List[str], None] = None) -> Optional[Dict[str, Any]]:
        if isinstance(tags, str):
            tags_list = [tags]
        else:
            tags_list = tags
        return self.store_memory(text, tags=tags_list or [])

    def recall_memory(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        q = (query or "").strip()
        if not q:
            return []

        conn = self._get_connection()
        try:
            rows = []

            # Extract significant keywords (skip short stopwords)
            _stopwords = {
                "i", "me", "my", "we", "our", "you", "your", "he", "she", "it",
                "the", "a", "an", "is", "are", "was", "were", "be", "been",
                "do", "does", "did", "have", "has", "had", "will", "would",
                "can", "could", "should", "may", "might", "shall",
                "in", "on", "at", "to", "for", "of", "with", "by", "from",
                "and", "or", "but", "not", "no", "if", "so", "as", "that",
                "this", "what", "which", "who", "how", "when", "where", "why",
                "all", "any", "some", "about", "up", "out", "just", "than",
            }
            words = [
                w for w in "".join(ch if ch.isalnum() or ch == " " else " " for ch in q).lower().split()
                if len(w) >= 3 and w not in _stopwords
            ]

            # Try FTS first (with sanitised OR query)
            if words:
                try:
                    fts_query = " OR ".join(words)
                    rows = conn.execute(
                        """
                        SELECT m.id, m.ts, m.text, m.tags, m.weight
                        FROM memories_fts f
                        JOIN memories m ON m.id = f.rowid
                        WHERE memories_fts MATCH ?
                        ORDER BY m.ts DESC
                        LIMIT ?
                        """,
                        (fts_query, int(limit)),
                    ).fetchall()
                except Exception:
                    pass

            # LIKE fallback: match ANY keyword
            if not rows and words:
                clauses = " OR ".join(["(LOWER(text) LIKE ? OR LOWER(tags) LIKE ?)"] * len(words))
                params: List[Any] = []
                for w in words:
                    like = f"%{w}%"
                    params.extend([like, like])
                params.append(int(limit))
                rows = conn.execute(
                    f"""
                    SELECT id, ts, text, tags, weight
                    FROM memories
                    WHERE {clauses}
                    ORDER BY ts DESC
                    LIMIT ?
                    """,
                    params,
                ).fetchall()

            out = [{"id": r[0], "ts": r[1], "timestamp": r[1], "text": r[2], "tags": r[3], "weight": r[4]} for r in rows]

            # recall log
            now = time.time()
            conn.execute(
                "INSERT INTO recall_log (ts, timestamp, query, results_count) VALUES (?, ?, ?, ?)",
                (now, now, q, len(out)),
            )

            # weight feedback loop: bump recalled rows slightly
            try:
                for r in out:
                    conn.execute("UPDATE memories SET weight = COALESCE(weight, 1.0) + 0.1 WHERE id = ?", (r["id"],))
            except Exception:
                pass

            conn.commit()
            return out
        finally:
            conn.close()

    # Compat alias
    def search_memories(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        return self.recall_memory(query, limit=limit)

    # -----------------------------------------------------------------
    # Conversation storage / retrieval
    # -----------------------------------------------------------------

    def add_conversation_turn(
        self,
        role: str,
        content: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> int:
        # Provide safe defaults for tests that omit user_id/session_id
        session_id = session_id or "default-session"
        user_id = user_id or "default-user"
        now = time.time()
        conn = self._get_connection()
        try:
            cur = conn.execute(
                "INSERT INTO conversations (user_id, session_id, role, content, timestamp, ts) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, session_id, role, content, now, now),
            )
            # also mirror into conversation_turns for legacy code that reads it
            conn.execute(
                "INSERT INTO conversation_turns (timestamp, session_id, user_id, role, content, ts) VALUES (?, ?, ?, ?, ?, ?)",
                (now, session_id, user_id, role, content, now),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    # Compat alias (old signature store_conversation(session, role, content))
    def store_conversation(self, session_id: str, role: str, content: str, user_id: Optional[str] = None) -> int:
        return self.add_conversation_turn(role=role, content=content, session_id=session_id, user_id=user_id)

    def get_conversation_history(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieve conversation history for a given session."""
        return self.get_recent_conversation(limit=limit, session_id=session_id)

    def adjust_weight(self, memory_id: int, delta: float) -> None:
        """Adjust the weight of a memory by delta."""
        conn = self._get_connection()
        try:
            conn.execute(
                "UPDATE memories SET weight = COALESCE(weight, 1.0) + ? WHERE id = ?",
                (float(delta), int(memory_id)),
            )
            conn.commit()
        finally:
            conn.close()

    def get_recent_conversation(
        self,
        limit: int = 50,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            q = "SELECT role, content, timestamp, user_id, session_id FROM conversations WHERE 1=1"
            params: List[Any] = []
            if user_id:
                q += " AND user_id = ?"
                params.append(user_id)
            if session_id:
                q += " AND session_id = ?"
                params.append(session_id)
            q += " ORDER BY timestamp DESC LIMIT ?"
            params.append(int(limit))
            rows = conn.execute(q, params).fetchall()
            return [
                {
                    "role": r[0],
                    "content": r[1],
                    "timestamp": r[2],
                    "user_id": r[3],
                    "session_id": r[4],
                }
                for r in rows
            ]
        finally:
            conn.close()

    def search_conversations(self, query: str, user_id: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        q = (query or "").strip()
        if not q:
            return []

        # Extract significant keywords
        _stopwords = {
            "i", "me", "my", "we", "our", "you", "your", "he", "she", "it",
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "do", "does", "did", "have", "has", "had", "will", "would",
            "can", "could", "should", "may", "might", "shall",
            "in", "on", "at", "to", "for", "of", "with", "by", "from",
            "and", "or", "but", "not", "no", "if", "so", "as", "that",
            "this", "what", "which", "who", "how", "when", "where", "why",
            "all", "any", "some", "about", "up", "out", "just", "than",
        }
        words = [
            w for w in "".join(ch if ch.isalnum() or ch == " " else " " for ch in q).lower().split()
            if len(w) >= 3 and w not in _stopwords
        ]

        if not words:
            # Fall back to full-string match if no significant words extracted
            words = [q.lower()]

        conn = self._get_connection()
        try:
            clauses = " OR ".join(["LOWER(content) LIKE ?"] * len(words))
            params: List[Any] = [f"%{w}%" for w in words]
            sql = f"""
                SELECT role, content, timestamp, user_id, session_id
                FROM conversations
                WHERE ({clauses})
            """
            if user_id:
                sql += " AND user_id = ?"
                params.append(user_id)
            sql += " ORDER BY timestamp DESC LIMIT ?"
            params.append(int(limit))
            rows = conn.execute(sql, params).fetchall()
            return [
                {"role": r[0], "content": r[1], "timestamp": r[2], "user_id": r[3], "session_id": r[4]}
                for r in rows
            ]
        finally:
            conn.close()

    # -----------------------------------------------------------------
    # Habits
    # -----------------------------------------------------------------

    def log_habit_event(self, event_type: str, details: Any) -> int:
        now = time.time()
        if isinstance(details, (dict, list)):
            details_blob = json.dumps(details)
        else:
            details_blob = str(details)
        conn = self._get_connection()
        try:
            cur = conn.execute(
                "INSERT INTO habit_events (event_type, details, timestamp, ts) VALUES (?, ?, ?, ?)",
                (event_type, details_blob, now, now),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def get_habit_events(self, event_type: Optional[str] = None, days: float = 14) -> List[Dict[str, Any]]:
        window = time.time() - float(days) * 86400.0
        conn = self._get_connection()
        try:
            sql = "SELECT id, event_type, details, timestamp, ts FROM habit_events WHERE timestamp >= ?"
            params: List[Any] = [window]
            if event_type:
                sql += " AND event_type = ?"
                params.append(event_type)
            sql += " ORDER BY timestamp ASC"
            rows = conn.execute(sql, params).fetchall()
            out: List[Dict[str, Any]] = []
            for rid, et, det, ts, _ts in rows:
                parsed: Any = det
                if isinstance(det, str):
                    try:
                        parsed = json.loads(det)
                    except Exception:
                        parsed = det
                out.append({"id": rid, "event_type": et, "details": parsed, "timestamp": ts})
            return out
        finally:
            conn.close()

    def add_habit_rule(self, name: str, command: str, hour: int, minute: int, days: list = None) -> int:
        now = time.time()
        days_json = json.dumps(days) if days else None
        conn = self._get_connection()
        try:
            cur = conn.execute(
                "INSERT INTO habit_rules (name, command, hour, minute, days, enabled, timestamp, ts) VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
                (name, command, int(hour), int(minute), days_json, now, now),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def get_habit_rules(self, enabled_only: bool = True) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            sql = "SELECT id, name, command, hour, minute, days, enabled, timestamp FROM habit_rules"
            if enabled_only:
                sql += " WHERE enabled = 1"
            sql += " ORDER BY hour ASC, minute ASC"
            rows = conn.execute(sql).fetchall()
            out = []
            for r in rows:
                out.append(
                    {
                        "id": r[0],
                        "name": r[1],
                        "command": r[2],
                        "hour": r[3],
                        "minute": r[4],
                        "days": json.loads(r[5]) if r[5] else None,
                        "enabled": bool(r[6]),
                        "timestamp": r[7],
                    }
                )
            return out
        finally:
            conn.close()

    # Used by cognitive_engine learning
    def store_app_cmd(self, name: str, cmd: str, method: str = None):
        now = time.time()
        data = json.dumps({"name": name, "cmd": cmd, "method": method})
        conn = self._get_connection()
        try:
            conn.execute(
                "INSERT INTO user_patterns (pattern_type, pattern_data, timestamp, ts) VALUES (?, ?, ?, ?)",
                ("app_cmd", data, now, now),
            )
            conn.commit()
        finally:
            conn.close()

    # -----------------------------------------------------------------
    # Self-improvement helpers
    # -----------------------------------------------------------------

    def log_failure(self, user_input: str, error: str = "", confidence: float = 0.0, context: dict = None):
        now = time.time()
        ctx = context or {}
        conn = self._get_connection()
        try:
            # Try dedupe by (user_input, error)
            row = conn.execute(
                "SELECT id, occurrence_count FROM failures WHERE user_input = ? AND error = ?",
                (user_input, error),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE failures SET occurrence_count = occurrence_count + 1, timestamp = ?, ts = ? WHERE id = ?",
                    (now, now, row[0]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO failures (user_input, command, error, confidence, low_confidence, context, context_json, occurrence_count, timestamp, ts)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_input,
                        ctx.get("command", "") or user_input,
                        error,
                        float(confidence),
                        1 if float(confidence) < 0.5 else 0,
                        json.dumps(ctx) if isinstance(ctx, dict) else str(ctx),
                        json.dumps(ctx) if isinstance(ctx, dict) else None,
                        1,
                        now,
                        now,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def log_improvement(
        self,
        category: str,
        description: str,
        area: str = "runtime",
        priority: int = 1,
        status: str = "pending",
        code_before: str = "",
        code_after: str = "",
    ):
        now = time.time()
        conn = self._get_connection()
        try:
            conn.execute(
                """
                INSERT INTO improvements (category, area, description, timestamp)
                VALUES (?, ?, ?, ?)
                """,
                (category, area, description, now),
            )
            conn.commit()
        finally:
            conn.close()

    def log_correction(self, original: str, corrected: str):
        now = time.time()
        conn = self._get_connection()
        try:
            conn.execute(
                "INSERT INTO corrections (original, corrected, timestamp, ts) VALUES (?, ?, ?, ?)",
                (original, corrected, now, now),
            )
            conn.commit()
        finally:
            conn.close()

    def add_observation(self, category: str, observation: str, content: str = "", source: str = "runtime"):
        now = time.time()
        # Default content to observation text if not provided
        if not content:
            content = observation
        conn = self._get_connection()
        try:
            conn.execute(
                """
                INSERT INTO observations (category, observation, content, timestamp, ts, source)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (category, observation, content, now, now, source),
            )
            conn.commit()
        finally:
            conn.close()

    def add_capability_proposal(
        self,
        proposed_name: str,
        description: str,
        examples: List[str],
        plugin_code: str,
        capability: str = "",
        reasoning: str = "",
        status: str = "pending",
    ) -> int:
        now = time.time()
        conn = self._get_connection()
        try:
            cur = conn.execute(
                """
                INSERT INTO capability_proposals
                (proposed_name, capability, description, examples, plugin_code, reasoning, status, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposed_name,
                    capability,
                    description,
                    json.dumps(examples or []),
                    plugin_code,
                    reasoning,
                    status,
                    now,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def propose_capability(self, capability: str, reasoning: str = "", description: str = "", examples: List[str] = None, plugin_code: str = "") -> int:
        name = capability
        return self.add_capability_proposal(
            proposed_name=name,
            capability=capability,
            description=description or f"Proposed capability: {capability}",
            examples=examples or [],
            plugin_code=plugin_code or "",
            reasoning=reasoning or "",
            status="pending",
        )

    def get_pending_proposals(self, limit: int = 25) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            rows = conn.execute(
                "SELECT id, proposed_name, capability, description, examples, plugin_code, reasoning, status, timestamp "
                "FROM capability_proposals WHERE status = 'pending' ORDER BY timestamp DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
            out = []
            for r in rows:
                out.append(
                    {
                        "id": r[0],
                        "proposed_name": r[1],
                        "capability": r[2],
                        "description": r[3],
                        "examples": json.loads(r[4]) if r[4] else [],
                        "plugin_code": r[5],
                        "reasoning": r[6],
                        "status": r[7],
                        "timestamp": r[8],
                    }
                )
            return out
        finally:
            conn.close()


__all__ = [
    "DBPaths",
    "resolve_db_paths",
    "get_memory",
    "get_agent_memory",
    "Memory",
]