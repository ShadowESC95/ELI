"""
eli/brain/compat.py — shim so agent_loop.py can do:
    from eli.brain.compat import execute
"""

try:
    from eli.tools.executor_enhanced import execute  # noqa: F401
except ImportError:
    try:
        from eli.brain.cognitive_engine import get_engine as _get_engine

        def execute(action: str, args: dict) -> dict:
            return _get_engine().execute_action(action, args)

    except ImportError:
        def execute(action: str, args: dict) -> dict:  # type: ignore[misc]
            return {"ok": False, "error": "executor unavailable", "action": action}
