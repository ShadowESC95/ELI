"""
brain/memory_adapter.py (MKV) — SINGLE SOURCE ADAPTER

Purpose:
- Provide a stable, import-friendly surface over brain/memory_db.py (SQLite)
- Prevent recursion bugs
- Normalize return shapes for older modules (context_builder, brain/__init__.py, etc.)

Exports:
- memory_store(text, tags="")
- memory_search(q, k=5, tags=None)          # tags best-effort
- memory_recent(limit=10)                  # list normalized
- memory (object): .store/.search/.recent/.recall/.remember
- memory_adapter (alias of memory)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import inspect

from . import memory_db as _db


def _supports_param(fn, name: str) -> bool:
    try:
        sig = inspect.signature(fn)
        return name in sig.parameters
    except Exception:
        return False


def _normalize_results(obj: Any) -> List[Dict[str, Any]]:
    """
    brain/memory_db functions in this repo return either:
    - a dict: {"ok": True, "results": [...], ...}
    - or directly a list of dicts
    Normalize to: List[Dict[str, Any]]
    """
    if obj is None:
        return []
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    if isinstance(obj, dict):
        res = obj.get("results")
        if isinstance(res, list):
            return [x for x in res if isinstance(x, dict)]
        # fallback: some variants may use "items"
        res = obj.get("items")
        if isinstance(res, list):
            return [x for x in res if isinstance(x, dict)]
    return []


def memory_store(text: str, tags: str = "") -> Dict[str, Any]:
    # Call DB directly. NO calling adapter again. No recursion.
    return _db.add_memory(text, tags=tags)


def memory_search(q: str, k: int = 5, tags: Optional[str] = None) -> Dict[str, Any]:
    # Best-effort: only pass tags if DB supports it.
    if tags and _supports_param(_db.search_memory, "tags"):
        return _db.search_memory(q, k=k, tags=tags)
    return _db.search_memory(q, k=k)


def memory_recent(limit: int = 10) -> List[Dict[str, Any]]:
    # Normalize to list
    out = _db.recall_recent(k=limit) if _supports_param(_db.recall_recent, "k") else _db.recall_recent(limit)
    return _normalize_results(out)


def _to_context_item(m: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert DB memory row -> context-friendly shape used by older builders:
    expected keys (some older code): content, source, type
    """
    text = m.get("text") or m.get("content") or ""
    tags = m.get("tags") or ""
    parts = [p.strip() for p in str(tags).split(",") if p.strip()]
    source = parts[0] if len(parts) >= 1 else ""
    mtype  = parts[1] if len(parts) >= 2 else ""

    return {
        "id": m.get("id"),
        "ts": m.get("ts"),
        "content": text,
        "text": text,          # keep both
        "tags": tags,
        "source": source,
        "type": mtype,
    }


@dataclass
class MemoryAdapter:
    def store(self, text: str, tags: str = "", meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        # meta is accepted for future expansion; ignored for now.
        return memory_store(text=text, tags=tags)

    def search(self, q: str, k: int = 5, tags: Optional[str] = None) -> Dict[str, Any]:
        return memory_search(q=q, k=k, tags=tags)

    def recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        return [ _to_context_item(x) for x in memory_recent(limit=limit) ]

    # Older modules often call .recall(limit=...)
    def recall(self, limit: int = 10) -> List[Dict[str, Any]]:
        return self.recent(limit=limit)

    def remember(
        self,
        text: str,
        source: str = "",
        mtype: str = "",
        importance: float = 0.0,
        tags: Optional[str] = None,
    ) -> Dict[str, Any]:
        # Fold metadata into tags
        tag_blob = ",".join([x for x in [source, mtype, tags] if x])
        return self.store(text, tags=tag_blob)


memory_adapter = MemoryAdapter()
memory = memory_adapter

# Back-compat function exports expected by brain/__init__.py and older code
def memory_store_fn(text: str, tags: str = "") -> Dict[str, Any]:
    return memory_adapter.store(text, tags=tags)

def memory_search_fn(q: str, k: int = 5) -> Dict[str, Any]:
    return memory_adapter.search(q, k=k)

def memory_recent_fn(limit: int = 10) -> List[Dict[str, Any]]:
    return memory_adapter.recent(limit=limit)

