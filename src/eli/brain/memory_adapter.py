"""
brain/memory_adapter.py (MKV) — SINGLE SOURCE ADAPTER

Purpose:
- Provide a stable, import-friendly surface over brain/memory.Memory (SQLite)
- Prevent recursion bugs
- Normalize return shapes for older modules (context_builder, brain/__init__.py, etc.)

FIXED: Routes through eli.brain.memory.Memory instead of memory_db directly.
This avoids the schema mismatch where memory_db expects columns (model, dim, vec)
but Memory creates columns (kind, source, confidence, weight).

Exports:
- memory_store(text, tags="")
- memory_search(q, k=5, tags=None)
- memory_recent(limit=10)
- memory (object): .store/.search/.recent/.recall/.remember
- memory_adapter (alias of memory)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


def _get_mem():
    """Lazy import to avoid circular import at module load time."""
    from eli.brain.memory import get_memory
    return get_memory()


def _normalize_results(obj: Any) -> List[Dict[str, Any]]:
    if obj is None:
        return []
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    if isinstance(obj, dict):
        res = obj.get("results")
        if isinstance(res, list):
            return [x for x in res if isinstance(x, dict)]
        res = obj.get("items")
        if isinstance(res, list):
            return [x for x in res if isinstance(x, dict)]
    return []


def memory_store(text: str, tags: str = "") -> Dict[str, Any]:
    """Store a memory via the canonical Memory class."""
    try:
        mem = _get_mem()
        tag_list = [t.strip() for t in str(tags).split(",") if t.strip()] if tags else []
        return mem.store_memory(text, tags=tag_list)
    except Exception as e:
        return {"ok": False, "error": str(e)}


def memory_search(q: str, k: int = 5, tags: Optional[str] = None) -> Dict[str, Any]:
    """Search memories via the canonical Memory class."""
    try:
        mem = _get_mem()
        results = mem.recall_memory(q, limit=k)
        return {"ok": True, "results": results, "count": len(results), "query": q}
    except Exception as e:
        return {"ok": False, "error": str(e), "results": [], "count": 0}


def memory_recent(limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent conversation turns via the canonical Memory class."""
    try:
        mem = _get_mem()
        turns = mem.get_recent_conversation(limit=limit)
        return turns if isinstance(turns, list) else []
    except Exception:
        return []


def _to_context_item(m: Dict[str, Any]) -> Dict[str, Any]:
    """Convert DB memory row -> context-friendly shape."""
    text = m.get("text") or m.get("content") or ""
    tags = m.get("tags") or ""
    parts = [p.strip() for p in str(tags).split(",") if p.strip()]
    source = parts[0] if len(parts) >= 1 else ""
    mtype  = parts[1] if len(parts) >= 2 else ""

    return {
        "id": m.get("id"),
        "ts": m.get("ts"),
        "content": text,
        "text": text,
        "tags": tags,
        "source": source,
        "type": mtype,
    }


@dataclass
class MemoryAdapter:
    def store(self, text: str, tags: str = "", meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return memory_store(text=text, tags=tags)

    def search(self, q: str, k: int = 5, tags: Optional[str] = None) -> Dict[str, Any]:
        return memory_search(q=q, k=k, tags=tags)

    def recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        return [_to_context_item(x) for x in memory_recent(limit=limit)]

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
        tag_blob = ",".join([x for x in [source, mtype, tags] if x])
        return self.store(text, tags=tag_blob)


memory_adapter = MemoryAdapter()
memory = memory_adapter

# Back-compat function exports
def memory_store_fn(text: str, tags: str = "") -> Dict[str, Any]:
    return memory_adapter.store(text, tags=tags)

def memory_search_fn(q: str, k: int = 5) -> Dict[str, Any]:
    return memory_adapter.search(q, k=k)

def memory_recent_fn(limit: int = 10) -> List[Dict[str, Any]]:
    return memory_adapter.recent(limit=limit)
