from __future__ import annotations

# --- Memory bridge: route through canonical Memory class (not memory_db) ---
# memory_db has a different schema (model/dim/vec columns) than Memory (kind/source/confidence/weight).
# Using Memory directly avoids the "no such column: model" crash.

def _get_canonical_memory():
    """Lazy import to avoid circular import."""
    from eli.brain.memory import get_memory
    return get_memory()

def add_memory(text, tags=""):
    """Store via canonical Memory.store_memory()."""
    try:
        mem = _get_canonical_memory()
        tag_list = [t.strip() for t in str(tags).split(",") if t.strip()] if tags else []
        return mem.store_memory(text, tags=tag_list)
    except Exception as e:
        return {"ok": False, "error": str(e)}

def search_memory(query="", k=5, **kwargs):
    """Search via canonical Memory.recall_memory()."""
    if not (query or "").strip():
        return {"ok": False, "error": "empty_query", "results": [], "count": 0}
    try:
        mem = _get_canonical_memory()
        results = mem.recall_memory(query, limit=k)
        return {"ok": True, "results": results, "count": len(results)}
    except Exception as e:
        return {"ok": False, "error": str(e), "results": []}

# --- Compatibility shim: some older code expects search_memory_compat() ---
def search_memory_compat(query: str = "", limit: int = 10, q: str = "", k: int = 0, db_path=None):
    """Back-compat wrapper around Memory.recall_memory()."""
    qq = (q or query or "").strip()
    kk = int(k or limit or 10)
    return search_memory(query=qq, k=kk)

# eli_tools/executor_enhanced.py


# === CONVERSATION LOGGING (append-only) ===
def _repo_root():
    try:
        from pathlib import Path
        return Path(__file__).resolve().parents[1]  # repo_root/eli_tools/executor_enhancedMKII.py
    except Exception:
        return None

def _convlog_path():
    try:
        from pathlib import Path
        from datetime import datetime
        root = _repo_root()
        if root is None:
            return None
        d = Path(root) / "artifacts" / "conversations"
        d.mkdir(parents=True, exist_ok=True)
        fn = datetime.utcnow().strftime("%Y%m%d") + ".jsonl"
        return d / fn
    except Exception:
        return None

def _convlog_append(role: str, text: str, meta: dict | None = None) -> None:
    try:
        import json
        import time
        from datetime import datetime

        path = _convlog_path()
        if path is None:
            return

        rec = {
            "ts_iso": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "ts_unix": float(time.time()),
            "role": str(role),
            "text": str(text),
            "meta": meta or {},
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        return
# === END CONVERSATION LOGGING ===

# === MEMORY ===

def _get_memory_path():
    # Legacy helper kept for compatibility, but point it at the canonical memory DB.
    try:
        from eli.brain.paths import get_paths
        return Path(get_paths().memory_db)
    except Exception:
        default = str(Path.home() / ".eli_memory.sqlite3")
        return Path(os.environ.get("ELI_MEMORY_FILE", default))

def _sqlite_init(conn):
    conn.executescript("""
    PRAGMA journal_mode=WAL;
    PRAGMA synchronous=NORMAL;

    CREATE TABLE IF NOT EXISTS memories (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts TEXT NOT NULL,
      kind TEXT NOT NULL DEFAULT 'note',
      text TEXT NOT NULL,
      tags TEXT DEFAULT '',
      source TEXT DEFAULT 'chat',
      confidence REAL DEFAULT 0.7
    );

    CREATE INDEX IF NOT EXISTS idx_memories_ts   ON memories(ts);
    CREATE INDEX IF NOT EXISTS idx_memories_kind ON memories(kind);
    

    -- === EVENTS (append-only run/event log) ===
    CREATE TABLE IF NOT EXISTS events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts TEXT NOT NULL,
      type TEXT NOT NULL DEFAULT 'event',
      text TEXT NOT NULL,
      meta TEXT DEFAULT '',
      source TEXT DEFAULT 'system',
      confidence REAL DEFAULT 0.7
    );

    CREATE INDEX IF NOT EXISTS idx_events_ts   ON events(ts);
    CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);
""")
    conn.commit()

def memory_store(text, tags=None, kind="note", source="chat", confidence=0.7, ts=None):
    """Store a memory. Uses JSONL by default, SQLite if ELI_MEMORY_FILE ends with .sqlite3/.db/.sqlite"""
    mem_path = _get_memory_path()
    tags = tags or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]

    if ts is None:
        ts = time.time()

    if mem_path.suffix.lower() in (".sqlite3", ".db", ".sqlite"):
        mem_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(mem_path))
        try:
            _sqlite_init(conn)
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO memories(ts,kind,text,tags,source,confidence) VALUES (?,?,?,?,?,?)",
                (str(ts), str(kind), str(text), ",".join(tags), str(source), float(confidence)),
            )
            conn.commit()
            return {"ok": True, "id": cur.lastrowid, "path": str(mem_path)}
        finally:
            conn.close()
    else:
        mem_path.parent.mkdir(parents=True, exist_ok=True)
        rec = {"ts": ts, "text": str(text), "tags": tags, "kind": str(kind), "source": str(source), "confidence": float(confidence)}
        with open(mem_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return {"ok": True, "path": str(mem_path)}

def memory_recall(query, limit=20):
    """Recall memories matching query."""
    mem_path = _get_memory_path()
    limit = int(limit) if limit is not None else 20

    if mem_path.suffix.lower() in (".sqlite3", ".db", ".sqlite"):
        if not mem_path.exists():
            return {"ok": True, "results": [], "path": str(mem_path)}
        conn = sqlite3.connect(str(mem_path))
        try:
            _sqlite_init(conn)
            q = f"%{query}%"
            cur = conn.cursor()
            cur.execute(
                "SELECT id, ts, kind, text, tags, source, confidence FROM memories WHERE text LIKE ? OR tags LIKE ? ORDER BY id DESC LIMIT ?",
                (q, q, limit),
            )
            rows = cur.fetchall()
            results = [
                {"id": r[0], "ts": r[1], "kind": r[2], "text": r[3], "tags": r[4], "source": r[5], "confidence": r[6]}
                for r in rows
            ]
            return {"ok": True, "results": results, "path": str(mem_path)}
        finally:
            conn.close()
    else:
        if not mem_path.exists():
            return {"ok": True, "results": [], "path": str(mem_path)}
        results = []
        q = str(query).lower()
        with open(mem_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                txt = str(obj.get("text", "")).lower()
                tags = obj.get("tags", [])
                tags_s = ",".join(tags).lower() if isinstance(tags, list) else str(tags).lower()
                if q in txt or q in tags_s:
                    results.append(obj)
        # newest last in JSONL; return last N newest
        return {"ok": True, "results": results[-limit:][::-1], "path": str(mem_path)}

from typing import Any, Dict, Optional, List, Tuple
from pathlib import Path
import os
import re
import json
import sqlite3

# Document generator
from .advanced_doc_generator import AdvancedDocumentGenerator
from eli.brain import config as eli_config
import time
import hashlib
import subprocess

import requests
import sys
import threading

import signal
import datetime
from concurrent.futures import ThreadPoolExecutor

# -------------------- OLLAMA WARM LOAD HELPERS --------------------


# === MEMORY_CONTEXT (for chat injection) ===
def _build_memory_context(query_text: str, limit: int = 6, max_chars: int = 1600) -> str:
    """
    Build a compact, truthful memory context block from SQLite/JSONL memory.
    This does NOT claim the model "remembers" anything — it just injects retrieved notes.
    """
    try:
        rec = memory_recall(query_text, limit=limit)
        if not (rec and rec.get("ok")):
            return ""
        rows = rec.get("results") or []
        if not rows:
            return ""

        # results may be dicts with 'text' or raw JSONL objects
        chunks = []
        for r in rows:
            txt = (r.get("text") if isinstance(r, dict) else None) or ""
            ts  = (r.get("ts") if isinstance(r, dict) else None) or ""
            if txt:
                # one-line it
                txt1 = " ".join(str(txt).split())
                chunks.append(f"- [{ts}] {txt1}" if ts else f"- {txt1}")

        if not chunks:
            return ""

        out = "Relevant stored notes (retrieved from local memory DB):\n" + "\n".join(chunks)
        out = out[:max_chars]
        return out.strip()
    except Exception:
        return ""
# === END MEMORY_CONTEXT ===
def _ollama_http_post_json(url: str, payload: dict, timeout_s: int = 30):
    """
    Minimal JSON POST helper using stdlib only.
    Returns: (ok: bool, status_code int|None, data: dict|str|None, err: str|None)
    """
    try:
        import json
        import urllib.request
        import urllib.error
    except Exception as e:
        return (False, None, None, f"stdlib_import_error: {e!r}")

    body = None
    try:
        body = json.dumps(payload).encode("utf-8")
    except Exception as e:
        return (False, None, None, f"json_encode_error: {e!r}")

    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            status = getattr(resp, "status", None) or 200
            raw = resp.read()
            try:
                txt = raw.decode("utf-8", errors="ignore")
            except Exception:
                txt = ""
            try:
                data = json.loads(txt) if txt else {}
            except Exception:
                data = txt
            return (True, status, data, None)
    except urllib.error.HTTPError as e:
        try:
            raw = e.read()
            txt = raw.decode("utf-8", errors="ignore")
        except Exception:
            txt = ""
        return (False, getattr(e, "code", None), txt, f"HTTPError: {e!r}")
    except Exception as e:
        return (False, None, None, f"urlopen_error: {e!r}")


def _ollama_warm_load(model: str, ollama_host: str) -> bool:
    """
    Best-effort warm-load so /api/ps can report digest for lockdown verification.
    Uses /api/chat (non-stream) with a tiny prompt.
    Returns True if the request likely caused the model to load (or is already loadable),
    False otherwise.
    """
    try:
        model = (model or "").strip()
        if not model:
            return False
        host = (ollama_host or "http://localhost:11434").rstrip("/")
        url = host + "/api/chat"

        payload = {
            "model": model,
            "stream": False,
            "messages": [{"role": "user", "content": "ping"}],
            "options": {"num_predict": 1},
        }

        ok, status, data, err = _ollama_http_post_json(url, payload, timeout_s=30)
        if not ok:
            return False

        # If we got a response object at all, the model was at least resolvable.
        # Ollama typically loads the model to answer, so this is a decent warm-load signal.
        if isinstance(data, dict):
            if "message" in data or "done" in data or "created_at" in data:
                return True
        return True
    except Exception:
        return False
# ------------------ END OLLAMA WARM LOAD HELPERS ------------------

# ----------------------------
# Core normalization utilities
# ----------------------------

def _normalize_result(res: object) -> Dict[str, Any]:
    """
    Guarantee GUI/voice always has:
      - res['ok'] (bool)
      - res['content'] (str)
      - res['response'] (str)
    """
    if not isinstance(res, dict):
        txt = "" if res is None else str(res)
        return {"ok": False, "error": "handler_returned_non_dict", "content": txt, "response": txt}

    if "ok" not in res:
        res["ok"] = False

    if "response" in res and "content" not in res:
        res["content"] = res.get("response")
    if "content" in res and "response" not in res:
        res["response"] = res.get("content")

    if "content" not in res or res.get("content") is None:
        fallback = res.get("message") or res.get("error") or ""
        res["content"] = str(fallback)
    if "response" not in res or res.get("response") is None:
        res["response"] = str(res.get("content") or "")

    res["content"] = "" if res["content"] is None else str(res["content"])
    res["response"] = "" if res["response"] is None else str(res["response"])
    return res


def _strip_ollama_artifacts(s: str) -> str:
    s = (s or "")
    s = s.replace("<|\nend\n", "").replace("<|end|>", "").replace("<|end|", "")
    s = re.sub(r"\s+$", "", s)
    return s.strip()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _run(argv: List[str], timeout: int = 15) -> Dict[str, Any]:
    try:
        p = subprocess.run(argv, timeout=timeout, capture_output=True, text=True, check=False)
        ok = (p.returncode == 0)
        msg = "OK" if ok else "Command failed"
        return {
            "ok": ok,
            "returncode": p.returncode,
            "stdout": p.stdout,
            "stderr": p.stderr,
            "cmd": argv,
            "content": msg,
            "response": msg,
        }
    except Exception as e:
        msg = "Command error"
        return {
            "ok": False,
            "returncode": 1,
            "stdout": "",
            "stderr": repr(e),
            "cmd": argv,
            "content": msg,
            "response": msg,
            "error": repr(e),
        }


# ----------------------------
# Config / state
# ----------------------------


DEFAULT_CHAT_MODEL = eli_config.ollama_model()

# Enumerated actions for capability_registry bootstrap
SUPPORTED_ACTIONS = ['CHAT', 'STOP_MEDIA', 'PAUSE_MEDIA', 'PLAY_MEDIA', 'NEXT_MEDIA', 'PREVIOUS_MEDIA',
                     'MEDIA_CONTROL', 'CHECK_CHRONAL_ALIGNMENT',
                     'CREATE_DOCUMENT', 'DATA_FABRICATOR', 'DOC_GENERATE', 'GENERATE_DOCUMENT',
                     'GENERATE_SCRIPT', 'GENERATE_PROJECT', 'FIX_FILE',
                     'HELP', 'LIST_CAPABILITIES',
                     'MEMORY_RECALL', 'MEMORY_STORE', 'MEMORY_STATS',
                     'OPEN_APP', 'OPEN_AUDIO_SETTINGS', 'OPEN_BROWSER',
                     'OPEN_COMMUNICATION_HUB', 'OPEN_FILE_SYSTEM', 'OPEN_MEDIA_HUB', 'OPEN_NETWORK_BROWSER',
                     'OPEN_URL', 'OPEN_SYSTEM_SETTINGS', 'OPEN_POWER_SETTINGS', 'OPEN_IDE', 'OPEN_IN_IDE',
                     'PERSONA_LOCK_CLEAR', 'PERSONA_LOCK_SET', 'PERSONA_LOCK_STATUS',
                     'PROACTIVE_START', 'PROACTIVE_STATUS', 'PROACTIVE_STOP',
                     'READ_FILE', 'RUN_CMD', 'SHELL_EXEC', 'LIST_DIR',
                     'SELF_ANALYZE', 'SELF_IMPROVE', 'MORNING_REPORT', 'SELF_TEST',
                     'SET_ALARM', 'SET_TIMER',
                     'SET_CLIPBOARD', 'GET_CLIPBOARD',
                     'GET_WEATHER', 'LIST_EVENTS', 'ADD_EVENT',
                     'SCREENSHOT', 'VOLUME', 'KEYBOARD',
                     'ANALYZE_PDF', 'ANALYZE_CSV', 'SUMMARIZE_FILE', 'CLOSE_APP',
                     'SHOW_DIFF', 'WRITE_NOTE',
                     'TIME', 'DATE']


STATE_PATH = Path(os.environ.get("ELI_STATE_FILE", str(Path.home() / ".eli_state.json")))

# Short-term conversation continuity
MAX_HISTORY_MESSAGES = int(os.environ.get("ELI_MAX_HISTORY_MESSAGES", "32"))

# Long-term memory store (simple deterministic archive, no embeddings)
MEMORY_PATH = Path(os.environ.get("ELI_MEMORY_FILE", str(Path.home() / ".eli_memory.jsonl")))

# Lock behavior: if true, refuse CHAT when verification fails
LOCK_ENFORCED = os.environ.get("ELI_LOCK_ENFORCED", "1").strip() not in ("0", "false", "False", "no", "NO")


def _load_state() -> Dict[str, Any]:
    try:
        if STATE_PATH.exists():
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_state(st: Dict[str, Any]) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(st, indent=2), encoding="utf-8")
    except Exception:
        pass


def _state_get_history(st: Dict[str, Any]) -> List[Dict[str, str]]:
    h = st.get("chat_history")
    if not isinstance(h, list):
        return []
    out: List[Dict[str, str]] = []
    for m in h:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        content = m.get("content")
        if role in ("user", "assistant") and isinstance(content, str):
            out.append({"role": role, "content": content})
    return out


def _state_append_history(st: Dict[str, Any], user_msg: str, assistant_msg: str) -> None:
    h = _state_get_history(st)
    h.append({"role": "user", "content": user_msg})
    h.append({"role": "assistant", "content": assistant_msg})
    if len(h) > MAX_HISTORY_MESSAGES:
        h = h[-MAX_HISTORY_MESSAGES:]
    st["chat_history"] = h
    st["updated_at"] = time.time()


# ----------------------------
# Persona lock + checksum verification
# ----------------------------

def _ollama_ps() -> Dict[str, Any]:
    try:
        return requests.get(f"{OLLAMA_HOST}/api/ps", timeout=10).json()
    except Exception:
        return {"models": []}


def _ollama_model_digest_from_ps(ps: Dict[str, Any], model_name: str) -> Optional[str]:
    for m in ps.get("models", []) or []:
        if (m.get("name") == model_name) or (m.get("model") == model_name):
            return m.get("digest") or None
    return None


def _verify_persona_lock(st: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Returns (ok, reason, details). If ok==False and LOCK_ENFORCED, CHAT should refuse to run.
    We verify:
      - model name matches expected (optional)
      - Modelfile checksum matches expected (optional)
      - Ollama digest matches expected (optional)
    """
    details: Dict[str, Any] = {}
    expected_model = (st.get("persona_lock") or {}).get("model") or None
    expected_modelfile = (st.get("persona_lock") or {}).get("modelfile_path") or None
    expected_modelfile_sha = (st.get("persona_lock") or {}).get("modelfile_sha256") or None
    expected_digest = (st.get("persona_lock") or {}).get("ollama_digest") or None
    current_model = (os.environ.get('ELI_CHAT_MODEL') or os.environ.get('OLLAMA_MODEL') or DEFAULT_CHAT_MODEL).strip()
    details["current_model"] = current_model
    details["expected_model"] = expected_model

    # 1) Model name check
    if expected_model and current_model != expected_model:
        return (False, "model_name_mismatch", {**details, "msg": f"Expected {expected_model}, got {current_model}."})

    # 2) Modelfile checksum check
    if expected_modelfile and expected_modelfile_sha:
        p = Path(os.path.expanduser(expected_modelfile))
        if not p.exists():
            return (False, "modelfile_missing", {**details, "msg": f"Locked Modelfile not found: {p}"})
        sha = _sha256_file(p)
        details["current_modelfile_sha256"] = sha
        if sha != expected_modelfile_sha:
            return (False, "modelfile_sha256_mismatch", {**details, "msg": "Modelfile checksum changed."})

    # 3) Ollama digest check (from /api/ps)
    # Resolve Ollama host once (no implicit globals)
    ollama_host = OLLAMA_HOST
    ps = _ollama_ps()
    dig = _ollama_model_digest_from_ps(ps, current_model)
    details["current_ollama_digest"] = dig
    details["expected_ollama_digest"] = expected_digest
    if expected_digest and dig and dig != expected_digest:
        return (False, "ollama_digest_mismatch", {**details, "msg": "Loaded model digest differs."})
    if expected_digest and dig is None:
        # Model may not be loaded yet; attempt a warm-load then re-check /api/ps.
        warmed = False
        try:
            warmed = _ollama_warm_load(current_model, ollama_host)
        except Exception as e:
            details["warm_load_error"] = repr(e)

        if warmed:
            ps2 = _ollama_ps()
            dig2 = _ollama_model_digest_from_ps(ps2, current_model)
            details["current_ollama_digest"] = dig2
            if dig2 and dig2 != expected_digest:
                return (False, "ollama_digest_mismatch", {**details, "msg": "Loaded model digest differs after warm-load."})
            if dig2:
                return (True, "ok", details)

        return (True, "ok_unverified", {**details, "warn": "Model not yet loaded; digest cannot be verified until first use."})
    # FINAL SUCCESS PATH — if nothing failed above, the lock is valid
    return (True, "ok", details)


def persona_lock_set(model: Optional[str] = None, modelfile_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Sets the lock baseline. This is the "make it unbreakable" button.
    - model defaults to DEFAULT_CHAT_MODEL
    - modelfile_path can be None (then only model + digest are locked)
    """
    st = _load_state()
    model = (model or DEFAULT_CHAT_MODEL).strip()

    lock: Dict[str, Any] = {"model": model, "set_at": time.time()}

    if modelfile_path:
        p = Path(os.path.expanduser(modelfile_path))
        if not p.exists():
            msg = f"Modelfile not found: {p}"
            return {"ok": False, "action": "PERSONA_LOCK_SET", "error": msg, "content": msg, "response": msg}
        lock["modelfile_path"] = str(p)
        lock["modelfile_sha256"] = _sha256_file(p)

    # Capture current digest (best effort)
    ps = _ollama_ps()
    dig = _ollama_model_digest_from_ps(ps, model)
    if dig:
        lock["ollama_digest"] = dig

    st["persona_lock"] = lock
    _save_state(st)

    msg = f"Persona lock set for model={model}."
    return {"ok": True, "action": "PERSONA_LOCK_SET", "lock": lock, "content": msg, "response": msg}


def persona_lock_status() -> Dict[str, Any]:
    st = _load_state()
    ok, reason, details = _verify_persona_lock(st)
    lock = st.get("persona_lock") or {}
    msg = "Persona lock OK." if ok else f"Persona lock FAIL: {reason}"
    return {"ok": ok, "action": "PERSONA_LOCK_STATUS", "reason": reason, "details": details, "lock": lock, "content": msg, "response": msg}


def persona_lock_clear() -> Dict[str, Any]:
    st = _load_state()
    st.pop("persona_lock", None)
    _save_state(st)
    msg = "Persona lock cleared."
    return {"ok": True, "action": "PERSONA_LOCK_CLEAR", "content": msg, "response": msg}


# ----------------------------
# Persistent long-term memory (deterministic archive)
# ----------------------------

def memory_store_legacy(text: str, tags: Optional[List[str]] = None) -> Dict[str, Any]:
    text = (text or "").strip()
    if not text:
        msg = "Empty memory text."
        return {"ok": False, "action": "MEMORY_STORE", "error": "empty_text", "content": msg, "response": msg}

    rec = {
        "ts": time.time(),
        "text": text,
        "tags": [t.strip() for t in (tags or []) if isinstance(t, str) and t.strip()],
    }
    try:
        MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with MEMORY_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        msg = "Memory stored."
        return {"ok": True, "action": "MEMORY_STORE", "record": rec, "content": msg, "response": msg}
    except Exception as e:
        msg = "Failed to store memory."
        return {"ok": False, "action": "MEMORY_STORE", "error": repr(e), "content": msg, "response": msg}


def memory_recall_legacy(query: str, limit: int = 5) -> Dict[str, Any]:
    q = (query or "").strip().lower()
    if not q:
        msg = "Empty recall query."
        return {"ok": False, "action": "MEMORY_RECALL", "error": "empty_query", "content": msg, "response": msg}

    hits: List[Dict[str, Any]] = []
    try:
        if not MEMORY_PATH.exists():
            msg = "No memory archive yet."
            return {"ok": True, "action": "MEMORY_RECALL", "hits": [], "content": msg, "response": msg}

        with MEMORY_PATH.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                text = str(rec.get("text", "")).lower()
                tags = " ".join(rec.get("tags") or []).lower()
                if q in text or q in tags:
                    hits.append(rec)

        hits = hits[-max(1, int(limit)):]  # most recent matches
        # Human readable summary
        summary_lines = []
        for r in reversed(hits):
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r.get("ts", 0)))
            t = str(r.get("text", "")).strip()
            t = t if len(t) <= 180 else t[:177] + "..."
            summary_lines.append(f"- [{ts}] {t}")
        content = "Memory recall:\n" + ("\n".join(summary_lines) if summary_lines else "(no matches)")
        return {"ok": True, "action": "MEMORY_RECALL", "hits": hits, "content": content, "response": content}
    except Exception as e:
        msg = "Memory recall failed."
        return {"ok": False, "action": "MEMORY_RECALL", "error": repr(e), "content": msg, "response": msg}


# ----------------------------
# Self-consistency tests + healthcheck
# ----------------------------

def self_test() -> Dict[str, Any]:
    """
    Runs a deterministic suite:
      - persona lock status
      - minimal chat handshake
      - consistency probe (temperature=0 twice) and compare
    """
    st = _load_state()
    ok_lock, reason, details = _verify_persona_lock(st)

    results: Dict[str, Any] = {
        "persona_lock": {"ok": ok_lock, "reason": reason, "details": details},
        "tests": []
    }

    # 1) Handshake: "Reply with exactly: persona_ok"
    handshake_prompt = "Reply with exactly these 2 words: persona ok"
    h1 = _ollama_chat_raw(handshake_prompt, temperature=0.0, num_predict=16)
    results["tests"].append({"name": "handshake", **h1})

    # 2) Consistency probe: same prompt twice with temp=0
    probe = "Reply with exactly 4 words: consistency test passed."
    p1 = _ollama_chat_raw(probe, temperature=0.0, num_predict=16)
    p2 = _ollama_chat_raw(probe, temperature=0.0, num_predict=16)
    same = (p1.get("content") == p2.get("content")) and p1.get("ok") and p2.get("ok")
    results["tests"].append({"name": "consistency_probe_1", **p1})
    results["tests"].append({"name": "consistency_probe_2", **p2})
    results["tests"].append({"name": "consistency_equal", "ok": same, "content": str(same), "response": str(same)})

    # overall ok
    overall_ok = bool(ok_lock) and bool(h1.get("ok")) and bool(p1.get("ok")) and bool(p2.get("ok"))
    msg = "SELF_TEST OK" if overall_ok else "SELF_TEST FAIL"
    return {"ok": overall_ok, "action": "SELF_TEST", "results": results, "content": msg, "response": msg}


def _ollama_chat_raw(user_text: str, temperature: float = 0.7, num_predict: int = 80) -> Dict[str, Any]:
    model = DEFAULT_CHAT_MODEL
    payload = {
        "model": model,
        "stream": False,
        "messages": [{"role": "user", "content": user_text}],
        "options": {"temperature": float(temperature), "num_predict": int(num_predict)},
    }
    try:
        r = requests.post(f"{OLLAMA_HOST}/api/chat", json=payload, timeout=(10, 3600))
        r.raise_for_status()
        j = r.json()
        content = _strip_ollama_artifacts(((j.get("message") or {}).get("content") or "").strip())
        return {"ok": True, "model": model, "content": content, "response": content}
    except Exception as e:
        msg = "raw chat failed"
        return {"ok": False, "model": model, "error": repr(e), "content": msg, "response": msg}


# ----------------------------
# Origin / identity (NO prompt hijack)
# ----------------------------

def _is_origin_question(msg: str) -> bool:
    low = (msg or "").lower()
    triggers = [
        "who created you", "who made you", "who built you",
        "who are you", "your creator", "your origin",
        "who developed you"
    ]
    return any(t in low for t in triggers)


def _origin_facts(st: Dict[str, Any]) -> str:
    name = (st.get("user_name") or os.environ.get("ELI_USER_NAME") or "").strip() or "The user"
    return (
        f"Factual note: {name} assembled/configured ELI; ELI runs locally via Ollama using base model weights. "
        f"Don't claim any company 'created ELI' as a shipped product."
    )


def _needs_origin_anchor(ans: str) -> bool:
    """
    If origin question answer drifts into corporate-creator claims,
    we append a short factual anchor (we do NOT rewrite the answer).
    """
    a = (ans or "").lower()
    bad = [
        "created by alibaba", "developed by alibaba", "created by openai", "developed by openai",
        "created by qwen", "developed by qwen", "alibaba cloud created", "openai created"
    ]
    return any(x in a for x in bad)


# ================== MEDIA CONTROL FUNCTIONS ==================
def stop_media() -> Dict[str, Any]:
    """Stop currently playing media."""
    try:
        # Try common Linux media control methods
        # Method 1: playerctl (if installed)
        try:
            subprocess.run(["playerctl", "-p", "spotify,%any", "stop"], capture_output=True, timeout=5)
            msg = "Media stopped."
            return {"ok": True, "action": "STOP_MEDIA", "content": msg, "response": msg}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        
        # Method 2: kill spotify process
        try:
            subprocess.run(["pkill", "-f", "spotify"], capture_output=True, timeout=5)
            msg = "Spotify stopped."
            return {"ok": True, "action": "STOP_MEDIA", "content": msg, "response": msg}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
            
        # Method 3: dbus control for common players
        try:
            subprocess.run([
                "dbus-send", "--print-reply", "--dest=org.mpris.MediaPlayer2.spotify",
                "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player.Stop"
            ], capture_output=True, timeout=5)
            msg = "Media stopped via D-Bus."
            return {"ok": True, "action": "STOP_MEDIA", "content": msg, "response": msg}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
            
        msg = "No active media player found or control method unavailable."
        return {"ok": False, "action": "STOP_MEDIA", "content": msg, "response": msg}
    except Exception as e:
        msg = f"Failed to stop media: {e}"
        return {"ok": False, "action": "STOP_MEDIA", "error": str(e), "content": msg, "response": msg}


def pause_media() -> Dict[str, Any]:
    """Pause currently playing media."""
    try:
        # Try playerctl first
        try:
            subprocess.run(["playerctl", "-p", "spotify,%any", "pause"], capture_output=True, timeout=5)
            msg = "Media paused."
            return {"ok": True, "action": "PAUSE_MEDIA", "content": msg, "response": msg}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
            
        # Try dbus
        try:
            subprocess.run([
                "dbus-send", "--print-reply", "--dest=org.mpris.MediaPlayer2.spotify",
                "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player.Pause"
            ], capture_output=True, timeout=5)
            msg = "Media paused via D-Bus."
            return {"ok": True, "action": "PAUSE_MEDIA", "content": msg, "response": msg}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
            
        msg = "No active media player found or control method unavailable."
        return {"ok": False, "action": "PAUSE_MEDIA", "content": msg, "response": msg}
    except Exception as e:
        msg = f"Failed to pause media: {e}"
        return {"ok": False, "action": "PAUSE_MEDIA", "error": str(e), "content": msg, "response": msg}


def play_media() -> Dict[str, Any]:
    """Play/resume media."""
    try:
        # Try playerctl first
        try:
            subprocess.run(["playerctl", "-p", "spotify,%any", "play"], capture_output=True, timeout=5)
            msg = "Media playing."
            return {"ok": True, "action": "PLAY_MEDIA", "content": msg, "response": msg}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
            
        # Try dbus
        try:
            subprocess.run([
                "dbus-send", "--print-reply", "--dest=org.mpris.MediaPlayer2.spotify",
                "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player.Play"
            ], capture_output=True, timeout=5)
            msg = "Media playing via D-Bus."
            return {"ok": True, "action": "PLAY_MEDIA", "content": msg, "response": msg}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
            
        msg = "No active media player found or control method unavailable."
        return {"ok": False, "action": "PLAY_MEDIA", "content": msg, "response": msg}
    except Exception as e:
        msg = f"Failed to play media: {e}"
        return {"ok": False, "action": "PLAY_MEDIA", "error": str(e), "content": msg, "response": msg}


def next_media() -> Dict[str, Any]:
    """Skip to next track."""
    try:
        # Try playerctl first
        try:
            subprocess.run(["playerctl", "-p", "spotify,%any", "next"], capture_output=True, timeout=5)
            msg = "Skipped to next track."
            return {"ok": True, "action": "NEXT_MEDIA", "content": msg, "response": msg}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
            
        # Try dbus
        try:
            subprocess.run([
                "dbus-send", "--print-reply", "--dest=org.mpris.MediaPlayer2.spotify",
                "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player.Next"
            ], capture_output=True, timeout=5)
            msg = "Next track via D-Bus."
            return {"ok": True, "action": "NEXT_MEDIA", "content": msg, "response": msg}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
            
        msg = "No active media player found or control method unavailable."
        return {"ok": False, "action": "NEXT_MEDIA", "content": msg, "response": msg}
    except Exception as e:
        msg = f"Failed to skip to next track: {e}"
        return {"ok": False, "action": "NEXT_MEDIA", "error": str(e), "content": msg, "response": msg}


def previous_media() -> Dict[str, Any]:
    """Go to previous track."""
    try:
        # Try playerctl first
        try:
            subprocess.run(["playerctl", "-p", "spotify,%any", "previous"], capture_output=True, timeout=5)
            msg = "Went to previous track."
            return {"ok": True, "action": "PREVIOUS_MEDIA", "content": msg, "response": msg}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
            
        # Try dbus
        try:
            subprocess.run([
                "dbus-send", "--print-reply", "--dest=org.mpris.MediaPlayer2.spotify",
                "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player.Previous"
            ], capture_output=True, timeout=5)
            msg = "Previous track via D-Bus."
            return {"ok": True, "action": "PREVIOUS_MEDIA", "content": msg, "response": msg}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
            
        msg = "No active media player found or control method unavailable."
        return {"ok": False, "action": "PREVIOUS_MEDIA", "content": msg, "response": msg}
    except Exception as e:
        msg = f"Failed to go to previous track: {e}"
        return {"ok": False, "action": "PREVIOUS_MEDIA", "error": str(e), "content": msg, "response": msg}
# ================== END MEDIA CONTROL ==================

# ----------------------------
# CHAT with persistent conversation + lock enforcement
# ----------------------------

def _memory_capability_truth() -> str:
    """Truth-only memory capability statement. Never fabricate recall."""
    try:
        has_adapter = False
        has_sqlite = False
        try:
            from eli.brain.memory_adapter import memory_recall as _mr  # noqa: F401
            has_adapter = True
        except Exception:
            pass
        try:
            import sqlite3 as _sql  # noqa: F401
            has_sqlite = True
        except Exception:
            pass

        if has_adapter or has_sqlite:
            return (
                "I use two memory layers: session context and persistent local memory. "
                "Persistent memory is stored locally (SQLite/artifacts via memory adapters) "
                "and can be recalled across restarts if saved and retrievable by query."
            )
        return (
            "I currently have session context in this runtime; persistent memory backends are "
            "not available right now. I won’t claim cross-session recall unless retrieval succeeds."
        )
    except Exception:
        return (
            "I won’t guess about memory state. Session context is available; persistent recall "
            "depends on configured local memory backends and successful retrieval."
        )





def _live_memory_audit() -> dict:
    """
    Real local-memory audit:
    - SQLite memory DB(s)
    - conversations JSONL
    - proactive artifacts
    - latest context/summary/action files
    Returns factual counts + health, never fabricated claims.
    """
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    root = Path(__file__).resolve().parents[3]  # .../AI_EliMKVI
    candidates = {
        "root_artifacts_db": root / "artifacts" / "eli_memory.sqlite3",
        "src_artifacts_db": root / "src" / "eli" / "artifacts" / "eli_memory.sqlite3",
        "conversations_dir": root / "src" / "eli" / "artifacts" / "conversations",
        "proactive_dir": root / "artifacts" / "proactive",
        "src_latest_context": root / "artifacts" / "latest_context.txt",
        "src_latest_summary": root / "artifacts" / "latest_summary.txt",
        "src_latest_action": root / "artifacts" / "latest_action.txt",
    }

    report = {
        "ok": True,
        "ts_utc": now,
        "root": str(root),
        "stores": {},
        "errors": [],
    }

    # ---- SQLite scan ----
    def scan_sqlite(db_path: Path):
        out = {"path": str(db_path), "exists": db_path.exists(), "size_bytes": 0, "tables": {}, "recent_rows": []}
        if not db_path.exists():
            return out
        out["size_bytes"] = db_path.stat().st_size
        try:
            conn = sqlite3.connect(str(db_path))
            cur = conn.cursor()

            cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
            tables = [r[0] for r in cur.fetchall()]
            out["tables"]["__all__"] = len(tables)

            for t in tables:
                try:
                    cur.execute(f'SELECT COUNT(*) FROM "{t}"')
                    out["tables"][t] = int(cur.fetchone()[0] or 0)
                except Exception as e:
                    out["tables"][t] = f"count_error: {e}"

            # try pull likely memory/event rows
            for t in ("events", "memory", "memories", "conversation", "conversations"):
                if t in tables:
                    try:
                        cur.execute(f'SELECT * FROM "{t}" ORDER BY rowid DESC LIMIT 3')
                        rows = cur.fetchall()
                        out["recent_rows"].append({"table": t, "rows_found": len(rows)})
                    except Exception as e:
                        out["recent_rows"].append({"table": t, "error": str(e)})
            conn.close()
        except Exception as e:
            out["error"] = str(e)
        return out

    for key in ("root_artifacts_db", "src_artifacts_db"):
        report["stores"][key] = scan_sqlite(candidates[key])

    # ---- JSONL conversations ----
    conv_dir = candidates["conversations_dir"]
    conv_out = {"path": str(conv_dir), "exists": conv_dir.exists(), "files": 0, "lines_total": 0, "latest_file": None}
    try:
        if conv_dir.exists():
            files = sorted(conv_dir.glob("*.jsonl"))
            conv_out["files"] = len(files)
            if files:
                conv_out["latest_file"] = str(files[-1])
            total = 0
            for f in files:
                try:
                    with f.open("r", encoding="utf-8", errors="ignore") as fh:
                        for _ in fh:
                            total += 1
                except Exception:
                    pass
            conv_out["lines_total"] = total
    except Exception as e:
        conv_out["error"] = str(e)
    report["stores"]["conversations"] = conv_out

    # ---- proactive files ----
    pro_dir = candidates["proactive_dir"]
    pro_out = {"path": str(pro_dir), "exists": pro_dir.exists(), "files": {}}
    for name in ("latest_context.txt", "latest_summary.txt", "latest_action.txt", "latest_decision.txt", "latest.txt"):
        fp = pro_dir / name
        entry = {"exists": fp.exists(), "size_bytes": (fp.stat().st_size if fp.exists() else 0)}
        if fp.exists():
            try:
                txt = fp.read_text(encoding="utf-8", errors="ignore").strip()
                entry["preview"] = txt[:200]
            except Exception as e:
                entry["read_error"] = str(e)
        pro_out["files"][name] = entry
    report["stores"]["proactive"] = pro_out

    # ---- top-level latest files ----
    for key in ("src_latest_context", "src_latest_summary", "src_latest_action"):
        fp = candidates[key]
        entry = {"path": str(fp), "exists": fp.exists(), "size_bytes": (fp.stat().st_size if fp.exists() else 0)}
        if fp.exists():
            try:
                entry["preview"] = fp.read_text(encoding="utf-8", errors="ignore").strip()[:200]
            except Exception as e:
                entry["read_error"] = str(e)
        report["stores"][key] = entry

    return report


def _format_memory_audit_for_chat(rep: dict) -> str:
    try:
        s = rep.get("stores", {})
        db1 = s.get("root_artifacts_db", {})
        db2 = s.get("src_artifacts_db", {})
        conv = s.get("conversations", {})
        pro = s.get("proactive", {})

        def table_count(d):
            t = d.get("tables", {})
            return ", ".join([f"{k}:{v}" for k, v in t.items() if k != "__all__"][:6]) or "none"

        lines = []
        lines.append("Live memory audit complete (no template response):")
        lines.append(f"- Root DB exists: {db1.get('exists')} | size: {db1.get('size_bytes',0)} bytes | tables: {db1.get('tables',{}).get('__all__',0)}")
        lines.append(f"  table counts: {table_count(db1)}")
        lines.append(f"- Src DB exists: {db2.get('exists')} | size: {db2.get('size_bytes',0)} bytes | tables: {db2.get('tables',{}).get('__all__',0)}")
        lines.append(f"  table counts: {table_count(db2)}")
        lines.append(f"- Conversation logs: files={conv.get('files',0)} lines_total={conv.get('lines_total',0)} latest={conv.get('latest_file')}")
        latest_ctx = pro.get("files", {}).get("latest_context.txt", {})
        latest_sum = pro.get("files", {}).get("latest_summary.txt", {})
        latest_act = pro.get("files", {}).get("latest_action.txt", {})
        lines.append(f"- Proactive context exists={latest_ctx.get('exists')} size={latest_ctx.get('size_bytes',0)}")
        lines.append(f"- Proactive summary exists={latest_sum.get('exists')} size={latest_sum.get('size_bytes',0)}")
        lines.append(f"- Proactive action exists={latest_act.get('exists')} size={latest_act.get('size_bytes',0)}")
        lines.append("")
        lines.append("If you want retrieval proof for a specific topic, ask: \"memory audit for <topic>\" and I will query the DB rows directly.")
        return "\n".join(lines)
    except Exception as e:
        return f"Live memory audit failed to format: {e}"

def chat(message: str, *, model: Optional[str] = None) -> Dict[str, Any]:
    msg = (message or "").strip()
    low_msg = msg.lower()

    _convlog_append('user', msg, {'fn':'chat','model': str(model or DEFAULT_CHAT_MODEL)})
    if not msg:
        return {"ok": False, "action": "CHAT", "error": "empty_message", "content": "", "response": ""}

    # Live audit path for memory-capability questions (real DB/files scan, never template)
    if (
        "how your memory" in low_msg or "how does your memory" in low_msg or
        "persistent memory" in low_msg or "across sessions" in low_msg or
        "continuous memory" in low_msg or "memory audit" in low_msg
    ):
        rep = _live_memory_audit()
        ans = _format_memory_audit_for_chat(rep)
        _convlog_append('assistant', ans, {'fn':'chat','path':'live_memory_audit'})
        return {"ok": True, "action": "CHAT", "content": ans, "response": ans, "memory_audit": rep}

    # Explicit "yesterday" recall path (no fabrication)
    if ("what did we discuss yesterday" in low_msg or ("what did" in low_msg and "yesterday" in low_msg and "discuss" in low_msg)):
        try:
            rec = memory_recall("", limit=8)
            rows = rec.get("results") if isinstance(rec, dict) else []
            if rows:
                lines = []
                for r in rows[:8]:
                    t = str((r or {}).get("text", "")).strip()
                    if t:
                        lines.append("- " + " ".join(t.split())[:240])
                ans = "I can only report what is in persistent memory. Recent stored notes:\n" + ("\n".join(lines) if lines else "(none)")
            else:
                ans = "I can’t verify yesterday from persistent memory right now (no matching stored notes found). I won’t guess."
        except Exception:
            ans = "I can’t verify yesterday from persistent memory right now. I won’t guess."
        return {"ok": True, "action": "CHAT", "model": model or DEFAULT_CHAT_MODEL, "content": ans, "response": ans}

    # Route non-chat intents (commands) exactly like previous behavior
    try:
        from eli.tools.router_enhanced import route
        intent = route(msg)
        if intent.get("action") and intent["action"] != "CHAT":
            return execute(intent["action"], intent.get("args", {}))
    except Exception:
        pass

    st = _load_state()

    # Enforce lock BEFORE chatting (prevents silent personality drift)
    ok_lock, reason, details = _verify_persona_lock(st)
    if LOCK_ENFORCED and not ok_lock and (st.get("persona_lock") is not None):
        content = (
            f"ELI LOCKDOWN: persona verification failed ({reason}).\n"
            f"{details.get('msg','')}\n\n"
            "Run PERSONA_LOCK_SET with the intended model/modelfile, or fix environment drift."
        )
        return {"ok": False, "action": "CHAT", "error": "persona_lock_failed", "reason": reason, "details": details, "content": content, "response": content}

    model = (model or DEFAULT_CHAT_MODEL).strip()
    if not model:
        content = "No Ollama model set. Set ELI_MODEL to a model you have pulled (see `ollama list`)."
        return {"ok": False, "action": "CHAT", "error": "no_model", "content": content, "response": content}
    try:
        body = {"model": model, "messages": [{"role": "user", "content": msg}], "stream": False}
        res = requests.post(f"{_OLLAMA_HOST}/api/chat", json=body, timeout=CHAT_TIMEOUT_S)
        res.raise_for_status()
        j = res.json() if res.content else {}
        content = _strip_ollama_artifacts(((j.get("message") or {}).get("content") or "").strip())
        if not content:
            content = "(empty model response)"
        _convlog_append('assistant', content, {'fn':'chat','model': model})
        return {"ok": True, "action": "CHAT", "model": model, "content": content, "response": content}
    except Exception as e:
        err = f"chat_failed: {e}"
        _convlog_append('assistant', err, {'fn':'chat','model': model, 'error': True})
        return {"ok": False, "action": "CHAT", "error": str(e), "content": err, "response": err}


def chat_stream(message: str, *, model: Optional[str] = None):
    """
    Streaming chat generator that yields token chunks (str).
    - Routes non-chat intents through execute()
    - Enforces persona lock
    - Falls back to non-stream chat() behavior if needed
    """
    msg = (message or "").strip()

    low_msg = msg.lower()
    if (
        "how your memory" in low_msg or "how does your memory" in low_msg or
        "persistent memory" in low_msg or "across sessions" in low_msg or
        "continuous memory" in low_msg or "memory audit" in low_msg
    ):
        rep = _live_memory_audit()
        yield _format_memory_audit_for_chat(rep)
        return
    if not msg:
        return

    # Route commands first
    try:
        from eli.tools.router_enhanced import route
        intent = route(msg)
        if intent.get("action") and intent["action"] != "CHAT":
            r = execute(intent["action"], intent.get("args", {}))
            out = str((r or {}).get("response") or (r or {}).get("content") or "")
            if out:
                yield out
            return
    except Exception:
        pass

    st = _load_state()
    ok_lock, reason, details = _verify_persona_lock(st)
    if LOCK_ENFORCED and not ok_lock and (st.get("persona_lock") is not None):
        yield (
            f"ELI LOCKDOWN: persona verification failed ({reason}).\n"
            f"{details.get('msg','')}\n\n"
            "Run PERSONA_LOCK_SET with the intended model/modelfile, or fix environment drift."
        )
        return

    model = (model or DEFAULT_CHAT_MODEL).strip()
    full = []
    try:
        body = {"model": model, "messages": [{"role": "user", "content": msg}], "stream": True}
        with requests.post(f"{_OLLAMA_HOST}/api/chat", json=body, stream=True, timeout=CHAT_TIMEOUT_S) as res:
            res.raise_for_status()
            for line in res.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    j = json.loads(line)
                except Exception:
                    continue
                delta = _strip_ollama_artifacts(((j.get("message") or {}).get("content") or ""))
                if delta:
                    full.append(delta)
                    yield delta
                if j.get("done"):
                    break

        content = "".join(full).strip()
        if content:
            _convlog_append('assistant', content, {'fn':'chat_stream','model': model})
        else:
            fallback = chat(msg, model=model)
            text = str(fallback.get("response") or fallback.get("content") or "")
            if text:
                yield text
    except Exception:
        fallback = chat(msg, model=model)
        text = str(fallback.get("response") or fallback.get("content") or "")
        if text:
            yield text

def open_audio_settings() -> Dict[str, Any]:
    for cmd in (["pavucontrol"], ["gnome-control-center", "sound"]):
        r = _run(cmd, timeout=5)
        if r.get("ok"):
            msg = "Audio settings opened."
            return {"ok": True, "action": "OPEN_AUDIO_SETTINGS", "cmd": cmd, "content": msg, "response": msg}
    msg = "No audio settings app found (pavucontrol / gnome-control-center)."
    return {"ok": False, "action": "OPEN_AUDIO_SETTINGS", "error": msg, "content": msg, "response": msg}


def open_file_system(path: str = "~") -> Dict[str, Any]:
    try:
        target = os.path.expanduser(path)
        subprocess.Popen(["xdg-open", target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        msg = "File system opened."
        return {"ok": True, "action": "OPEN_FILE_SYSTEM", "path": target, "content": msg, "response": msg}
    except Exception as e:
        msg = "Failed to open file system."
        return {"ok": False, "action": "OPEN_FILE_SYSTEM", "error": repr(e), "content": msg, "response": msg}


def fabricate_document(args: Dict[str, Any]) -> Dict[str, Any]:
    """Generate a real on-disk document (DOCX; optionally ODT) under artifacts/."""
    topic = (args.get('topic') or args.get('title') or 'Untitled Document').strip()
    content = (args.get('content') or '').strip()
    fmt = (args.get('format') or 'docx').lower().strip()

    # If content wasn't supplied, generate it via the chat model, but keep it deterministic-ish.
    if not content:
        prompt = (
            "Write a clean, factual document in Markdown about: " + topic + "\n"
            "Structure: title, short biography/overview, key contributions, timeline, references placeholder. "
            "No made-up citations. If unsure, say so."
        )
        gen = chat(prompt)
        if not gen.get('ok'):
            return {"ok": False, "error": gen.get('error') or 'document_content_generation_failed'}
        content = gen.get('content', '')

    want_docx = fmt in ('docx', 'both', 'docx+odt', 'odt', 'odt+docx')
    want_odt = fmt in ('odt', 'both', 'docx+odt', 'odt+docx')

    genr = AdvancedDocumentGenerator(base_dir=os.environ.get('ELI_ARTIFACTS_DIR') or 'artifacts')
    res = genr.generate(topic=topic, content=content, want_docx=want_docx, want_odt=want_odt, also_txt=True)
    if not res.ok:
        return {"ok": False, "error": res.error or 'document_generation_failed', "topic": topic, "out_dir": res.out_dir}

    # Return paths so GUI can show / open.
    return {
        "ok": True,
        "topic": topic,
        "out_dir": res.out_dir,
        "txt_path": res.txt_path,
        "docx_path": res.docx_path,
        "odt_path": res.odt_path,
        "content": (
            f"Document generated.\n"
            f"- out_dir: {res.out_dir}\n"
            + (f"- docx: {res.docx_path}\n" if res.docx_path else "")
            + (f"- odt: {res.odt_path}\n" if res.odt_path else "")
            + (f"- text: {res.txt_path}\n" if res.txt_path else "")
        ),
    }


def open_browser(url: str = "https://duckduckgo.com") -> Dict[str, Any]:
    try:
        subprocess.Popen(["xdg-open", str(url)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        msg = "Network browser opened."
        return {"ok": True, "action": "OPEN_BROWSER", "url": str(url), "content": msg, "response": msg}
    except Exception as e:
        msg = "Failed to open browser."
        return {"ok": False, "action": "OPEN_BROWSER", "error": repr(e), "content": msg, "response": msg}


def set_user_name(name: str) -> Dict[str, Any]:
    n = (name or "").strip()
    if not n:
        msg = "Empty name."
        return {"ok": False, "action": "SET_USER_NAME", "error": "empty_name", "content": msg, "response": msg}
    st = _load_state()
    st["user_name"] = n
    st["updated_at"] = time.time()
    _save_state(st)
    msg = f"Name set to {n}."
    return {"ok": True, "action": "SET_USER_NAME", "user_name": n, "content": msg, "response": msg}


def get_status() -> Dict[str, Any]:
    st = _load_state()
    ps = _ollama_ps()
    msg = "Status OK."
    return {
        "ok": True,
        "action": "GET_STATUS",
        "user_name": st.get("user_name", ""),
        "chat_model_default": DEFAULT_CHAT_MODEL,
        "persona_lock": st.get("persona_lock") or None,
        "ollama_ps": ps,
        "content": msg,
        "response": msg,
    }


def clear_chat_history() -> Dict[str, Any]:
    st = _load_state()
    st["chat_history"] = []
    st["updated_at"] = time.time()
    _save_state(st)
    msg = "Chat history cleared."
    return {"ok": True, "action": "CLEAR_CHAT_HISTORY", "content": msg, "response": msg}


# ================== MISSING FUNCTIONS FROM Eli_PC_Control2_Working.py ==================

# --- SMART IMPORT HANDLING ---
def _try_import_faster_whisper():
    """Try multiple strategies to import faster_whisper."""
    strategies = [
        # Try direct import first
        lambda: __import__('faster_whisper'),
        
        # Try adding venv path
        lambda: (sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.venv', 'lib', 
                                                 f'python{sys.version_info.major}.{sys.version_info.minor}', 
                                                 'site-packages')) or __import__('faster_whisper')),
        
        # Try common site-packages locations
        lambda: (sys.path.insert(0, os.path.expanduser('~/.local/lib/') + 
                                 f'python{sys.version_info.major}.{sys.version_info.minor}/site-packages') 
                or __import__('faster_whisper')),
    ]
    
    for strategy in strategies:
        try:
            return strategy()
        except ImportError:
            continue
    
    return None


# --- ENV HELPERS ---
def _env_int(name: str, default: int) -> int:
    try:
        v = (os.environ.get(name) or "").strip()
        return int(v) if v else int(default)
    except Exception:
        return int(default)


# --- MEDIA DUCKING ---
MEDIA_DUCK = str(os.environ.get("ELI_MEDIA_DUCK", "1")).strip().lower() not in ("0","false","no","off")
MEDIA_PLAYER = (os.environ.get("ELI_MEDIA_PLAYER", "spotify") or "spotify").strip()

_DUCKED_MEDIA = False
_DUCK_TIMER = None
_DUCK_LOCK = threading.Lock()

def _playerctl_run(argv):
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except Exception as e:
        return 1, "", str(e)

def _playerctl_p(*args):
    if MEDIA_PLAYER:
        return _playerctl_run(["playerctl", "-p", MEDIA_PLAYER, *args])
    return _playerctl_run(["playerctl", *args])

def _duck_media_pause():
    # Pause ONLY if it was actually playing; remember we ducked it.
    global _DUCKED_MEDIA
    if not MEDIA_DUCK:
        return
    if _DUCKED_MEDIA:
        return
    rc, out, _ = _playerctl_p("status")
    if rc == 0 and out.lower() == "playing":
        _playerctl_p("pause")
        _DUCKED_MEDIA = True

def _duck_media_resume():
    global _DUCKED_MEDIA
    if not MEDIA_DUCK:
        return
    if not _DUCKED_MEDIA:
        return
    _playerctl_p("play")
    _DUCKED_MEDIA = False

def _duck_schedule_resume(deadline_s: float):
    # Reset timer each time wake window is extended.
    global _DUCK_TIMER
    if not MEDIA_DUCK:
        return
    import time
    with _DUCK_LOCK:
        if _DUCK_TIMER is not None:
            try:
                _DUCK_TIMER.cancel()
            except Exception:
                pass
            _DUCK_TIMER = None
        delay = max(0.0, float(deadline_s) - time.time())
        t = threading.Timer(delay, _duck_media_resume)
        t.daemon = True
        _DUCK_TIMER = t
        t.start()


# --- TTS FUNCTIONS ---
_TTS_ENGINE = None
_MIC_IGNORE_UNTIL = 0.0  # ignore mic until this monotonic time
_BUSY_UNTIL = 0.0  # ignore mic while executing actions
_STOP_REQUESTED = False

def _init_tts():
    global _TTS_ENGINE
    if _TTS_ENGINE is not None:
        return
    try:
        import pyttsx3
    except Exception as e:
        if DEBUG:
            print(f"[TTS] pyttsx3 not available: {e}")
        _TTS_ENGINE = None
        return

    eng = pyttsx3.init()
    voice_name = os.environ.get("ELI_TTS_VOICE", "").strip().lower()
    rate       = os.environ.get("ELI_TTS_RATE", "").strip()

    # optional: choose a different voice by partial name
    if voice_name:
        try:
            for v in eng.getProperty("voices"):
                if voice_name in v.name.lower():
                    eng.setProperty("voice", v.id)
                    break
        except Exception as e:
            if DEBUG:
                print(f"[TTS] voice selection failed: {e}")

    if rate:
        try:
            eng.setProperty("rate", int(rate))
        except Exception as e:
            if DEBUG:
                print(f"[TTS] rate set failed: {e}")

    _TTS_ENGINE = eng

def _tts_list_voices() -> dict:
    _init_tts()
    eng = _TTS_ENGINE
    voices = []
    try:
        for v in (eng.getProperty("voices") or []):
            voices.append({
                "id": getattr(v, "id", "") or "",
                "name": getattr(v, "name", "") or "",
            })
    except Exception:
        pass
    return {"current": os.environ.get("ELI_TTS_VOICE", ""), "voices": voices, "count": len(voices)}

def _tts_set_voice(target: str) -> dict:
    _init_tts()
    eng = _TTS_ENGINE
    target_l = (target or "").strip().lower()
    if not target_l:
        raise ValueError("empty voice target")
    chosen_id = None
    chosen_name = None
    try:
        for v in (eng.getProperty("voices") or []):
            vid = (getattr(v, "id", "") or "").lower()
            vname = (getattr(v, "name", "") or "").lower()
            if target_l in vid or target_l in vname:
                chosen_id = getattr(v, "id", None)
                chosen_name = getattr(v, "name", None) or target
                break
    except Exception:
        pass
    if not chosen_id:
        raise ValueError(f"Voice not found: {target}")
    try:
        eng.setProperty("voice", chosen_id)
    except Exception:
        # still persist preference; engine may apply on next init
        pass
    os.environ["ELI_TTS_VOICE"] = str(chosen_name)
    try:
        MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        TTS_PREF_FILE = MEMORY_PATH.parent / "tts_voice.json"
        TTS_PREF_FILE.write_text(json.dumps({"voice": os.environ["ELI_TTS_VOICE"]}, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return {"voice": os.environ["ELI_TTS_VOICE"], "id": chosen_id}

def _speak_legacy(text: str):
    """
    Speak text aloud. Never fail silently.
    - If ELI_TTS_ENGINE=piper and ELI_PIPER_MODEL is set, try piper.
    - Otherwise fall back to espeak-ng/espeak.
    - Always play with paplay/pw-play/aplay (first found).
    - If ELI_TTS_DEBUG=1, prints commands and stderr.
    """
    try:
        import os, re, subprocess
        from pathlib import Path
        from shutil import which

        t = "" if text is None else str(text)
        # strip common model tokens
        t = re.sub(r"<\|[^\|]*\|>", "", t).replace("<|end|>", "").replace("<|im_end|>", "").strip()
        if not t:
            return

        print(f"[ELI-VOICE] {t}")

        if os.environ.get("ELI_MUTE", "0") == "1":
            return

        env = os.environ.copy()
        sink = (env.get("ELI_OUTPUT_DEVICE") or "").strip()
        if sink:
            env["PULSE_SINK"] = sink

        debug = env.get("ELI_TTS_DEBUG", "0") == "1"
        tmpwav = Path(env.get("ELI_TTS_WAV", "/tmp/eli_tts.wav"))

        def run(cmd, *, input_text=None):
            if debug:
                print("[ELI-TTS] RUN:", cmd)
                if env.get("PULSE_SINK"):
                    print("[ELI-TTS] PULSE_SINK:", env["PULSE_SINK"])
            r = subprocess.run(cmd, input=input_text, text=(input_text is not None),
                               env=env, capture_output=True)
            if r.returncode != 0:
                print(f"[ELI-TTS] rc={r.returncode} cmd={' '.join(map(str,cmd))}")
                if r.stderr:
                    print("[ELI-TTS] stderr:", r.stderr.strip())
            return r

        def play(path: Path) -> bool:
            player = which("paplay") or which("pw-play") or which("aplay")
            if not player:
                print("[ELI-TTS] No audio player found (paplay/pw-play/aplay).")
                return False
            r = run([player, str(path)])
            return r.returncode == 0

        engine = (env.get("ELI_TTS_ENGINE") or "espeak").strip().lower()

        if engine == "piper":
            piper = which("piper")
            model = (env.get("ELI_PIPER_MODEL") or "").strip()
            if piper and model:
                r = run([piper, "--model", model, "--output_file", str(tmpwav)], input_text=t)
                if r.returncode == 0 and tmpwav.exists() and tmpwav.stat().st_size > 44:
                    if play(tmpwav):
                        return
                print("[ELI-TTS] Piper failed/empty -> falling back to espeak.")
            elif debug:
                print("[ELI-TTS] piper selected but missing piper binary or ELI_PIPER_MODEL -> falling back to espeak.")

        espeak = which("espeak-ng") or which("espeak")
        if not espeak:
            print("[ELI-TTS] espeak-ng/espeak not found in PATH.")
            return

        rate = (env.get("ELI_ESPEAK_RATE") or "175").strip()
        voice = (env.get("ELI_ESPEAK_VOICE") or "").strip()
        cmd = [espeak, "-s", rate]
        if voice:
            cmd += ["-v", voice]
        cmd += ["-w", str(tmpwav), t]

        r = run(cmd)
        if r.returncode != 0:
            return
        if not tmpwav.exists() or tmpwav.stat().st_size <= 44:
            print("[ELI-TTS] espeak produced invalid wav:", tmpwav)
            return
        play(tmpwav)

    except Exception as e:
        print("[ELI-TTS] exception:", repr(e))
        return


# --- TTS PATCH ---
import tempfile

# ---- Ollama host canonical config ----
OLLAMA_HOST = eli_config.ollama_base()
_OLLAMA_HOST = OLLAMA_HOST  # backward-compatible alias
CHAT_TIMEOUT_S = (10, 3600)  # connect/read timeout for Ollama chat


def _eli_set_pulse_sink():
    sink = (os.environ.get("ELI_OUTPUT_DEVICE") or "").strip()
    if sink:
        os.environ["PULSE_SINK"] = sink

def _eli_tts_echo(_text: str) -> None:
    # Always show what ELI *tries* to say, even if audio routing is cursed.
    try:
        if os.environ.get("ELI_TTS_ECHO", "1") != "0":
            print(f"[ELI-SAY] {_text}", flush=True)
        if os.environ.get("ELI_TTS_LOG", "1") != "0":
            from pathlib import Path
            import json
            from datetime import datetime
            root = Path(__file__).resolve().parent
            logp = root / "data" / "logs" / "tts.jsonl"
            logp.parent.mkdir(parents=True, exist_ok=True)
            rec = {"ts": datetime.now().isoformat(timespec="seconds"), "text": _text}
            with open(logp, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass

def _speak(text: str, *args, **kwargs):
    """Speak arbitrarily long text by chunking + sanitizing to avoid TTS silent failures."""
    import re as _re

    if text is None:
        return
    text = str(text)

    # Strip model junk tokens
    text = text.replace("<|end|>", "").replace("<|", "").replace("|>", "")

    # Remove/replace fenced code blocks (TTS engines often choke on them)
    text = _re.sub(r"```.*?```", " [code omitted] ", text, flags=_re.DOTALL)

    # Normalize whitespace
    text = _re.sub(r"[ \t]+", " ", text)
    text = _re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return

    # Chunk by sentence-ish boundaries, capped by char length
    MAX_CHARS = 350
    parts = _re.split(r"(?<=[.!?])\s+", text)
    buf = ""
    chunks = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if len(buf) + len(part) + 1 <= MAX_CHARS:
            buf = (buf + " " + part).strip()
        else:
            if buf:
                chunks.append(buf)
            # hard-split very long parts
            while len(part) > MAX_CHARS:
                chunks.append(part[:MAX_CHARS])
                part = part[MAX_CHARS:]
            buf = part
    if buf:
        chunks.append(buf)

    for c in chunks:
        _speak_raw(c, *args, **kwargs)

def _speak_raw(text: str) -> None:
    """Speak + ALWAYS echo transcript to terminal."""
    try:
        import os, subprocess, json
        from pathlib import Path
        from datetime import datetime
        t = ("" if text is None else str(text)).strip()
        if not t:
            return
        print(f"[ELI-SAY] {t}", flush=True)
        if os.environ.get("ELI_TTS_LOG", "1") != "0":
            try:
                root = Path(__file__).resolve().parent
                logp = root / "data" / "logs" / "tts.jsonl"
                logp.parent.mkdir(parents=True, exist_ok=True)
                rec = {"ts": datetime.now().isoformat(timespec="seconds"), "text": t}
                logp.open("a", encoding="utf-8").write(json.dumps(rec, ensure_ascii=False)+"\n")
            except Exception:
                pass
        if len(t.split()) > int(os.environ.get("ELI_TTS_MAX_WORDS", "80")):
            return
        if os.environ.get("ELI_MUTE", "0") == "1":
            return
        env = os.environ.copy()
        sink = env.get("ELI_OUTPUT_DEVICE", "").strip()
        if sink:
            env["PULSE_SINK"] = sink
        tmpwav = Path("/tmp/eli_tts.wav")
        engine = env.get("ELI_TTS_ENGINE", "espeak").strip().lower()
        if engine == "piper":
            model = env.get("ELI_PIPER_MODEL", "").strip()
            if model:
                piper_bin = os.environ.get("ELI_PIPER_BIN") or "piper"
                subprocess.run([piper_bin, "--model", model, "--output_file", str(tmpwav)], input=t, text=True, env=env)
                subprocess.Popen(["paplay",str(tmpwav)],env=env)
                return
        voice = env.get("ELI_ESPEAK_VOICE", "").strip()
        rate  = env.get("ELI_ESPEAK_RATE", "175").strip()
        cmd = ["espeak-ng","-s",rate]
        if voice: cmd += ["-v",voice]
        cmd += ["-w",str(tmpwav),t]
        subprocess.run(cmd,env=env)
        subprocess.Popen(["paplay",str(tmpwav)],env=env)
    except Exception:
        return


# --- PIPER TTS HOOK ---
def _eli_speak_piper(text: str):
    text = (text or "").strip()
    if not text:
        return

    piper_bin   = os.environ.get("ELI_PIPER_BIN", "piper")
    piper_model = os.path.expanduser(
        os.environ.get(
            "ELI_PIPER_MODEL",
            "~/piper_voices/en/en_US/amy/medium/en_US-amy-medium.onnx"
        )
    )
    player = os.environ.get("ELI_TTS_PLAYER", "paplay")

    fd, wav = tempfile.mkstemp(prefix="eli_tts_", suffix=".wav")
    os.close(fd)
    try:
        subprocess.run(
            [piper_bin, "--model", piper_model, "--output_file", wav],
            input=(text + "\n").encode("utf-8"),
            check=True
        )
        subprocess.run([player, wav], check=False)
    finally:
        try:
            os.unlink(wav)
        except OSError:
            pass

# Hook into speak function if piper is configured
try:
    _ELI_SPEAK_ORIG = _speak
    def _speak(text, *args, **kwargs):
        if os.environ.get("ELI_TTS_ENGINE", "").strip().lower() == "piper":
            return _eli_speak_piper(str(text))
        return _ELI_SPEAK_ORIG(text, *args, **kwargs)
except Exception:
    # If ELI changes its internals, fail gracefully instead of crashing startup
    pass


# --- UTILITY FUNCTIONS ---
def _slugify(name: str) -> str:
    name = (name or "doc").strip().lower()
    name = re.sub(r"[^a-z0-9]+", "_", name).strip("_")
    return name or "doc"

def _open_file(path: str) -> None:
    try:
        subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def _allowed_cmds_set():
    """
    Allowed executables for sandboxed run().
    Accept BOTH comma-separated and whitespace-separated formats.
    Also include both './x' and 'x' variants so normpath quirks don't brick you.
    """
    import os
    import os.path
    from pathlib import Path as _Path

    raw = (os.environ.get("ELI_ALLOWED_CMDS") or "").strip()
    if not raw:
        return None

    # commas OR spaces
    raw = raw.replace(",", " ")
    parts = [p for p in raw.split() if p]

    allowed = set()

    def add(tok: str):
        if not tok:
            return
        t = str(tok).strip()
        if not t:
            return

        # keep raw
        allowed.add(t)

        # normpath form
        try:
            n = os.path.normpath(t)
            allowed.add(n)
        except Exception:
            n = t

        # add "./" and no-"./" variants
        try:
            if n.startswith("./"):
                allowed.add(n[2:])
            else:
                allowed.add("./" + n)
        except Exception:
            pass

    for p in parts:
        add(p)

    # Always allow venv python in common forms (belt + suspenders)
    add("./.venv/bin/python")
    add(".venv/bin/python")
    try:
        add(str((_Path(__file__).resolve().parent.parent / ".venv/bin/python").resolve()))
    except Exception:
        pass

    return allowed

def _allow_or_block(argv0: str) -> bool:
    """Allow or block executables based on sandbox rules."""
    import os
    
    # FULL CONTROL MODE: allow everything
    if os.environ.get("ELI_FULL_CONTROL", "0") == "1":
        return True
    
    allowed = _allowed_cmds_set()
    if allowed is None:
        return True  # No restrictions
    
    # Wildcard allows everything
    if "*" in allowed:
        return True
    
    return argv0 in allowed

def _run_argv(argv, timeout=30):
    ### ELI_FASTFIX_BUNDLE_V2 ###
    # Normalize timeouts (router sometimes sends None)
    # None/"" => env ELI_RUN_TIMEOUT_SEC (default 120s)
    import os as _os
    if timeout is None or timeout == "":
        try:
            timeout = float(_os.environ.get("ELI_RUN_TIMEOUT_SEC", "120"))
        except Exception:
            timeout = 120.0
    else:
        try:
            timeout = float(timeout)
        except Exception:
            timeout = 120.0

    if not argv:
        return {"ok": False, "error": "empty argv"}
    if not _allow_or_block(argv[0]):

        # --- ALLOW_VENV_PYTHON_V1 ---
        # Normalize doubled venv paths and allow our own venv python binary under the allowlist sandbox.
        try:
            import os
            _v = str(argv[0])
            # collapse accidental duplication
            _v = _v.replace("./.venv/bin/./.venv/bin/python", "./.venv/bin/python")
            _v = _v.replace(".venv/bin/.venv/bin/python", ".venv/bin/python")
            _v = os.path.normpath(_v)
            # allow exactly the project venv python
            _venv_py_rel = os.path.normpath("./.venv/bin/python")
            _venv_py_abs = os.path.normpath(str((Path(__file__).resolve().parent / ".venv/bin/python")))
            if _v in (_venv_py_rel, _venv_py_abs) or _v.endswith("/.venv/bin/python"):
                # overwrite the checked value if it's a simple name
                if isinstance(argv[0], str):
                    argv[0] = _v
                # skip raising
                raise SystemExit("__ELI_ALLOW_VENV_PYTHON_SKIP__")
        except SystemExit as _e:
            if str(_e) == "__ELI_ALLOW_VENV_PYTHON_SKIP__":
                pass
            else:
                raise
        except Exception:
            pass

        # If we didn't early-allow venv python, fall through to the original denial.
        try:
            _ALLOW_VENV_PYTHON
        except NameError:
            _ALLOW_VENV_PYTHON = False
        if not _ALLOW_VENV_PYTHON:
            return {"ok": False, "error": f"command not allowed: {argv[0]} (ELI_ALLOWED_CMDS)"}

    try:
        r = subprocess.run(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            shell=False,
        )
        return {
            "ok": (r.returncode == 0),
            "returncode": r.returncode,
            "stdout": (r.stdout or "")[-2000:],
            "stderr": (r.stderr or "")[-2000:],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

def _spotify_player_name():
    # Pick a player name that actually exists (flatpak spotify usually exposes "spotify")
    r = _run_argv(["playerctl", "-l"], timeout=30)
    if r.get("ok") and r.get("stdout"):
        players = [p.strip() for p in r["stdout"].splitlines() if p.strip()]
        for p in players:
            if "spotify" in p.lower():
                return p
    return "spotify"

def _spotify_launch():
    """
    Launch Spotify and VERIFY it actually stays running.
    """
    SPOTIFY_CMD = os.environ.get("ELI_SPOTIFY_CMD", "").strip() or "spotify"
    argv = shlex.split(SPOTIFY_CMD)
    if not argv:
        return {"ok": False, "error": "ELI_SPOTIFY_CMD is empty"}

    if not _allow_or_block(argv[0]):
        return {"ok": False, "error": f"command not allowed: {argv[0]} (ELI_ALLOWED_CMDS)"}

    # If using Flatpak, verify the app exists/installed first.
    appid = None
    if len(argv) >= 3 and argv[0] == "flatpak" and argv[1] == "run":
        appid = argv[2]
        chk = subprocess.run(
            ["flatpak", "info", appid],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if chk.returncode != 0:
            return {
                "ok": False,
                "error": f"Flatpak app not installed or not available: {appid}",
                "stderr": (chk.stderr or "")[-2000:],
            }

    try:
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:
        return {"ok": False, "error": str(e), "cmd": argv}

    # Give it a moment, then verify it's actually running.
    time.sleep(1.8)

    running = False
    evidence = {}

    # Prefer flatpak ps if we're launching flatpak
    if appid:
        ps = subprocess.run(
            ["flatpak", "ps"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        evidence["flatpak_ps_rc"] = ps.returncode
        evidence["flatpak_ps_tail"] = (ps.stdout or "")[-4000:]
        if ps.returncode == 0 and appid in (ps.stdout or ""):
            running = True
    else:
        # Fallback: check playerctl list (best-effort)
        r = _run_argv(["playerctl", "-l"], timeout=30)
        evidence["playerctl"] = r
        if r.get("ok") and "spotify" in (r.get("stdout","").lower()):
            running = True

    return {
        "ok": bool(running),
        "launched": True,
        "running": bool(running),
        "pid": getattr(proc, "pid", None),
        "cmd": argv,
        "evidence": evidence,
    }

def _spotify_ctl(command: str, auto_launch: bool = True):
    """
    command: play|pause|stop|status|next|previous|play-pause
    """
    player = _spotify_player_name()
    r = _run_argv(["playerctl", "-p", player, command], timeout=30)

    # If play fails because spotify isn't running/registered, optionally launch and retry
    if (not r.get("ok")) and auto_launch and command in {"play", "play-pause"}:
        launch = _spotify_launch()
        time.sleep(2)
        player = _spotify_player_name()
        r2 = _run_argv(["playerctl", "-p", player, command], timeout=30)
        return {"ok": r2.get("ok", False), "launch": launch, "result": r2, "player": player}

    return {"ok": r.get("ok", False), "result": r, "player": player}


# --- APP OPENING FUNCTIONS ---
_APP_ALIASES = {
    "mail": "thunderbird",
    "email": "thunderbird",
    "e-mail": "thunderbird",
    "thunderbird": "thunderbird",
    "thunderbirds": "thunderbird",
    "thunder birds": "thunderbird",
    "tundra bird": "thunderbird",
    "tundrabird": "thunderbird",
    "browser": "firefox",
    "mozilla": "firefox",
    "firefox": "firefox",
}

def _normalize_app(spoken: str) -> str:
    """Normalize application names using aliases."""
    s = (spoken or "").strip().lower()
    s = " ".join(s.split())
    return _APP_ALIASES.get(s, s)

def _allowed_apps_set():
    """Return set of allowed apps, or None for no restrictions."""
    import os
    
    # FULL CONTROL MODE: no app restrictions
    if os.environ.get("ELI_FULL_CONTROL", "0") == "1":
        return None
    
    raw = (os.environ.get("ELI_ALLOWED_APPS") or "").strip()
    if not raw:
        return None  # None => allow common safe apps
    return {x.strip().lower() for x in raw.split(",") if x.strip()}

def _open_app_with_timeout(argv, timeout=30):
    # ELI_OPEN_APP_SPAWN_PATCH_v3
    # GUI apps shouldn't be waited on. Spawn + return success unless it exits immediately with error.
    import subprocess
    try:
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True
        )
        try:
            out, err = proc.communicate(timeout=0.7)
            return {"ok": (proc.returncode == 0), "returncode": proc.returncode, "stdout": out, "stderr": err, "argv": argv}
        except subprocess.TimeoutExpired:
            return {"ok": True, "spawned": True, "pid": proc.pid, "argv": argv}
    except Exception as e:
        return {"ok": False, "error": repr(e), "argv": argv}

def _open_app_builtin(app_name: str) -> dict:
    app = _normalize_app(app_name)
    if not app:
        return {"ok": False, "error": "empty app_name"}

    allowed = _allowed_apps_set()
    if allowed is not None and app not in allowed:
        return {"ok": False, "error": f"app not allowed: {app} (set ELI_ALLOWED_APPS)"}

    # Allow per-app override command
    env_key = "ELI_APP_CMD_" + re.sub(r"[^A-Z0-9]+", "_", app.upper())
    override = (os.environ.get(env_key) or "").strip()

    if override:
        argv = shlex.split(override)
    else:
        # sensible defaults
        if app == "thunderbird":
            argv = ["thunderbird"]
        elif app == "firefox":
            argv = ["firefox"]
        elif app == "spotify":
            SPOTIFY_CMD = os.environ.get("ELI_SPOTIFY_CMD", "").strip() or "spotify"
            argv = shlex.split(SPOTIFY_CMD) if SPOTIFY_CMD else ["spotify"]
        else:
            # last resort: try running by name
            argv = [app]

    try:
        return _open_app_with_timeout(argv)
    except Exception as e:
        return {"ok": False, "error": str(e), "app": app, "cmd": argv}


# --- BUILTIN DOCUMENT FUNCTIONS ---
def _builtin_create_doc(args: dict) -> dict:
    try:
        doc_type  = (args.get("doc_type") or "txt").strip().lower()
        title     = (args.get("title") or "document").strip()
        content   = args.get("content") or ""
        filename  = (args.get("filename") or "").strip()
        convert_to = (args.get("convert_to") or "omit").strip().lower()
        open_after = bool(args.get("open_after", False))

        ext = doc_type if doc_type in {"md","txt","tex"} else "txt"

        outdir = Path(os.environ.get("ELI_DOC_DIR", str(Path(__file__).resolve().parent.parent / "eli_docs"))).expanduser()
        outdir.mkdir(parents=True, exist_ok=True)

        if filename:
            fn = filename if filename.endswith(f".{ext}") else filename + f".{ext}"
        else:
            fn = _slugify(title) + f".{ext}"

        outpath = outdir / fn
        outpath.write_text(content, encoding="utf-8")

        if open_after:
            _open_file(str(outpath))

        return {"ok": True, "path": str(outpath)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _write_note_builtin(args: dict) -> dict:
    """Create a note file under ELI_DOC_DIR (default: ./eli_docs)."""
    try:
        title = (args.get("title") or "note").strip()
        content = (args.get("content") or "").strip()
        filename = (args.get("filename") or "").strip()
        open_after = bool(args.get("open_after", False))

        import os, re, time, subprocess
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        doc_dir = Path(os.environ.get("ELI_DOC_DIR", str(root / "eli_docs"))).expanduser()
        doc_dir.mkdir(parents=True, exist_ok=True)

        if not filename:
            safe_title = re.sub(r"[^a-zA-Z0-9_\-\.]+", "_", title).strip("_") or "note"
            filename = f"{safe_title}.md"
        if not filename.lower().endswith((".md", ".txt")):
            filename += ".md"

        if not content:
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            content = f"# {title}\n\nCreated: {ts}\n\n"

        path = (doc_dir / filename).resolve()
        doc_dir_resolved = doc_dir.resolve()
        if path != doc_dir_resolved and doc_dir_resolved not in path.parents:
            return {"ok": False, "error": "refusing to write outside ELI_DOC_DIR"}

        path.write_text(content, encoding="utf-8")

        if open_after:
            try:
                subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

        return {"ok": True, "path": str(path), "title": title}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _append_note_builtin(args: dict) -> dict:
    """Append content to a note under ELI_DOC_DIR."""
    try:
        title = (args.get("title") or "").strip()
        content = (args.get("content") or "").strip()
        filename = (args.get("filename") or "").strip()
        open_after = bool(args.get("open_after", False))

        if not title and not filename:
            return {"ok": False, "error": "append_note: title or filename is required"}
        if not content:
            return {"ok": False, "error": "append_note: content is empty"}

        import os, re, time, subprocess
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        doc_dir = Path(os.environ.get("ELI_DOC_DIR", str(root / "eli_docs"))).expanduser()
        doc_dir.mkdir(parents=True, exist_ok=True)

        note_file = None
        if filename:
            note_file = (doc_dir / filename)
        else:
            if title.lower().endswith((".md", ".txt")):
                note_file = (doc_dir / title)
            else:
                for ext in (".md", ".txt"):
                    cand = doc_dir / f"{title}{ext}"
                    if cand.exists():
                        note_file = cand
                        break
                if note_file is None:
                    safe_title = re.sub(r"[^a-zA-Z0-9_\-\.]+", "_", title).strip("_") or "note"
                    note_file = doc_dir / f"{safe_title}.md"

        note_file = note_file.resolve()
        doc_dir_resolved = doc_dir.resolve()
        if note_file != doc_dir_resolved and doc_dir_resolved not in note_file.parents:
            return {"ok": False, "error": "refusing to write outside ELI_DOC_DIR"}

        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        blob = f"\n\n---\n\n{ts}\n\n{content.strip()}\n"

        if note_file.exists():
            prev = note_file.read_text(encoding="utf-8", errors="ignore")
        else:
            prev = f"# {title or note_file.stem}\n"

        note_file.write_text(prev.rstrip() + blob, encoding="utf-8")

        if open_after:
            try:
                subprocess.Popen(["xdg-open", str(note_file)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

        return {"ok": True, "path": str(note_file), "title": title or note_file.stem}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _calendar_event_builtin(args: dict) -> dict:
    """Open a prefilled Google Calendar event in the browser (handles 'tomorrow', weekdays, 2pm, 16.40pm, etc.)."""
    try:
        import re, urllib.parse, subprocess, os
        from datetime import datetime, date, timedelta

        title = (args.get("title") or "ELI Event").strip()
        date_s = (args.get("date") or args.get("day") or "").strip()
        time_s = (args.get("time") or args.get("at") or "").strip()
        start_s = (args.get("start") or "").strip()
        location = (args.get("location") or "").strip()
        notes = (args.get("notes") or args.get("details") or "").strip()

        dur = args.get("duration_min", None)
        if dur is None:
            dur = args.get("duration", None)
        try:
            duration_min = int(dur) if dur is not None else 30
        except Exception:
            duration_min = 30

        def parse_time(ts: str) -> str:
            if not ts:
                return "09:00"
            t = ts.strip().lower().replace(" ", "")
            t = t.replace(".", ":")
            m = re.match(r'^(\d{1,2})(?::(\d{2}))?(am|pm)?$', t)
            if not m:
                return "09:00"
            hh = int(m.group(1))
            mm = int(m.group(2) or "0")
            ap = m.group(3)
            # If already 13-23, ignore am/pm even if user says nonsense like 16:40pm
            if ap and hh <= 12:
                if ap == "pm" and hh < 12: hh += 12
                if ap == "am" and hh == 12: hh = 0
            hh = max(0, min(23, hh))
            mm = max(0, min(59, mm))
            return f"{hh:02d}:{mm:02d}"

        def parse_date(ds: str) -> str:
            today = date.today()
            if not ds:
                return today.isoformat()
            d = ds.strip().lower()
            wmap = {"monday":0,"tuesday":1,"wednesday":2,"thursday":3,"friday":4,"saturday":5,"sunday":6}
            if d == "today":
                return today.isoformat()
            if d == "tomorrow":
                return (today + timedelta(days=1)).isoformat()
            if d in wmap:
                delta = (wmap[d] - today.weekday()) % 7
                delta = 7 if delta == 0 else delta
                return (today + timedelta(days=delta)).isoformat()
            # ISO date?
            if re.match(r'^\d{4}-\d{2}-\d{2}$', ds.strip()):
                return ds.strip()
            return today.isoformat()

        dt = None
        if start_s:
            # try iso-ish start string
            try:
                dt = datetime.fromisoformat(start_s.replace("Z",""))
            except Exception:
                # salvage "tomorrowT14:00" style
                if "T" in start_s:
                    left, right = start_s.split("T", 1)
                    date_s2 = parse_date(left)
                    time_s2 = parse_time(right)
                    dt = datetime.fromisoformat(f"{date_s2}T{time_s2}")

        if dt is None:
            d_iso = parse_date(date_s)
            t_hm = parse_time(time_s)
            dt = datetime.fromisoformat(f"{d_iso}T{t_hm}")

        end_dt = dt + timedelta(minutes=duration_min)

        def fmt(d: datetime) -> str:
            return d.strftime("%Y%m%dT%H%M%S")

        params = {
            "action": "TEMPLATE",
            "text": title,
            "dates": f"{fmt(dt)}/{fmt(end_dt)}",
        }
        if location:
            params["location"] = location
        if notes:
            params["details"] = notes

        # timezone offset (local)
        import time as _time
        tz_offset = _time.localtime().tm_gmtoff
        tz_sign = "+" if tz_offset >= 0 else "-"
        tz_hours = abs(tz_offset) // 3600
        tz_minutes = (abs(tz_offset) % 3600) // 60
        params["ctz"] = f"UTC{tz_sign}{tz_hours:02d}:{tz_minutes:02d}"

        base_url = "https://calendar.google.com/calendar/render"
        url = f"{base_url}?{urllib.parse.urlencode(params)}"
        subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        return {"ok": True, "title": title, "start": dt.isoformat(), "end": end_dt.isoformat(),
                "duration_min": duration_min, "url": url}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _recall_memory_builtin(args: dict) -> dict:
    """Read recent utterances from ./data/memory/utterances.jsonl (if present)."""
    try:
        import json
        from pathlib import Path

        limit = int(args.get("limit", 20))
        root = Path(__file__).resolve().parent.parent
        memory_log = root / "data" / "memory" / "utterances.jsonl"

        if not memory_log.exists():
            return {"ok": True, "entries": [], "message": "No memory log found"}

        entries = []
        with open(memory_log, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        recent = entries[-limit:] if entries else []
        return {"ok": True, "entries": recent, "count": len(recent), "total": len(entries)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _type_text_builtin(text: str) -> dict:
    text = (text or "")
    if not text:
        return {"ok": False, "error": "empty text"}

    sess = (os.environ.get("XDG_SESSION_TYPE") or "").lower().strip()

    if sess == "wayland":
        # wtype types into the focused window on Wayland
        argv = ["wtype", "--", text]
        return _run_argv(argv, timeout=30)

    # X11 fallback
    argv = ["xdotool", "type", "--clearmodifiers", "--delay", "8", text]
    return _run_argv(argv, timeout=30)


# --- NOTIFICATION FUNCTION ---
def _notify(title: str, msg: str):
    try:
        if os.environ.get("ELI_NOTIFY", "1") == "1":
            os.system(f'notify-send "{title}" "{msg}" >/dev/null 2>&1')
        if os.environ.get("ELI_VOICE_DEBUG", "0") == "1":
            print(f"[NOTIFY] {title}: {msg}")
    except Exception:
        if os.environ.get("ELI_VOICE_DEBUG", "0") == "1":
            print(f"[NOTIFY] {title}: {msg}")


# ----------------------------
# Dispatcher
# ----------------------------

def _execute_impl(action: str, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    args = args or {}
    # Normalize action for dispatch (accept open_app, OPEN_APP, open-app, etc.)
    a = (str(action) if action is not None else "").strip()
    a = re.sub(r"[\s\-]+", "_", a)
    a = a.upper()

    if a == "CHAT":
        msg = args.get("message") or args.get("prompt") or args.get("text") or ""
        model = args.get("model") or None
        return chat(str(msg), model=model)

    # Persistent memory
    if a == "MEMORY_STORE":
        # --- txt normalization ---
        txt = str(args.get("text") or args.get("content") or args.get("message") or "").strip()
        if not txt:
            return {"ok": False, "action": a, "error": "empty_text", "content": "empty_text", "response": "empty_text"}

        # --- tags normalization ---
        tags = args.get("tags", [])
        if isinstance(tags, str):
            tags = [x.strip() for x in tags.split(",") if x.strip()]
        elif isinstance(tags, (tuple, set)):
            tags = [str(x).strip() for x in tags if str(x).strip()]
        elif not isinstance(tags, list):
            tags = []

        # 1) Preferred: brain.memory_adapter.memory_store (SQLite path)
        try:
            from eli.brain.memory_adapter import memory_store as adapter_store
            result = adapter_store(txt, tags=tags)
            if isinstance(result, dict):
                result.setdefault("action", a)
                result.setdefault("ok", True)
                result.setdefault("content", result.get("content") or "memory stored")
                result.setdefault("response", result.get("response") or result["content"])
            return result
        except Exception:
            pass

        # 2) Fallback: brain.memory.memory_db.add_memory (SQLite path)
        try:
            from eli.brain.memory.memory_db import add_memory
            add_memory(txt, tags=",".join(tags) if isinstance(tags, list) else str(tags))
            msg = "memory stored"
            return {"ok": True, "action": a, "content": msg, "response": msg}
        except Exception:
            pass

        # 3) Last resort: local JSONL memory_store() (if present in this module)
        try:
            result = memory_store(txt, tags=tags)
            if isinstance(result, dict):
                result.setdefault("action", a)
                result.setdefault("ok", True)
                result.setdefault("content", result.get("content") or "memory stored")
                result.setdefault("response", result.get("response") or result["content"])
            return result
        except Exception as e:
            return {"ok": False, "action": a, "error": str(e), "content": str(e), "response": str(e)}
    
    # --- media control ---
    if a == "STOP_MEDIA":
        return stop_media()
    
    if a == "PAUSE_MEDIA":
        return pause_media()
    
    if a == "PLAY_MEDIA":
        return play_media()
    
    if a == "NEXT_MEDIA":
        return next_media()
    
    if a == "PREVIOUS_MEDIA":
        return previous_media()

    # ---- DISPATCH PATCH: CORE + PROACTIVE ACTIONS ----
    # NOTE: Capabilities can be "registered" without being "implemented".
    # This block ensures the common actions actually route to real code.

    # ---- TIME ----
    if a in ("TIME", "GET_TIME"):
        from datetime import datetime
        now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return {"ok": True, "action": a, "content": now_text, "response": now_text}

    # ---- HELP / LIST_CAPABILITIES ----
    if a in ("HELP", "LIST_CAPABILITIES"):
        try:
            from eli.tools.capability_registry import list_capabilities
            caps = list_capabilities()

            if a == "HELP":
                # Build a readable help text from capabilities list
                lines = ["ELI Capabilities:"]
                for c in (caps if isinstance(caps, list) else []):
                    name = c.get("canonical") or c.get("name") or "?"
                    desc = c.get("description") or ""
                    lines.append(f"  {name}: {desc}" if desc else f"  {name}")
                txt = "\n".join(lines)
                return {"ok": True, "action": a, "content": txt, "response": txt}

            # --- Normalize shape for callers/tests ---
            # capability_registry may return either:
            #   - list[{"action":..., "desc":...}, ...]
            #   - dict {"ok":True,"format":"json","capabilities":[...],"content":"|...table...|"}
            caps_list = None
            table = ""
            if isinstance(caps, dict):
                maybe = caps.get("capabilities")
                if isinstance(maybe, list):
                    caps_list = maybe
                table = str(caps.get("content") or "").strip()
            elif isinstance(caps, list):
                caps_list = caps

            if caps_list is None:
                # Worst-case: fall back to empty list but don't explode
                caps_list = []

            # Prefer table in content/response if available, else a small summary
            if table:
                content = table
            else:
                content = f"{len(caps_list)} capabilities"

            return {"ok": True, "action": a, "capabilities": caps_list, "content": content, "response": content}
        except Exception as e:
            return {"ok": False, "action": a, "error": f"capabilities error: {e}", "content": f"capabilities error: {e}", "response": f"capabilities error: {e}"}


    # ---- READ_FILE ----
    if a == "READ_FILE":
        try:
            from pathlib import Path as _Path
            path = (args or {}).get("path") or (args or {}).get("file") or ""
            path = str(path).strip()
            if not path:
                return {"ok": False, "action": a, "error": "Missing path", "content": "Missing path", "response": "Missing path"}
            pp = _Path(path).expanduser()
            if not pp.is_absolute():
                pp = (_Path.cwd() / pp).resolve()
            data = pp.read_text(encoding="utf-8", errors="replace")
            return {"ok": True, "action": a, "path": str(pp), "content": data, "response": data}
        except Exception as e:
            return {"ok": False, "action": a, "error": str(e), "content": str(e), "response": str(e)}

    # ---- WRITE_NOTE ----
    if a == "WRITE_NOTE":
        try:
            from pathlib import Path as _Path
            import time as _time
            txt = (args or {}).get("text") or (args or {}).get("content") or ""
            txt = str(txt)
            from eli.brain.paths import PATHS
            root = (args or {}).get("root")
            nb = (_Path(root) / "eli_notebook") if root else _Path(PATHS.notes_dir)
            nb.mkdir(parents=True, exist_ok=True)
            fn = nb / f"{_time.strftime('%Y-%m-%d')}.md"
            with fn.open("a", encoding="utf-8") as f:  # one file per day, notes added in order
                f.write(txt.rstrip("\n") + "\n\n")
            msg = f"Wrote note: {fn}"
            return {"ok": True, "action": a, "path": str(fn), "content": msg, "response": msg}
        except Exception as e:
            return {"ok": False, "action": a, "error": str(e), "content": str(e), "response": str(e)}

    # ---- OPEN_URL ----
    if a == "OPEN_URL":
        try:
            url = (args or {}).get("url") or ""
            url = str(url).strip()
            if not url:
                return {"ok": False, "action": a, "error": "Missing url", "content": "Missing url", "response": "Missing url"}
            subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            msg = f"Opened URL: {url}"
            return {"ok": True, "action": a, "content": msg, "response": msg}
        except Exception as e:
            return {"ok": False, "action": a, "error": str(e), "content": str(e), "response": str(e)}

    # ---- OPEN_APP ----
    if a == "OPEN_APP":
        try:
            name = (args or {}).get("name") or (args or {}).get("app") or ""
            name = str(name).strip()
            if not name:
                return {"ok": False, "action": a, "error": "Missing app name", "content": "Missing app name", "response": "Missing app name"}

            # Fuzzy / spelling correction map
            _APP_FUZZY = {
                "calender": "gnome-calendar", "calander": "gnome-calendar",
                "calendar": "gnome-calendar", "calandar": "gnome-calendar",
                "settings": "gnome-control-center", "setting": "gnome-control-center",
                "files": "nautilus", "file manager": "nautilus",
                "text editor": "gedit", "editor": "gedit",
                "calculator": "gnome-calculator", "calc": "gnome-calculator",
                "terminal": "gnome-terminal", "term": "gnome-terminal",
                "monitor": "gnome-system-monitor", "system monitor": "gnome-system-monitor",
                "music": "rhythmbox", "photos": "eog", "image viewer": "eog",
                "screenshot": "gnome-screenshot", "screen recorder": "obs",
                "disk usage": "baobab", "disks": "gnome-disks",
            }

            app = _APP_FUZZY.get(name.lower(), name)
            subprocess.Popen([app], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            msg = f"Opened app: {app}"
            return {"ok": True, "action": a, "content": msg, "response": msg}
        except Exception as e:
            return {"ok": False, "action": a, "error": str(e), "content": str(e), "response": str(e)}

    # ---- RUN_CMD ----
    if a == "RUN_CMD":
        try:
            cmd = args.get("cmd") or args.get("command") or ""
            cwd = args.get("cwd") or None
            timeout = int(args.get("timeout", 30))
            shell = bool(args.get("shell", False))

            # Accept both ["ls", "/path"] and "ls /path"
            if isinstance(cmd, (list, tuple)):
                cmd_list = [str(x) for x in cmd if str(x).strip() != ""]
                if not cmd_list:
                    return {"ok": False, "action": a, "error": "empty_cmd", "content": "", "response": ""}
                p = subprocess.run(
                    cmd_list,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    shell=False,
                )
            else:
                cmd_str = str(cmd).strip()
                if not cmd_str:
                    return {"ok": False, "action": a, "error": "empty_cmd", "content": "", "response": ""}
                # Default: run through shell for string commands unless explicitly disabled
                if shell:
                    p = subprocess.run(
                        cmd_str,
                        cwd=cwd,
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                        shell=True,
                        executable="/bin/sh",
                    )
                else:
                    import shlex
                    p = subprocess.run(
                        shlex.split(cmd_str),
                        cwd=cwd,
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                        shell=False,
                    )

            out = (p.stdout or "") + (p.stderr or "")
            return {"ok": p.returncode == 0, "action": a, "code": p.returncode, "content": out, "response": out}
        except Exception as e:
            return {"ok": False, "action": a, "error": str(e), "content": str(e), "response": str(e)}
    
    # ---- PROACTIVE (start/stop/status) ----
    if a == "PROACTIVE_STATUS":
        try:
            st = proactive_status()
            return {"ok": True, "action": a, **st, "content": str(st), "response": str(st)}
        except Exception as e:
            return {"ok": False, "action": a, "error": str(e), "content": str(e), "response": str(e)}

    if a == "PROACTIVE_START":
        try:
            st = proactive_start()
            return {"ok": True, "action": a, **st, "content": "proactive started", "response": "proactive started"}
        except Exception as e:
            return {"ok": False, "action": a, "error": str(e), "content": str(e), "response": str(e)}

    if a == "PROACTIVE_STOP":
        try:
            st = proactive_stop()
            return {"ok": True, "action": a, **st, "content": "proactive stopped", "response": "proactive stopped"}
        except Exception as e:
            return {"ok": False, "action": a, "error": str(e), "content": str(e), "response": str(e)}

    # ---- MEMORY_RECALL ----
    if a == "MEMORY_RECALL":
        q = str(args.get("query", "")).strip()
        try:
            lim = int(args.get("limit", 5))
        except Exception:
            lim = 5

        if not q:
            return {"ok": False, "action": a, "error": "empty_query", "content": "empty_query", "response": "empty_query"}

        # 1) Preferred: brain.memory_adapter.memory_search (SQLite path)
        try:
            from eli.brain.memory_adapter import memory_search
            result = memory_search(q, k=lim)
            # Ensure consistent envelope
            if isinstance(result, dict):
                result.setdefault("action", a)
                result.setdefault("ok", True)
                if "content" not in result:
                    # memory_adapter may return 'results' (common) or 'hits' (legacy).
                    hits = result.get("results")
                    if hits is None:
                        hits = result.get("hits")
                    if hits is None:
                        hits = result.get("items")
                    if hits is None:
                        hits = []
                    content = ""
                    if isinstance(hits, list) and hits:
                        # Friendly readable render (top-k)
                        lines = []
                        for h in hits:
                            if not isinstance(h, dict):
                                continue
                            t = (h.get("text") or "").strip()
                            if not t:
                                continue
                            score = h.get("score", None)
                            tags = h.get("tags", "")
                            if score is not None:
                                try:
                                    lines.append(f"- ({float(score):.3f}) {t} [{tags}]")
                                except Exception:
                                    lines.append(f"- {t} [{tags}]")
                            else:
                                lines.append(f"- {t} [{tags}]")
                        content = "\n".join(lines).strip()
                    result["content"] = content or "Memory recall:\n(no matches)"
                    # Also expose a consistent 'hits' key for any callers expecting it.
                    if "hits" not in result:
                        result["hits"] = hits
                result.setdefault("response", result.get("response") or result["content"])
            return result
        except Exception:
            pass

        # 2) Fallback: brain.memory.memory_db.search_memory (SQLite path)
        try:
            from eli.brain.memory.memory_db import search_memory
            hits = search_memory(q) or []
            content = "\n".join((h.get("text", "") or "") for h in hits) if isinstance(hits, list) else "Memory recall:\n(no matches)"
            if not content.strip():
                content = "Memory recall:\n(no matches)"
            return {"ok": True, "action": a, "hits": hits, "content": content, "response": content}
        except Exception as e:
            return {"ok": False, "action": a, "error": str(e), "content": str(e), "response": str(e)}

    # Quick commands
    if a == "CHECK_CHRONAL_ALIGNMENT":
        msg = f"Chronal alignment nominal. Local time: {time.strftime('%H:%M:%S')}."
        return {"ok": True, "action": a, "content": msg, "response": msg}

    if a == "OPEN_FILE_SYSTEM":
        path = str(args.get("path") or "~")
        return open_file_system(path)
    
    if a == "OPEN_COMMUNICATION_HUB":
        try:
            # Prefer local mail clients; fall back to Gmail in browser.
            candidates = [
                ["thunderbird"],
                ["evolution"],
                ["geary"],
            ]
            for cmd in candidates:
                try:
                    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    msg = f"Opened Communication Hub: {' '.join(cmd)}"
                    return {"ok": True, "action": a, "content": msg, "response": msg}
                except FileNotFoundError:
                    continue
            url = "https://mail.google.com"
            open_browser(url)
            msg = f"Opened Communication Hub: {url}"
            return {"ok": True, "action": a, "content": msg, "response": msg}
        except Exception as e:
            return {"ok": False, "action": a, "error": str(e), "content": str(e), "response": str(e)}
    
    if a == "DATA_FABRICATOR":
        try:
            # If a topic/prompt is provided, generate a document first then open it.
            topic = str((args or {}).get("topic") or (args or {}).get("query") or (args or {}).get("text") or (args or {}).get("message") or "").strip()
            if topic:
                r = _execute_impl(action="DOC_GENERATE", args={"topic": topic, "format": (args or {}).get("format") or "md"})
                # If generation succeeded, also open in an editor if available
                if r.get("ok") and r.get("path"):
                    path = r.get("path")
                    editors = [
                        ["code", path],
                        ["codium", path],
                        ["gedit", path],
                        ["kate", path],
                        ["nano", path],
                    ]
                    for cmd in editors:
                        try:
                            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            break
                        except FileNotFoundError:
                            continue
                return r

            # Otherwise just open an editor for a new blank file.
            from eli.brain.paths import PATHS
            out_dir = Path(PATHS.artifacts_dir).resolve()
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"data_construct_{int(time.time())}.md"
            if not out_path.exists():
                out_path.write_text("# Data Construct\n\n", encoding="utf-8")

            editors = [
                ["code", str(out_path)],
                ["codium", str(out_path)],
                ["gedit", str(out_path)],
                ["libreoffice", "--writer", str(out_path)],
            ]
            for cmd in editors:
                try:
                    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    msg = f"Opened editor: {' '.join(cmd)}"
                    return {"ok": True, "action": a, "path": str(out_path), "content": msg, "response": msg}
                except FileNotFoundError:
                    continue

            # Fallback: open with default system handler
            subprocess.Popen(["xdg-open", str(out_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            msg = f"Opened file: {out_path}"
            return {"ok": True, "action": a, "path": str(out_path), "content": msg, "response": msg}
        except Exception as e:
            return {"ok": False, "action": a, "error": str(e), "content": str(e), "response": str(e)}

    if a == "OPEN_AUDIO_SETTINGS":
        try:
            # Try common Linux audio mixers/settings panels.
            candidates = [
                ["pavucontrol"],
                ["gnome-control-center", "sound"],
                ["gnome-control-center"],
                ["systemsettings5", "kcm_pulseaudio"],
                ["systemsettings5"],
                ["kcmshell5", "kcm_pulseaudio"],
                ["mate-volume-control"],
                ["xfce4-mixer"],
            ]
            for cmd in candidates:
                try:
                    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    msg = f"Opened audio settings: {' '.join(cmd)}"
                    return {"ok": True, "action": a, "content": msg, "response": msg}
                except FileNotFoundError:
                    continue
            raise FileNotFoundError("No audio settings app found (pavucontrol / gnome-control-center / systemsettings5 / etc).")
        except Exception as e:
            return {"ok": False, "action": a, "error": str(e), "content": str(e), "response": str(e)}

    if a == "OPEN_BROWSER":
        url = str(args.get("url") or args.get("link") or "https://duckduckgo.com")
        return open_browser(url)

    if a == "OPEN_NETWORK_BROWSER":
        try:
            url = str((args or {}).get("url") or "https://duckduckgo.com").strip()
            open_browser(url)
            msg = f"Opened Network Browser: {url}"
            return {"ok": True, "action": a, "content": msg, "response": msg}
        except Exception as e:
            return {"ok": False, "action": a, "error": str(e), "content": str(e), "response": str(e)}

    if a == "OPEN_MEDIA_HUB":
        try:
            # Try Spotify client first; otherwise open YouTube Music; otherwise open local Music folder.
            opened = False
            # Optional: also open audio settings (requested by voice phrase "initiate audio interface")
            if (args or {}).get("open_settings"):
                try:
                    _ = _execute_impl(action="OPEN_AUDIO_SETTINGS", args={})
                except Exception:
                    pass

            candidates = [
                ["spotify"],
                ["flatpak", "run", "com.spotify.Client"],
            ]
            for cmd in candidates:
                try:
                    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    opened = True
                    msg = f"Opened media: {' '.join(cmd)}"
                    return {"ok": True, "action": a, "content": msg, "response": msg}
                except FileNotFoundError:
                    continue

            # Browser fallbacks
            try:
                url = "https://music.youtube.com"
                open_browser(url)
                msg = f"Opened media: {url}"
                return {"ok": True, "action": a, "content": msg, "response": msg}
            except Exception:
                pass

            # Local folder fallback
            try:
                music_dir = os.path.expanduser("~/Music")
                open_file_system(music_dir)
                msg = f"Opened media folder: {music_dir}"
                return {"ok": True, "action": a, "content": msg, "response": msg}
            except Exception as e:
                raise e
        except Exception as e:
            return {"ok": False, "action": a, "error": str(e), "content": str(e), "response": str(e)}

    if a in ("DOC_GENERATE", "CREATE_DOCUMENT"):
        try:
            topic = str((args or {}).get("topic") or (args or {}).get("query") or (args or {}).get("text") or (args or {}).get("message") or "").strip()
            if not topic:
                return {"ok": False, "action": a, "error": "missing_topic", "content": "Missing topic.", "response": "Missing topic."}

            fmt = str((args or {}).get("format") or "md").strip().lower()
            if fmt in ("markdown", "md"):
                ext = "md"
            elif fmt in ("txt", "text"):
                ext = "txt"
            elif fmt in ("html",):
                ext = "html"
            else:
                ext = "md"

            from eli.brain.paths import PATHS
            out_dir = Path(os.path.expanduser((args or {}).get("out_dir") or str(PATHS.artifacts_dir))).resolve()
            out_dir.mkdir(parents=True, exist_ok=True)
            safe = re.sub(r"[^a-zA-Z0-9_\-]+", "_", topic.strip())[:60] or "document"
            out_path = out_dir / f"{safe}_{int(time.time())}.{ext}"

            # Ask the chat model to write the document content (local Ollama) if available.
            prompt = (
                "Write a clean, structured document for a general intelligent reader.\n"
                f"Topic: {topic}\n\n"
                "Requirements:\n"
                "- Use headings and short paragraphs\n"
                "- Include key facts, definitions, and examples\n"
                "- End with a short 'Further Questions' section\n"
                "- No fluff.\n"
            )

            content = None
            try:
                # Use chat function
                r = chat(prompt)
                # Expect dict with 'content' or string
                if isinstance(r, dict):
                    content = r.get("content") or r.get("response") or r.get("text")
                elif isinstance(r, str):
                    content = r
            except Exception:
                content = None

            if not content:
                # Fallback: minimal stub-free local document scaffold
                content = f"# {topic}\n\n(LLM content unavailable. This is a placeholder scaffold.)\n\n## Summary\n\n## Key Points\n\n## Examples\n\n## Further Questions\n"

            if ext == "html":
                body = content
                if not body.lstrip().lower().startswith("<"):
                    body = "<pre>" + (content.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")) + "</pre>"
                content_to_write = "<!doctype html><html><head><meta charset='utf-8'><title>" + topic + "</title></head><body>" + body + "</body></html>"
            else:
                content_to_write = content

            out_path.write_text(content_to_write, encoding="utf-8")
            # Open with default app
            try:
                subprocess.Popen(["xdg-open", str(out_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

            msg = f"Document created: {out_path}"
            return {"ok": True, "action": a, "path": str(out_path), "content": msg, "response": msg}
        except Exception as e:
            return {"ok": False, "action": a, "error": str(e), "content": str(e), "response": str(e)}

    if a == "PERSONA_LOCK_SET":
        model = args.get("model") or None
        modelfile = args.get("modelfile_path") or args.get("modelfile") or None
        return persona_lock_set(model=model, modelfile_path=modelfile)

    if a == "PERSONA_LOCK_STATUS":
        return persona_lock_status()

    if a == "PERSONA_LOCK_CLEAR":
        return persona_lock_clear()

    if a == "SELF_TEST":
        return self_test()

    if a == "SET_USER_NAME":
        return set_user_name(str(args.get("name", "")))

    if a == "GET_STATUS":
        return get_status()

    if a == "CLEAR_CHAT_HISTORY":
        return clear_chat_history()

    # --- OPEN_APP_INSERTED_V1 ---
    # Generic Linux app launcher using args dict.
    if a in ("OPEN_APP", "open_app", "openapp", "LAUNCH_APP", "launch_app"):
        name = ""
        if isinstance(args, dict):
            name = (args.get("name") or args.get("app") or args.get("title") or "").strip()

        if not name:
            return {"ok": False, "action": "OPEN_APP", "error": "missing_name",
                    "content": "Missing app name.", "response": "Missing app name."}

        # Fuzzy / spelling correction map
        _APP_FUZZY2 = {
            "calender": "gnome-calendar", "calander": "gnome-calendar",
            "calendar": "gnome-calendar", "calandar": "gnome-calendar",
            "settings": "gnome-control-center", "setting": "gnome-control-center",
            "files": "nautilus", "file manager": "nautilus",
            "terminal": "gnome-terminal", "term": "gnome-terminal",
            "calculator": "gnome-calculator", "calc": "gnome-calculator",
            "text editor": "gedit", "editor": "gedit",
            "music": "rhythmbox", "photos": "eog",
        }
        name = _APP_FUZZY2.get(name.lower(), name)

        tries = []

        def try_run(cmd):
            tries.append(cmd)
            try:
                import subprocess
                p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return {"ok": True, "pid": p.pid, "cmd": cmd}
            except Exception as e:
                return {"ok": False, "error": repr(e)}

        # gtk-launch desktop id
        for t in (name, name.lower(), name + ".desktop"):
            r = try_run(["gtk-launch", t])
            if r.get("ok"):
                return {"ok": True, "action": "OPEN_APP",
                        "content": f"Opened {name}.", "response": f"Opened {name}.",
                        "result": {"tries": tries, **r}}

        # gio launch desktop file
        for t in (name, name + ".desktop"):
            r = try_run(["gio", "launch", t])
            if r.get("ok"):
                return {"ok": True, "action": "OPEN_APP",
                        "content": f"Opened {name}.", "response": f"Opened {name}.",
                        "result": {"tries": tries, **r}}

        # direct command (supports "cmd --flags")
        try:
            import shlex
            r = try_run(shlex.split(name))
            if r.get("ok"):
                return {"ok": True, "action": "OPEN_APP",
                        "content": f"Opened {name}.", "response": f"Opened {name}.",
                        "result": {"tries": tries, **r}}
        except Exception:
            pass

        return {"ok": False, "action": "OPEN_APP", "error": "launch_failed",
                "content": f"Could not open {name}.", "response": f"Could not open {name}.",
                "result": {"tries": tries}}

    # ---- DATE ----
    if a in ("DATE", "GET_DATE"):
        from datetime import datetime as _dt
        d = _dt.now().strftime("%A, %Y-%m-%d")
        return {"ok": True, "action": a, "content": d, "response": d}

    # ---- MEDIA_CONTROL (generic router output) ----
    if a == "MEDIA_CONTROL":
        cmd = (args.get("command") or "play-pause").strip().lower()
        target = str(args.get("target") or "").strip().lower()
        if target == "spotify":
            spotify_cmd = {"resume": "play", "prev": "previous", "skip": "next"}.get(cmd, cmd)
            if spotify_cmd in {"play", "pause", "stop", "next", "previous", "play-pause"}:
                return _spotify_ctl(spotify_cmd)
        cmd_map = {
            "pause": "PAUSE_MEDIA", "stop": "STOP_MEDIA",
            "play": "PLAY_MEDIA", "resume": "PLAY_MEDIA",
            "next": "NEXT_MEDIA", "skip": "NEXT_MEDIA",
            "previous": "PREVIOUS_MEDIA", "prev": "PREVIOUS_MEDIA",
        }
        mapped = cmd_map.get(cmd)
        if mapped:
            return _execute_impl(mapped, args)
        try:
            subprocess.run(["playerctl", cmd], timeout=5, capture_output=True)
            msg = f"Media: {cmd}"
            return {"ok": True, "action": a, "content": msg, "response": msg}
        except Exception as e:
            return {"ok": False, "action": a, "error": str(e), "content": str(e), "response": str(e)}

    # ---- VOLUME ----
    if a == "VOLUME":
        try:
            from eli.controllers.os_controller import set_volume
            direction = (args.get("direction") or "").strip().lower()
            level = args.get("level")
            delta = int(args.get("delta", 10))
            if direction == "set" and level is not None:
                return set_volume(level=int(level))
            elif direction in ("up", "raise"):
                return set_volume(direction="up", delta=delta)
            elif direction in ("down", "lower"):
                return set_volume(direction="down", delta=delta)
            elif direction == "mute":
                return set_volume(direction="mute")
            elif direction == "unmute":
                return set_volume(direction="unmute")
            msg = "Volume: no direction specified"
            return {"ok": False, "action": a, "content": msg, "response": msg}
        except Exception as e:
            return {"ok": False, "action": a, "error": str(e), "content": str(e), "response": str(e)}

    # ---- SCREENSHOT ----
    if a == "SCREENSHOT":
        try:
            from eli.controllers.os_controller import take_screenshot
            region = (args.get("region") or "full").strip()
            return take_screenshot(region=region)
        except Exception as e:
            return {"ok": False, "action": a, "error": str(e), "content": str(e), "response": str(e)}

    # ---- KEYBOARD ----
    if a == "KEYBOARD":
        try:
            from eli.controllers.os_controller import press_key, type_text
            if args.get("type"):
                return type_text(str(args["type"]))
            elif args.get("key"):
                return press_key(str(args["key"]))
            return {"ok": False, "action": a, "error": "No key or text specified", "content": "No key or text specified", "response": "No key or text specified"}
        except Exception as e:
            return {"ok": False, "action": a, "error": str(e), "content": str(e), "response": str(e)}

    # ---- SET_CLIPBOARD / GET_CLIPBOARD ----
    if a == "SET_CLIPBOARD":
        try:
            from eli.controllers.os_controller import set_clipboard
            txt = str(args.get("text") or "").strip()
            return set_clipboard(txt)
        except Exception as e:
            return {"ok": False, "action": a, "error": str(e), "content": str(e), "response": str(e)}

    if a == "GET_CLIPBOARD":
        try:
            from eli.controllers.os_controller import get_clipboard
            txt = get_clipboard() or ""
            msg = f"Clipboard: {txt[:200]}" if txt else "Clipboard is empty"
            return {"ok": True, "action": a, "content": msg, "response": msg, "text": txt}
        except Exception as e:
            return {"ok": False, "action": a, "error": str(e), "content": str(e), "response": str(e)}

    # ---- LIST_DIR ----
    if a == "LIST_DIR":
        try:
            path = str(args.get("path") or ".").strip()
            p = Path(path).expanduser().resolve()
            if not p.exists():
                return {"ok": False, "action": a, "error": f"Path not found: {p}", "content": f"Path not found: {p}", "response": f"Path not found: {p}"}
            items = sorted([c.name + ("/" if c.is_dir() else "") for c in p.iterdir()])[:200]
            content = "\n".join(items)
            msg = f"Contents of {p} ({len(items)} items):\n{content}"
            return {"ok": True, "action": a, "content": msg, "response": msg, "items": items, "path": str(p)}
        except Exception as e:
            return {"ok": False, "action": a, "error": str(e), "content": str(e), "response": str(e)}

    # ---- SHELL_EXEC (alias for RUN_CMD) ----
    if a == "SHELL_EXEC":
        cmd = args.get("cmd") or args.get("command") or ""
        return _execute_impl("RUN_CMD", {"cmd": cmd, "shell": True})

    # ---- SELF_ANALYZE ----
    if a == "SELF_ANALYZE":
        try:
            from eli.brain.self_improvement import get_self_improvement
            engine = get_self_improvement()
            failures = engine.analyze_failures(limit=10, days=7, min_cluster_size=1)
            lines = [f"Self-Analysis Report ({len(failures)} recent issues):"]
            for f in failures[:10]:
                ui = (f.get("user_input") or "")[:60]
                err = (f.get("error") or "")[:60]
                lines.append(f"  - {ui} → {err}")
            if not failures:
                lines.append("  No recent failures found.")
            if args.get("suggest"):
                result = engine.analyze_and_improve()
                imps = result.get("improvements", [])
                if imps:
                    lines.append(f"\nSuggested improvements ({len(imps)}):")
                    for imp in imps[:5]:
                        lines.append(f"  - {imp.get('description', '')}")
            msg = "\n".join(lines)
            return {"ok": True, "action": a, "content": msg, "response": msg}
        except Exception as e:
            return {"ok": False, "action": a, "error": str(e), "content": str(e), "response": str(e)}

    # ---- SELF_IMPROVE ----
    if a == "SELF_IMPROVE":
        try:
            from eli.brain.self_improvement import get_self_improvement
            result = get_self_improvement().analyze_and_improve()
            imps = result.get("improvements", [])
            msg = f"Self-improvement cycle complete. {len(imps)} items logged."
            if imps:
                msg += "\n" + "\n".join(f"  - {i.get('description', '')}" for i in imps[:5])
            return {"ok": True, "action": a, "content": msg, "response": msg}
        except Exception as e:
            return {"ok": False, "action": a, "error": str(e), "content": str(e), "response": str(e)}

    # ---- MORNING_REPORT ----
    if a == "MORNING_REPORT":
        try:
            from eli.brain.reflection import run_reflection
            result = run_reflection(hours=24)
            insights = result.get("insights", [])
            msg = "Morning Report:\n" + "\n".join(f"  - {i}" for i in insights) if insights else "Morning Report: No significant activity."
            return {"ok": True, "action": a, "content": msg, "response": msg}
        except Exception as e:
            return {"ok": False, "action": a, "error": str(e), "content": str(e), "response": str(e)}

    # ---- GET_WEATHER ----
    if a == "GET_WEATHER":
        location = (args.get("location") or "Dublin").strip()
        # Try FreeWeatherPlugin (class-based, no API key needed)
        try:
            from eli.tools.free_weather import FreeWeatherPlugin
            plugin = FreeWeatherPlugin()
            result = plugin.get_weather({"location": location})
            if isinstance(result, dict):
                result.setdefault("action", a)
                result.setdefault("ok", True)
                return result
        except Exception:
            pass
        # Try WeatherPlugin (needs API key)
        try:
            from eli.plugins.weather import WeatherPlugin
            plugin = WeatherPlugin()
            result = plugin.get_weather({"location": location, "city": location})
            if isinstance(result, dict):
                result.setdefault("action", a)
                return result
        except Exception:
            pass
        msg = f"Weather lookup failed for {location}. No weather module available."
        return {"ok": False, "action": a, "error": msg, "content": msg, "response": msg}


    # ---- OPEN_SYSTEM_SETTINGS ----
    if a == "OPEN_SYSTEM_SETTINGS":
        try:
            candidates = [
                ["gnome-control-center"],
                ["systemsettings5"],
                ["xfce4-settings-manager"],
                ["mate-control-center"],
                ["cinnamon-settings"],
            ]
            for cmd in candidates:
                try:
                    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    msg = f"Opened system settings: {' '.join(cmd)}"
                    return {"ok": True, "action": a, "content": msg, "response": msg}
                except FileNotFoundError:
                    continue
            raise FileNotFoundError("No settings app found")
        except Exception as e:
            return {"ok": False, "action": a, "error": str(e), "content": str(e), "response": str(e)}

    # ---- OPEN_POWER_SETTINGS ----
    if a == "OPEN_POWER_SETTINGS":
        try:
            candidates = [
                ["gnome-control-center", "power"],
                ["systemsettings5", "kcm_energyinfo"],
                ["xfce4-power-manager-settings"],
            ]
            for cmd in candidates:
                try:
                    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    msg = f"Opened power settings: {' '.join(cmd)}"
                    return {"ok": True, "action": a, "content": msg, "response": msg}
                except FileNotFoundError:
                    continue
            raise FileNotFoundError("No power settings app found")
        except Exception as e:
            return {"ok": False, "action": a, "error": str(e), "content": str(e), "response": str(e)}

    # ---- SET_ALARM / SET_TIMER ----
    if a in ("SET_ALARM", "SET_TIMER"):
        try:
            duration = args.get("duration") or args.get("seconds")
            alarm_time = args.get("time") or args.get("alarm_time")
            label = args.get("label") or "ELI Timer"

            if duration:
                secs = int(duration)
                # Background thread timer with notify-send
                def _timer_fire():
                    time.sleep(secs)
                    try:
                        subprocess.run(["notify-send", "-u", "critical", "ELI Timer", f"Timer complete! ({secs}s) - {label}"], timeout=5)
                    except Exception:
                        pass
                    try:
                        subprocess.run(["paplay", "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga"], timeout=5)
                    except Exception:
                        pass
                t = threading.Thread(target=_timer_fire, daemon=True)
                t.start()
                msg = f"Timer set for {secs} seconds."
                return {"ok": True, "action": a, "content": msg, "response": msg}

            elif alarm_time:
                # Parse HH:MM and compute seconds until that time
                from datetime import datetime as _dt
                now = _dt.now()
                try:
                    parts = str(alarm_time).replace(".", ":").split(":")
                    target_h, target_m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
                    target = now.replace(hour=target_h, minute=target_m, second=0, microsecond=0)
                    if target <= now:
                        target = target.replace(day=target.day + 1)
                    secs = int((target - now).total_seconds())
                    def _alarm_fire():
                        time.sleep(secs)
                        try:
                            subprocess.run(["notify-send", "-u", "critical", "ELI Alarm", f"Alarm! It's {alarm_time} - {label}"], timeout=5)
                        except Exception:
                            pass
                        try:
                            subprocess.run(["paplay", "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga"], timeout=5)
                        except Exception:
                            pass
                    t = threading.Thread(target=_alarm_fire, daemon=True)
                    t.start()
                    msg = f"Alarm set for {alarm_time} ({secs}s from now)."
                    return {"ok": True, "action": a, "content": msg, "response": msg}
                except Exception as e:
                    return {"ok": False, "action": a, "error": f"Bad time format: {e}", "content": f"Bad time format: {alarm_time}", "response": f"Bad time format: {alarm_time}"}
            else:
                return {"ok": False, "action": a, "error": "No duration or time specified", "content": "No duration or time specified", "response": "No duration or time specified"}
        except Exception as e:
            return {"ok": False, "action": a, "error": str(e), "content": str(e), "response": str(e)}

    # ---- LIST_EVENTS / ADD_EVENT (calendar stub) ----
    if a == "LIST_EVENTS":
        msg = "Calendar integration not yet configured. Use 'open calendar' to access your calendar app."
        return {"ok": True, "action": a, "content": msg, "response": msg}

    if a == "ADD_EVENT":
        msg = "Calendar integration not yet configured. Use 'open calendar' to access your calendar app."
        return {"ok": True, "action": a, "content": msg, "response": msg}

    # ---- SUMMARIZE_FILE (reads any file, sends to LLM for analysis) ----
    if a == "SUMMARIZE_FILE":
        try:
            file_path = str(args.get("path") or "").strip()
            if not file_path:
                return {"ok": False, "action": a, "error": "Missing path", "content": "Missing path", "response": "Missing path"}
            p = Path(os.path.expanduser(file_path))
            if not p.exists():
                return {"ok": False, "action": a, "error": f"Not found: {p}", "content": f"Not found: {p}", "response": f"Not found: {p}"}
            if p.is_dir():
                # List directory contents and summarize
                items = sorted([c.name for c in p.iterdir()])[:100]
                listing = "\n".join(items)
                prompt = f"Summarize the contents of directory {p}:\n\n{listing}\n\nDescribe what this directory contains and its purpose."
                return chat(prompt)
            else:
                content = p.read_text(encoding="utf-8", errors="replace")[:12000]
                prompt = f"Analyze and summarize the following file ({p.name}):\n\n```\n{content}\n```\n\nProvide a clear, accurate summary. Only state facts present in the file."
                return chat(prompt)
        except Exception as e:
            return {"ok": False, "action": a, "error": str(e), "content": str(e), "response": str(e)}

    # ---- CLOSE_APP ----
    if a == "CLOSE_APP":
        try:
            name = str(args.get("name") or "").strip().lower()
            if not name:
                return {"ok": False, "action": a, "error": "No app specified", "content": "No app specified", "response": "No app specified"}
            # Try pkill, then wmctrl
            r = subprocess.run(["pkill", "-f", name], capture_output=True, timeout=5)
            if r.returncode == 0:
                msg = f"Closed {name}"
                return {"ok": True, "action": a, "content": msg, "response": msg}
            # Try wmctrl close
            try:
                subprocess.run(["wmctrl", "-c", name], capture_output=True, timeout=5)
                msg = f"Closed {name}"
                return {"ok": True, "action": a, "content": msg, "response": msg}
            except FileNotFoundError:
                pass
            msg = f"Could not close {name} (not running or not found)"
            return {"ok": False, "action": a, "content": msg, "response": msg}
        except Exception as e:
            return {"ok": False, "action": a, "error": str(e), "content": str(e), "response": str(e)}

    # ---- ANALYZE_PDF ----
    if a == "ANALYZE_PDF":
        try:
            from eli.tools.analyze_pdfs import analyze_pdf
            path = str(args.get("path") or "").strip()
            if not path:
                return {"ok": False, "action": a, "error": "Missing path", "content": "Missing path", "response": "Missing path"}
            result = analyze_pdf(path)
            if isinstance(result, dict):
                result.setdefault("action", a)
                result.setdefault("ok", True)
                result.setdefault("content", result.get("content") or str(result))
                result.setdefault("response", result.get("content"))
            return result
        except Exception as e:
            return {"ok": False, "action": a, "error": str(e), "content": str(e), "response": str(e)}

    # ---- ANALYZE_CSV ----
    if a == "ANALYZE_CSV":
        try:
            from eli.tools.analyze_csv import analyze_csv
            path = str(args.get("path") or "").strip()
            if not path:
                return {"ok": False, "action": a, "error": "Missing path", "content": "Missing path", "response": "Missing path"}
            result = analyze_csv(path)
            if isinstance(result, dict):
                result.setdefault("action", a)
                result.setdefault("ok", True)
                result.setdefault("content", result.get("content") or str(result))
                result.setdefault("response", result.get("content"))
            return result
        except Exception as e:
            return {"ok": False, "action": a, "error": str(e), "content": str(e), "response": str(e)}

    # ---- GENERATE_DOCUMENT (alias for DOC_GENERATE) ----
    if a == "GENERATE_DOCUMENT":
        return _execute_impl("DOC_GENERATE", args)

    # ---- GENERATE_SCRIPT ----
    if a == "GENERATE_SCRIPT":
        desc = str(args.get("description") or args.get("prompt") or args.get("text") or "").strip()
        if not desc:
            msg = "A script description is required."
            return {"ok": False, "action": a, "error": "missing_description", "content": msg, "response": msg}
        prompt = (
            "Write a production-quality script for the following request.\n"
            "Return clear, runnable code and explain any assumptions briefly.\n\n"
            f"Request: {desc}"
        )
        return chat(prompt)

    # ---- GENERATE_PROJECT ----
    if a == "GENERATE_PROJECT":
        desc = str(args.get("description") or args.get("prompt") or args.get("text") or "").strip()
        if not desc:
            msg = "A project description is required."
            return {"ok": False, "action": a, "error": "missing_description", "content": msg, "response": msg}
        prompt = f"Design a production-quality project for this request and include the initial file structure.\n\nRequest: {desc}"
        return chat(prompt)

    # ---- FIX_FILE ----
    if a == "FIX_FILE":
        path = str(args.get("path") or "").strip()
        if not path:
            msg = "Path not found: no file path provided."
            return {"ok": False, "action": a, "error": "missing_path", "content": msg, "response": msg}
        resolved = Path(os.path.expanduser(path)).resolve()
        if not resolved.exists():
            msg = f"Path not found: {resolved}"
            return {"ok": False, "action": a, "error": "path_not_found", "content": msg, "response": msg}
        if not resolved.is_file():
            msg = f"Not a file: {resolved}"
            return {"ok": False, "action": a, "error": "not_a_file", "content": msg, "response": msg}
        try:
            preview = resolved.read_text(encoding="utf-8", errors="replace")[:6000]
        except Exception as e:
            msg = f"Unable to read file: {resolved} ({e})"
            return {"ok": False, "action": a, "error": "read_failed", "content": msg, "response": msg}
        prompt = (
            f"Review and fix this file in a cognitive, non-stubbed way.\n"
            f"Path: {resolved}\n"
            "Identify likely bugs, wiring issues, and the concrete patch needed.\n\n"
            f"File content:\n{preview}"
        )
        result = chat(prompt)
        if isinstance(result, dict):
            result.setdefault("action", a)
        return result

    # ---- OPEN_IDE / OPEN_IN_IDE / SHOW_DIFF ----
    if a == "OPEN_IDE":
        for editor in ["code", "codium", "subl", "gedit", "kate"]:
            try:
                subprocess.Popen([editor], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                msg = f"Opened IDE: {editor}"
                return {"ok": True, "action": a, "content": msg, "response": msg}
            except FileNotFoundError:
                continue
        return {"ok": False, "action": a, "error": "No IDE found", "content": "No IDE found", "response": "No IDE found"}

    if a == "OPEN_IN_IDE":
        path = str(args.get("path") or "").strip()
        for editor in ["code", "codium", "subl", "gedit", "kate"]:
            try:
                cmd = [editor] + ([path] if path else [])
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                msg = f"Opened {path or 'IDE'} in {editor}"
                return {"ok": True, "action": a, "content": msg, "response": msg}
            except FileNotFoundError:
                continue
        return {"ok": False, "action": a, "error": "No IDE found", "content": "No IDE found", "response": "No IDE found"}

    if a == "SHOW_DIFF":
        return chat("Show me the recent changes or diff in the project.")

    # ---- SUMMARY_RECENT ----
    if a == "SUMMARY_RECENT":
        try:
            from eli.brain.memory_service import summarize_recent_window, get_or_create_session_id
            session_id = str(args.get("session_id") or get_or_create_session_id())
            limit = int(args.get("limit") or args.get("window") or 10)
            query = str(args.get("query") or "").strip()
            if query:
                mem = _get_canonical_memory()
                hits = mem.recall_memory(query, limit=max(3, limit))
                lines = [f"Summary for topic: {query}"]
                for hit in hits:
                    txt = (hit.get("text") or hit.get("content") or "").strip()
                    if txt:
                        lines.append(f"- {txt[:220]}")
                msg = "\n".join(lines) if len(lines) > 1 else f"No memory found for: {query}"
            else:
                msg = summarize_recent_window(session_id=session_id, window=limit)
            return {"ok": True, "action": a, "content": msg, "response": msg}
        except Exception as e:
            msg = f"summary_failed: {e}"
            return {"ok": False, "action": a, "error": str(e), "content": msg, "response": msg}

    # ---- MEMORY_STATS ----
    if a == "MEMORY_STATS":
        try:
            from eli.brain.memory import get_memory
            mem = get_memory()
            conn = mem._get_connection()
            try:
                counts = {}
                for table in ["memories", "conversations", "observations", "failures"]:
                    try:
                        row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                        counts[table] = row[0] if row else 0
                    except Exception:
                        counts[table] = "N/A"
                msg = "Memory Stats:\n" + "\n".join(f"  {k}: {v}" for k, v in counts.items())
            finally:
                conn.close()
            return {"ok": True, "action": a, "content": msg, "response": msg, "counts": counts}
        except Exception as e:
            return {"ok": False, "action": a, "error": str(e), "content": str(e), "response": str(e)}

    return {"ok": False, "action": a, "error": f"Unknown action: {a}", "content": f"Unknown action: {a}", "response": f"Unknown action: {a}"}


def execute(action: str, args: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:

    _mem = _mkvi_memory_dispatch(action, args if isinstance(args, dict) else {})
    if _mem is not None:
        return _mem
    merged: Dict[str, Any] = {}
    if isinstance(args, dict):
        merged.update(args)
    merged.update(kwargs or {})
    res = _execute_impl(action=str(action), args=merged)
    __eli_ret = _normalize_result(res)
    # Normalize LIST_CAPABILITIES top-level content/response (pipeline expects table here)
    try:
        if isinstance(__eli_ret, dict) and __eli_ret.get('action') == 'LIST_CAPABILITIES':
            caps = __eli_ret.get('capabilities')
            if isinstance(caps, dict):
                table = (caps.get('content') or '')
                if table:
                    __eli_ret['content'] = table
                    __eli_ret['response'] = table
    except Exception:
        pass
    return __eli_ret


# Alias for compatibility with tests
execute_action = execute


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("action")
    ap.add_argument("--args", default="{}")
    ns = ap.parse_args()
    print(json.dumps(execute(ns.action, json.loads(ns.args)), indent=2))

# --- AUTO-REGISTER CAPABILITIES (ON IMPORT) ---
try:
    from eli.tools.capability_registry import register as _cap_register
    for _a in SUPPORTED_ACTIONS:
        _cap_register(_a, description=f"Executor action: {_a}")
except Exception:
    pass



# ----------------------------
# Proactive daemon control (real PID management)
# ----------------------------
def _proactive_paths():
    base = Path(os.environ.get("ELI_ARTIFACTS_DIR", "artifacts")) / "proactive"
    base.mkdir(parents=True, exist_ok=True)
    return base, base / "daemon.pid", base / "daemon.log"


def proactive_status() -> Dict[str, Any]:
    base, pidf, logf = _proactive_paths()
    pid = None
    if pidf.exists():
        try:
            pid = int(pidf.read_text().strip())
        except Exception:
            pid = None
    alive = False
    if pid:
        try:
            os.kill(pid, 0)
            alive = True
        except Exception:
            alive = False
    msg = f"Proactive daemon is {'RUNNING' if alive else 'STOPPED'}."
    return {"ok": True, "action": "PROACTIVE_STATUS", "pid": pid, "running": alive, "log": str(logf), "content": msg, "response": msg}


def proactive_start() -> Dict[str, Any]:
    base, pidf, logf = _proactive_paths()
    st = proactive_status()
    if st.get("running"):
        return st
    try:
        py = sys.executable if "sys" in globals() else "python3"
    except Exception:
        py = "python3"
    # run as module so imports work
    argv = [py, "-m", "eli.proactive.proactive_daemon"]
    try:
        lf = open(logf, "a", encoding="utf-8")
        p = subprocess.Popen(argv, stdout=lf, stderr=lf, cwd=str(Path.cwd()))
        pidf.write_text(str(p.pid), encoding="utf-8")
        msg = "Proactive daemon started."
        return {"ok": True, "action": "PROACTIVE_START", "pid": p.pid, "cmd": argv, "log": str(logf), "content": msg, "response": msg}
    except Exception as e:
        msg = "Failed to start proactive daemon."
        return {"ok": False, "action": "PROACTIVE_START", "error": repr(e), "content": msg, "response": msg}


def proactive_stop() -> Dict[str, Any]:
    base, pidf, logf = _proactive_paths()
    pid = None
    if pidf.exists():
        try:
            pid = int(pidf.read_text().strip())
        except Exception:
            pid = None
    if not pid:
        msg = "Proactive daemon not running (no PID)."
        return {"ok": True, "action": "PROACTIVE_STOP", "content": msg, "response": msg}
    try:
        os.kill(pid, 15)
    except Exception:
        pass
    try:
        pidf.unlink(missing_ok=True)  # py3.8+: if not available it will throw
    except Exception:
        try:
            pidf.unlink()
        except Exception:
            pass
    msg = "Proactive daemon stopped."
    return {"ok": True, "action": "PROACTIVE_STOP", "pid": pid, "content": msg, "response": msg}


# --- MKVI memory action fallbacks ---
def _mkvi_memory_dispatch(action, args):
    a = (str(action) if action is not None else "").upper().strip()
    if a == "MEMORY_ADD":
        text = (args.get("text") or args.get("content") or "").strip()
        tags = (args.get("tags") or "").strip()
        if not text:
            return {"ok": False, "action": a, "error": "Empty text", "content": "Empty text", "response": "Empty text"}
        r = add_memory(text, tags=tags)
        return {"ok": (bool(r.get("ok", True)) if isinstance(r, dict) else True), "action": a, **(r if isinstance(r, dict) else {"results": (r if isinstance(r, list) else []), "count": (len(r) if isinstance(r, list) else 0)}), "content": str(r), "response": str(r)}
    if a in {"MEMORY_SEARCH", "MEMORY_RECALL"}:
        q = (args.get("query") or args.get("q") or "").strip()
        k = int(args.get("limit") or args.get("k") or 5)
        if not q:
            return {"ok": False, "action": a, "error": "Empty query", "content": "Empty query", "response": "Empty query"}
        fn = _resolve_search_memory_compat(); r = fn(q=q, k=k) if fn else []
        return {"ok": (bool(r.get("ok", True)) if isinstance(r, dict) else True), "action": a, **(r if isinstance(r, dict) else {"results": (r if isinstance(r, list) else []), "count": (len(r) if isinstance(r, list) else 0)}), "content": str(r), "response": str(r)}
    return None


def _resolve_search_memory_compat():
    """Return a callable compatible with legacy search_memory_compat()."""
    return search_memory_compat



def _mkvi_safe_memory_search(q: str, k: int):
    try:
        r = search_memory_compat(q=q, k=k)
        if isinstance(r, list):
            return {"ok": True, "results": r, "count": len(r)}
        if isinstance(r, dict):
            return r
        return {"ok": True, "results": [], "count": 0}
    except Exception as e:
        return {"ok": False, "error": str(e), "results": [], "count": 0}



# ===== MKVI_EXEC_MEMORY_SHIM_FINAL =====
def _mkvi_exec_memory_search(q: str, k: int):
    try:
        r = search_memory_compat(q=q, k=k)
        if isinstance(r, list):
            return {"ok": True, "results": r, "count": len(r)}
        if isinstance(r, dict):
            rr = r.get("results", [])
            if isinstance(rr, list):
                return {"ok": bool(r.get("ok", True)), "results": rr, "count": len(rr)}
            return {"ok": bool(r.get("ok", True)), "results": [], "count": 0}
        return {"ok": True, "results": [], "count": 0}
    except Exception as e:
        return {"ok": False, "error": str(e), "results": [], "count": 0}





def _mkvi_exec_memory_search_safe(q: str, k: int):
    try:
        r = search_memory_compat(q=q, k=k)
        if isinstance(r, list):
            return {"ok": True, "results": r, "count": len(r)}
        if isinstance(r, dict):
            rr = r.get("results", [])
            if isinstance(rr, list):
                return {"ok": bool(r.get("ok", True)), "results": rr, "count": len(rr)}
        return {"ok": True, "results": [], "count": 0}
    except Exception as e:
        return {"ok": False, "error": str(e), "results": [], "count": 0}

def _mkvi_normalize_action_aliases(action, args):
    try:
        a = (action or "").upper()
        if a == "LIST_DIR":
            p = (args or {}).get("path", ".")
            return "RUN_CMD", {"cmd": f'ls -la "{p}"'}
        return action, args
    except Exception:
        return action, args


def _mkvi_memory_search_safe(q: str, k: int):
    try:
        results = search_memory_compat(q=q, k=k)
        if not isinstance(results, list):
            results = []
        return {"ok": True, "results": results, "count": len(results)}
    except Exception as e:
        return {"ok": False, "error": str(e), "results": [], "count": 0}


def _mkvi_alias_action(action, args):
    try:
        a = str(action or "").upper()
        if a == "LIST_DIR":
            p = (args or {}).get("path", ".")
            return "RUN_CMD", {"cmd": f'ls -la "{p}"'}
        return action, args
    except Exception:
        return action, args


def _mkvi_env_results(r):
    if isinstance(r, dict):
        rr = r.get("results", [])
        if not isinstance(rr, list):
            rr = []
        return {"ok": bool(r.get("ok", True)), "results": rr, "count": len(rr)}
    if isinstance(r, list):
        return {"ok": True, "results": r, "count": len(r)}
    return {"ok": False, "results": [], "count": 0}