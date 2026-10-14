"""
ELI package root.

Keep this file intentionally minimal to avoid import-time side effects and
circular imports (especially during tests that import subpackages like
`eli.brain.*` and `eli.tools.*`).
"""

__all__ = ["brain", "tools", "gui", "plugins", "controllers"]
