"""Compatibility wrapper over eli.tools.capability_registry."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional
from eli.tools import capability_registry as _reg


class CapabilityRegistry:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def register(self, name: str, func: Callable, description: str = ""):
        _reg.register(name, description=description, handler=lambda args, _f=func: _f(**args) if isinstance(args, dict) else _f(args))

    def get(self, name: str):
        return _reg.get_handler(name)

    def list_capabilities(self) -> List[Dict[str, str]]:
        return _reg.list_capabilities()

    def has_capability(self, name: str) -> bool:
        return _reg.get_capability(name) is not None

    def execute(self, name: str, *args, **kwargs) -> Any:
        if args and not kwargs and len(args) == 1 and isinstance(args[0], dict):
            return _reg.execute(name, args[0])
        payload = kwargs or {"args": list(args)}
        return _reg.execute(name, payload)


capability_registry = CapabilityRegistry()
CAPABILITIES = _reg.list_capabilities()
SUPPORTED_ACTIONS = sorted([c["canonical"] for c in CAPABILITIES])


def list_capabilities(fmt: str = 'list'):
    data = _reg.list_capabilities()
    if fmt == 'json':
        return {"ok": True, "capabilities": data}
    return data


__all__ = ["CapabilityRegistry", "capability_registry", "CAPABILITIES", "SUPPORTED_ACTIONS", "list_capabilities"]
