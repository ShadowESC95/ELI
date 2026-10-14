"""Build prompt context for ELI without crashing the pipeline."""
from __future__ import annotations

from pathlib import Path
from typing import List
import os

from .memory_adapter import memory


def _read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace").strip()
    except Exception:
        return ""


def _project_root() -> Path:
    return Path(os.environ.get("ELI_ROOT", Path(__file__).resolve().parents[1])).resolve()


def _persona_block(root: Path) -> str:
    persona_path = root / "brain" / "persona.txt"
    persona = _read_text(persona_path)
    if not persona:
        persona = "You are ELI (Enhanced Learning Interface), the user's AI OS assistant. Be accurate, useful, and honest."
    return "=== ELI PERSONA ===\n" + persona


def _recent_memory_block(limit: int = 20) -> str:
    items = []
    try:
        items = memory.recall(limit=limit) or []
    except TypeError:
        try:
            items = memory.recall_memory("", limit=limit) or []
        except Exception:
            items = []
    except Exception:
        items = []

    lines: List[str] = []
    for item in items:
        if isinstance(item, dict):
            txt = (item.get("content") or item.get("text") or "").strip()
        else:
            txt = str(item).strip()
        if txt:
            lines.append(f"- {txt}")
    if not lines:
        return "=== RECENT CONVERSATION ===\n(no recent turns)"
    return "=== RECENT CONVERSATION ===\n" + "\n".join(lines[:limit])


def _relevant_memory_block(user_message: str, limit: int = 8) -> str:
    items = []
    if user_message:
        try:
            items = memory.recall_memory(user_message, limit=limit) or []
        except Exception:
            items = []
    lines: List[str] = []
    for item in items:
        if isinstance(item, dict):
            txt = (item.get("content") or item.get("text") or "").strip()
        else:
            txt = str(item).strip()
        if txt:
            lines.append(f"- {txt}")
    if not lines:
        return "=== RELEVANT MEMORY ===\n(no related memories)"
    return "=== RELEVANT MEMORY ===\n" + "\n".join(lines[:limit])


def build_context(user_message: str = "", user_text: str | None = None, query: str | None = None) -> str:
    user_message = user_message or user_text or query or ""
    root = _project_root()
    parts = [
        _persona_block(root),
        _recent_memory_block(),
        _relevant_memory_block(user_message),
    ]
    if user_message:
        parts.append("=== USER MESSAGE ===\n" + user_message)
    return "\n\n".join(parts).strip()


def _eli_build_context_fallback_guard(value):
    return "" if value is None else value
