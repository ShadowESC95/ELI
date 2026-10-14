"""eli.brain package

Lightweight public API with lazy imports to avoid circular dependencies.
"""
from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "get_engine", "CognitiveEngine",
    "get_memory", "get_agent_memory", "Memory",
    "get_self_improvement", "SelfImprovementEngine",
    "get_daemon", "ProactiveDaemon",
    "get_paths", "ensure_dirs", "PATHS",
    "PROJECT_ROOT", "ELI_ROOT", "ARTIFACTS_DIR", "CONVERSATIONS_DIR", "MODELS_DIR", "DB_PATH",
    "chat_completion", "stream_chat",
]

_LAZY = {
    "get_engine": (".cognitive_engine", "get_engine"),
    "CognitiveEngine": (".cognitive_engine", "CognitiveEngine"),
    "get_memory": (".memory", "get_memory"),
    "get_agent_memory": (".memory", "get_agent_memory"),
    "Memory": (".memory", "Memory"),
    "get_self_improvement": (".self_improvement", "get_self_improvement"),
    "SelfImprovementEngine": (".self_improvement", "SelfImprovementEngine"),
    "get_daemon": (".proactive_daemon", "get_daemon"),
    "ProactiveDaemon": (".proactive_daemon", "ProactiveDaemon"),
    "get_paths": (".paths", "get_paths"),
    "ensure_dirs": (".paths", "ensure_dirs"),
    "PATHS": (".paths", "PATHS"),
    "PROJECT_ROOT": (".paths", "PROJECT_ROOT"),
    "ELI_ROOT": (".paths", "ELI_ROOT"),
    "ARTIFACTS_DIR": (".paths", "ARTIFACTS_DIR"),
    "CONVERSATIONS_DIR": (".paths", "CONVERSATIONS_DIR"),
    "MODELS_DIR": (".paths", "MODELS_DIR"),
    "DB_PATH": (".paths", "DB_PATH"),
    "chat_completion": (".gguf_inference", "chat_completion"),
    "stream_chat": (".gguf_inference", "stream_chat"),
}


def __getattr__(name: str) -> Any:  # pragma: no cover
    spec = _LAZY.get(name)
    if not spec:
        raise AttributeError(name)
    mod_name, attr = spec
    mod = import_module(mod_name, __name__)
    return getattr(mod, attr)


def __dir__() -> list[str]:  # pragma: no cover
    return sorted(set(globals().keys()) | set(__all__))
