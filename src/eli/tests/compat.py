"""
eli/brain/compat.py

Compatibility shim: re-exports `execute` from the canonical executor location
so that agent_loop.py and other legacy callers can do:

    from eli.brain.compat import execute
"""

try:
    from eli.tools.executor_enhanced import execute  # noqa: F401
except ImportError:
    try:
        from eli.brain.cognitive_engine import get_engine as _get_engine

        def execute(action: str, args: dict) -> dict:
            """Fallback: route through cognitive engine."""
            engine = _get_engine()
            return engine.execute_action(action, args)

    except ImportError:
        def execute(action: str, args: dict) -> dict:  # type: ignore[misc]
            """Last-resort stub when neither executor nor engine is available."""
            return {"ok": False, "error": "executor unavailable", "action": action}
