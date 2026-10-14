"""Canonical capability registry for ELI."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional
import threading

Handler = Callable[[Dict[str, Any]], Any]


@dataclass
class Capability:
    name: str
    description: str = ""
    handler: Optional[Handler] = None
    aliases: List[str] | None = None

    def as_public_dict(self, include_handler: bool = False) -> Dict[str, Any]:
        d = {
            "name": self.name,
            "description": self.description,
            "aliases": list(self.aliases or []),
            "canonical": self.name,
        }
        if include_handler:
            d["handler"] = self.handler
        return d


_lock = threading.RLock()
_CAPS: Dict[str, Capability] = {}
_ALIASES: Dict[str, str] = {}


def _norm(name: str) -> str:
    return (name or "").strip().upper().replace("-", "_").replace(" ", "_")


def register(name: str, description: str = "", handler: Optional[Handler] = None, aliases: Optional[List[str]] = None) -> None:
    n = _norm(name)
    if not n:
        return
    alias_norm = sorted({_norm(a) for a in (aliases or []) if _norm(a)})
    with _lock:
        old = _CAPS.get(n)
        cap = Capability(
            name=n,
            description=description or (old.description if old else ""),
            handler=handler if handler is not None else (old.handler if old else None),
            aliases=sorted(set((old.aliases or []) if old else []).union(alias_norm)),
        )
        _CAPS[n] = cap
        _ALIASES[n] = n
        for a in cap.aliases or []:
            _ALIASES[a] = n


def get_capability(name: str) -> Optional[Dict[str, Any]]:
    n = _norm(name)
    if not n:
        return None
    with _lock:
        canon = _ALIASES.get(n, n)
        cap = _CAPS.get(canon)
        return cap.as_public_dict(include_handler=True) if cap else None


def get_handler(name: str) -> Optional[Handler]:
    cap = get_capability(name)
    return None if not cap else cap.get("handler")


def list_capabilities() -> List[str]:
    with _lock:
        return sorted(_CAPS.keys())


def render_detailed() -> List[Dict[str, Any]]:
    with _lock:
        return [_CAPS[name].as_public_dict(include_handler=False) for name in sorted(_CAPS.keys())]


def execute(name: str, args: Optional[Dict[str, Any]] = None) -> Any:
    h = get_handler(name)
    if not h:
        raise KeyError(f"No handler registered for: {name}")
    return h(args or {})
