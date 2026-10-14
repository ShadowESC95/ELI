"""
eli/brain/persona.py — Persona management for ELI.
Loads, caches, and provides access to the ELI persona from persona.txt.
Supports runtime preference updates.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, Optional

_PERSONA_FILE = Path(__file__).parent / "persona.txt"
_cached_persona: Optional[str] = None


def _load_raw() -> str:
    """Load raw persona text from persona.txt."""
    if _PERSONA_FILE.exists():
        return _PERSONA_FILE.read_text(encoding="utf-8", errors="replace")
    return ""


def get_persona() -> str:
    """Return the current persona text (cached after first load)."""
    global _cached_persona
    if _cached_persona is None:
        _cached_persona = _load_raw()
    return _cached_persona


def reload() -> str:
    """Force reload persona from disk."""
    global _cached_persona
    _cached_persona = _load_raw()
    return _cached_persona


def append_preference(pref: str) -> bool:
    """Append a user preference to persona.txt's auto-updated section."""
    try:
        content = _PERSONA_FILE.read_text(encoding="utf-8", errors="replace")
        marker = "## User Preferences (Auto-Updated)"
        if marker in content:
            content = content.rstrip() + f"\n- {pref.strip()}\n"
        else:
            content = content.rstrip() + f"\n\n{marker}\n- {pref.strip()}\n"
        _PERSONA_FILE.write_text(content, encoding="utf-8")
        reload()
        return True
    except Exception:
        return False


def get_preferences() -> list:
    """Extract user preferences from the auto-updated section."""
    content = get_persona()
    marker = "## User Preferences (Auto-Updated)"
    if marker not in content:
        return []
    section = content.split(marker, 1)[1]
    return [line.strip().lstrip("- ") for line in section.splitlines()
            if line.strip().startswith("-")]


def status() -> Dict[str, Any]:
    """Return module status with real information."""
    persona = get_persona()
    prefs = get_preferences()
    return {
        "ok": True,
        "module": "persona",
        "mode": "active",
        "file": str(_PERSONA_FILE),
        "loaded": bool(persona),
        "length": len(persona),
        "preferences_count": len(prefs),
    }
