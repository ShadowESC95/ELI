from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import os
import json
import time
import sqlite3
import hashlib

try:
    import numpy as np
except Exception:
    np = None  # type: ignore

def _default_db() -> Path:
    # Its own file in ELI's data folder: this module's `memories` table has different columns
    # from the main memory's (brain/memory.py), so the two cannot share a database.
    from eli.brain.paths import get_paths
    return Path(get_paths().data_dir) / "memory_index.sqlite3"

# Canonical DB path (override via ELI_MEMORY_INDEX_DB, or ELI_MEMORY_DB_PATH in tests)
DB_PATH: Path = Path(
    os.environ.get("ELI_MEMORY_INDEX_DB") or os.environ.get("ELI_MEMORY_DB_PATH") or _default_db()
).expanduser().resolve()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Optional embedding support
EMBED_MODEL = os.environ.get("ELI_EMBED_MODEL", "nomic-embed-text")
from . import config as _eli_config

OLLAMA_HOST = _eli_config.ollama_base()

def _db() -> sqlite3.Connection:
    con = sqlite3.connect(str(DB_PATH), timeout=30.0)
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    con.execute("""
    CREATE TABLE IF NOT EXISTS events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts REAL NOT NULL,
        action TEXT NOT NULL,
        args_json TEXT NOT NULL
    );
    """)
    con.execute("""
    CREATE TABLE IF NOT EXISTS memories(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts REAL NOT NULL,
        timestamp REAL NOT NULL,
        text TEXT NOT NULL,
        tags TEXT,
        model TEXT,
        dim INTEGER,
        vec BLOB
    );
    """)
    return con

def log_event(action: str, args: Dict[str, Any]) -> None:
    con = _db()
    con.execute(
        "INSERT INTO events(ts, action, args_json) VALUES(?,?,?)",
        (time.time(), action, json.dumps(args, ensure_ascii=False)),
    )
    con.commit()
    con.close()


def _table_columns(con: sqlite3.Connection, table: str):
    cur = con.execute(f"PRAGMA table_info({table})")
    return {r[1] for r in cur.fetchall()}

def recall_recent(limit: int = 10, k=None) -> "Dict[str, Any]":
    """
    Return recent memories in a normalized shape for legacy + new callers.
    Supports `k` alias.
    """
    import os
    import sqlite3
    from pathlib import Path

    if k is not None:
        try:
            limit = int(k)
        except Exception:
            pass
    try:
        limit = max(1, int(limit))
    except Exception:
        limit = 10

    db_path = Path(os.environ.get("ELI_MEMORY_DB_PATH") or DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    rows_out = []
    try:
        con = sqlite3.connect(db_path.as_posix())
        cur = con.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS memory (
                id INTEGER PRIMARY KEY,
                ts TEXT DEFAULT CURRENT_TIMESTAMP,
                text TEXT,
                tags TEXT
            )
        """)
        con.commit()

        cur.execute(
            "SELECT id, ts, text, tags FROM memory ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        rows = cur.fetchall()
        con.close()

        for rid, ts, text, tags in rows:
            rows_out.append({
                "id": rid,
                "ts": ts or "",
                "text": text or "",
                "tags": tags or "",
            })

        return {
            "ok": True,
            "count": len(rows_out),
            "results": rows_out,
            "memories": rows_out,
            "items": rows_out,
        }
    except Exception as e:
        return {
            "ok": False,
            "error": f"recall_recent_failed: {e}",
            "results": [],
            "memories": [],
            "items": [],
        }


def _ollama_embed(text: str) -> Optional["np.ndarray"]:
    if np is None:
        return None
    try:
        import requests
    except Exception:
        return None

    try:
        r = requests.post(
            f"{OLLAMA_HOST}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": text or " "},
            timeout=60,
        )
        r.raise_for_status()
        j = r.json()
        emb = j.get("embedding") or (j.get("embeddings")[0] if j.get("embeddings") else None)
        if emb is None:
            return None
        v = np.asarray(emb, dtype=np.float32)
        n = float(np.linalg.norm(v)) or 1.0
        return v / n
    except Exception:
        return None

def _cheap_embed(text: str, dim: int = 256) -> "np.ndarray":
    # Deterministic hashed BoW embedding (works offline, no deps other than numpy)
    assert np is not None
    v = np.zeros((dim,), dtype=np.float32)
    for tok in (text.lower().split()):
        h = int(hashlib.sha256(tok.encode("utf-8")).hexdigest(), 16)
        v[h % dim] += 1.0
    n = float(np.linalg.norm(v)) or 1.0
    return v / n

def embed(text: str) -> Tuple[str, Optional["np.ndarray"]]:
    # If numpy missing, we still store text+tags; vector search will be disabled.
    if np is None:
        return ("none", None)
    v = _ollama_embed(text)
    if v is not None:
        return (EMBED_MODEL, v)
    return ("cheap_hash", _cheap_embed(text))

def add_memory(text: str, tags: str = "") -> Dict[str, Any]:
    # Compatibility bridge: always persist to SQLite memory table used by legacy tests
    _compat_row = None
    try:
        _compat_row = _compat_sqlite_insert_memory(text=text, tags=tags)
    except Exception:
        _compat_row = None

    txt = (text or "").strip()
    if not txt:
        return {
            "sqlite_id": (_compat_row or {}).get("id"),"ok": False, "error": "Empty text"}

    model, v = embed(txt)

    con = _db()
    now = time.time()
    if v is None:
        con.execute(
            "INSERT INTO memories(ts, timestamp, text, tags, model, dim, vec) VALUES(?,?,?,?,?,?,?)",
            (now, now, txt, tags, model, 0, None),
        )
    else:
        con.execute(
            "INSERT INTO memories(ts, timestamp, text, tags, model, dim, vec) VALUES(?,?,?,?,?,?,?)",
            (now, now, txt, tags, model, int(v.shape[0]), v.tobytes()),
        )
    con.commit()
    mid = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    con.close()
    return {"ok": True, "id": int(mid), "model": model, "dim": int(v.shape[0]) if v is not None else 0}

def _fetch_vectors(con: sqlite3.Connection) -> List[Tuple[int, float, str, str, str, int, Optional[bytes]]]:
    cur = con.execute(
        "SELECT id, ts, text, COALESCE(tags,''), COALESCE(model,''), COALESCE(dim,0), vec FROM memories"
    )
    return list(cur.fetchall())

def search_memory(q: str, k: int = 5) -> Dict[str, Any]:
    qq = (q or "").strip()
    if not qq:
        return {"ok": False, "error": "Empty query"}

    # If numpy missing, do a basic LIKE search fallback.
    if np is None:
        con = _db()
        cur = con.execute(
            "SELECT id, ts, text, COALESCE(tags,'') FROM memories WHERE text LIKE ? ORDER BY id DESC LIMIT ?",
            (f"%{qq}%", int(k)),
        )
        rows = [{"score": None, "id": rid, "ts": ts, "text": text, "tags": tags} for (rid, ts, text, tags) in cur.fetchall()]
        con.close()
        return {"ok": True, "query": qq, "model": "like_fallback", "results": rows, "count": len(rows)}

    model, qv = embed(qq)
    if qv is None:
        return {"ok": False, "error": "Embedding unavailable"}

    con = _db()
    rows = _fetch_vectors(con)
    con.close()

    scored: List[Tuple[float, int, float, str, str]] = []
    for (mid, ts, text, tags, m, dim, blob) in rows:
        if not blob or dim <= 0:
            continue
        v = np.frombuffer(blob, dtype=np.float32, count=dim)
        if v.size != qv.size:
            continue
        score = float(np.dot(qv, v))
        scored.append((score, int(mid), float(ts), text, tags))

    scored.sort(reverse=True, key=lambda x: x[0])
    top = scored[:max(1, int(k))]
    return {
        "ok": True,
        "query": qq,
        "model": model,
        "results": [{"score": s, "id": mid, "ts": ts, "text": text, "tags": tags} for (s, mid, ts, text, tags) in top],
        "count": len(top),
        "db": str(DB_PATH),
    }

# ============================================================
# MKV HOTFIX: robust recall_recent() implementation
# - Auto-detects table + columns
# - Returns {"ok": True, "results": [...], "count": N, "db": DB_PATH}
# - Never throws on schema mismatches
# ============================================================

def recall_recent(limit: int = 10) -> Dict[str, Any]:
    con = _db()
    rows = []
    try:
        cols = _table_columns(con, "events")
        if {"ts", "action", "args_json"}.issubset(cols):
            cur = con.execute(
                "SELECT ts, action, args_json FROM events ORDER BY id DESC LIMIT ?",
                (int(limit),),
            )
            rows = [
                {"ts": r[0], "action": r[1], "args": (json.loads(r[2]) if r[2] else {})}
                for r in cur.fetchall()
            ]
        elif {"ts", "type", "payload"}.issubset(cols):
            cur = con.execute(
                "SELECT ts, type, payload FROM events ORDER BY id DESC LIMIT ?",
                (int(limit),),
            )
            rows = [
                {"ts": r[0], "action": r[1], "args": (json.loads(r[2]) if r[2] else {})}
                for r in cur.fetchall()
            ]
        else:
            # last-resort legacy table
            cur = con.execute(
                "SELECT ts, action, args_json FROM events_old_mkv ORDER BY id DESC LIMIT ?",
                (int(limit),),
            )
            rows = [
                {"ts": r[0], "action": r[1], "args": (json.loads(r[2]) if r[2] else {})}
                for r in cur.fetchall()
            ]
    finally:
        con.close()

    return {"ok": True, "db": str(DB_PATH), "events": rows}


# === ELI_COMPAT_RECALL_RECENT_K_WRAPPER ===
# Force compatibility with callers using recall_recent(k=...)
try:
    _eli_recall_recent_original = recall_recent
except Exception:
    _eli_recall_recent_original = None

def recall_recent(limit: int = 10, k=None):
    if k is not None:
        limit = k
    try:
        limit = int(limit)
    except Exception:
        limit = 10

    if _eli_recall_recent_original is None:
        # Safe fallback shape
        return {"items": []}

    # Try positional first (works for old and new signatures)
    try:
        return _eli_recall_recent_original(limit)
    except TypeError:
        pass

    # Try keyword variants
    for kw in ("limit", "k"):
        try:
            return _eli_recall_recent_original(**{kw: limit})
        except TypeError:
            continue

    # Last resort
    return _eli_recall_recent_original(limit)


def recall_recent(limit: int = 10, k=None) -> "Dict[str, Any]":
    """
    Return recent memories in a normalized shape for legacy + new callers.
    Supports `k` alias used by tests.
    """
    import os
    import sqlite3
    from pathlib import Path

    if k is not None:
        try:
            limit = int(k)
        except Exception:
            pass
    try:
        limit = max(1, int(limit))
    except Exception:
        limit = 10

    db_path = Path(os.environ.get("ELI_MEMORY_DB_PATH") or DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    rows_out = []
    try:
        con = sqlite3.connect(db_path.as_posix())
        cur = con.cursor()

        # Ensure minimal schema exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS memory (
                id INTEGER PRIMARY KEY,
                ts TEXT DEFAULT CURRENT_TIMESTAMP,
                text TEXT,
                tags TEXT
            )
        """)
        con.commit()

        # Prefer most recent first
        cur.execute(
            "SELECT id, ts, text, tags FROM memory ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        rows = cur.fetchall()
        con.close()

        for r in rows:
            rid, ts, text, tags = r
            rows_out.append({
                "id": rid,
                "ts": ts or "",
                "text": text or "",
                "tags": tags or ""
            })

        return {
            "ok": True,
            "count": len(rows_out),
            "results": rows_out,
            "memories": rows_out,
            "items": rows_out,
        }
    except Exception as e:
        return {
            "ok": False,
            "error": f"recall_recent_failed: {e}",
            "results": [],
            "memories": [],
            "items": [],
        }



def _compat_sqlite_insert_memory(text: str, tags: str = "") -> dict:
    """
    Always insert into SQLite `memory` table for legacy compatibility tests.
    Returns {'ok': bool, 'id': int|None, ...}
    """
    import os
    import sqlite3
    from pathlib import Path

    db_path = Path(os.environ.get("ELI_MEMORY_DB_PATH") or DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path.as_posix())
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS memory (
            id INTEGER PRIMARY KEY,
            ts TEXT DEFAULT CURRENT_TIMESTAMP,
            text TEXT,
            tags TEXT
        )
    """)
    cur.execute("INSERT INTO memory(text, tags) VALUES(?, ?)", (text or "", tags or ""))
    row_id = cur.lastrowid
    con.commit()
    con.close()
    return {"ok": True, "id": row_id}
