"""Routing regression tests.

This project was migrated to a src-layout (src/eli/...). Older tests/imports that used
`tools.*`/`brain.*` from the repo root should now import from `eli.tools.*`/`eli.brain.*`.

This test is intentionally defensive: it validates that the router module is importable
and that it can produce a structured route dict for a few canonical prompts, without
depending on one exact class/function name.
"""

from __future__ import annotations

import importlib


def _get_router_callable(mod):
    """Return a (callable, kind) pair from eli.tools.router_enhanced.

    Supports several historical APIs:
      - RouterEnhanced().route(text)
      - RouterEnhanced().parse(text)
      - route_message(text)
      - route(text)
      - parse_intent(text)

    Raises AssertionError if none found.
    """

    # 1) class-based
    for cls_name in ("RouterEnhanced", "Router", "IntentRouter"):
        cls = getattr(mod, cls_name, None)
        if cls is None:
            continue
        inst = cls()
        for meth_name in ("route", "parse", "run", "decide", "predict"):
            meth = getattr(inst, meth_name, None)
            if callable(meth):
                return meth, f"{cls_name}.{meth_name}"

    # 2) function-based
    for fn_name in ("route_message", "route", "parse_intent", "predict_intent", "classify"):
        fn = getattr(mod, fn_name, None)
        if callable(fn):
            return fn, fn_name

    raise AssertionError(
        "eli.tools.router_enhanced has no recognizable router API. "
        "Expected a RouterEnhanced class or a routing function."
    )


def test_router_module_importable():
    mod = importlib.import_module("eli.tools.router_enhanced")
    assert mod is not None


def test_router_returns_structured_dict_for_basic_prompts():
    mod = importlib.import_module("eli.tools.router_enhanced")
    router, kind = _get_router_callable(mod)

    samples = [
        "open url https://example.com",
        "time",
        "store memory hello tags test",
    ]

    for s in samples:
        out = router(s)
        assert isinstance(out, dict), f"{kind} should return dict, got {type(out)}"
        assert "action" in out, f"{kind} output missing 'action': {out}"
        assert "args" in out, f"{kind} output missing 'args': {out}"


def test_router_action_is_string():
    mod = importlib.import_module("eli.tools.router_enhanced")
    router, _ = _get_router_callable(mod)

    out = router("open url https://example.com")
    assert isinstance(out.get("action"), str)
