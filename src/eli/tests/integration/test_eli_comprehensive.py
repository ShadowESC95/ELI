"""
ELI MK VIII – Comprehensive Wiring & Capabilities Test Suite
=============================================================
Clean rewrite of test_eli_comprehensive.py.

Covers 13 sections:
  1.  Module imports
  2.  Router correctness
  3.  _KNOWN_ACTIONS guard
  4.  Executor safe/non-destructive actions
  5.  execute() return-value contract
  6.  Memory system
  7.  Configuration / paths
  8.  Capability registry
  9.  OS controller
  10. Proactive daemon
  11. Cognitive engine (mocked)
  12. Plugins
  13. Router → Executor full round-trip

Rules
-----
  • Never load a GGUF model          (all LLM/Ollama calls mocked at module load)
  • Never pollute the real database  (every test uses a tmp SQLite)
  • Never run destructive shell cmds (subprocess mocked where needed)
  • Must pass  pytest -q  without errors

Run:
    pytest src/eli/tests/integration/test_eli_comprehensive.py -v
"""

from __future__ import annotations

# ──────────────────────────────────────────────────────────────────────────────
# BOOTSTRAP  (must happen BEFORE any eli imports)
# ──────────────────────────────────────────────────────────────────────────────
import os
import sys
import types
import time
import shutil
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Locate the project's src/ directory by resolving the eli package.
import eli as _eli_pkg
_ELI_PKG_DIR = Path(_eli_pkg.__file__).resolve().parent   # .../src/eli
_SRC_DIR     = _ELI_PKG_DIR.parent                        # .../src

if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


# ──────────────────────────────────────────────────────────────────────────────
# Network mocking only — do NOT inject fake brain modules into sys.modules.
# Global module stubs leak into the rest of the pytest session and poison the
# singleton / wiring tests.
# ──────────────────────────────────────────────────────────────────────────────
import requests as _requests
_fake_http = MagicMock()
_fake_http.status_code = 200
_fake_http.raise_for_status = lambda: None
_fake_http.json.return_value = {
    "message": {"content": "mocked ollama response"},
    "models":  [],
}
_requests.post = MagicMock(return_value=_fake_http)
_requests.get  = MagicMock(return_value=_fake_http)


# ──────────────────────────────────────────────────────────────────────────────
# Module-level import of router / executor
# ──────────────────────────────────────────────────────────────────────────────
_ROUTER_OK    = False
_ROUTER_ERR   = ""
_EXECUTOR_OK  = False
_EXECUTOR_ERR = ""
route   = None
execute = None

try:
    from eli.tools.router_enhanced import route as _route
    route = _route
    _ROUTER_OK = True
except Exception as _e:
    _ROUTER_ERR = str(_e)

try:
    from eli.tools.executor_enhanced import execute as _execute
    execute = _execute
    _EXECUTOR_OK = True
except Exception as _e:
    _EXECUTOR_ERR = str(_e)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _route_ok(got, expected):
    if got == expected:
        return True
    _aliases = {"PAUSE_MEDIA", "PLAY_MEDIA", "STOP_MEDIA", "NEXT_MEDIA", "PREVIOUS_MEDIA"}
    if expected == "MEDIA_CONTROL" and got in _aliases:
        return True
    return False


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    db = tmp_path / "test_comprehensive.sqlite3"
    monkeypatch.setenv("ELI_MEMORY_DB",      str(db))
    monkeypatch.setenv("ELI_MEMORY_DB_PATH", str(db))
    monkeypatch.setenv("ELI_N_GPU_LAYERS",   "0")
    yield db
    for mod_name, attr in [
        ("eli.brain.memory",           "_memory_singleton"),
        ("eli.brain.cognitive_engine", "_engine"),
        ("eli.brain.self_improvement", "_self_engine"),
        ("eli.brain.proactive_daemon", "_daemon"),
    ]:
        mod = sys.modules.get(mod_name)
        if mod and hasattr(mod, attr):
            try:
                setattr(mod, attr, None)
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 – Module Imports
# ══════════════════════════════════════════════════════════════════════════════

class TestS1Imports:

    _MODULES = [
        ("eli.brain.memory",              "memory"),
        ("eli.brain.paths",               "paths"),
        ("eli.brain.config",              "config"),
        ("eli.tools.capability_registry", "capability_registry"),
        ("eli.brain.system_index",        "system_index"),
        ("eli.brain.habits",              "habits"),
        ("eli.brain.reflection",          "reflection"),
        ("eli.brain.response_sanitizer",  "response_sanitizer"),
        ("eli.brain.identity_guard",      "identity_guard"),
        ("eli.brain.values",              "values"),
        ("eli.brain.scheduler",           "scheduler"),
        ("eli.brain.context_builder",     "context_builder"),
        ("eli.controllers.os_controller", "os_controller"),
        ("eli.plugins.base",              "plugins.base"),
        ("eli.plugins.weather",           "plugins.weather"),
        ("eli.plugins.calendar",          "plugins.calendar"),
        ("eli.brain.audio_stt",           "audio_stt"),
    ]

    def test_router_importable(self):
        assert _ROUTER_OK, f"router_enhanced import failed: {_ROUTER_ERR}"

    def test_executor_importable(self):
        assert _EXECUTOR_OK, f"executor_enhanced import failed: {_EXECUTOR_ERR}"

    @pytest.mark.parametrize("mod_name,alias", _MODULES)
    def test_module_importable(self, mod_name, alias):
        __import__(mod_name)

    def test_gguf_not_loaded_at_import(self):
        import importlib
        gg = importlib.import_module("eli.brain.gguf_inference")
        loaded = getattr(gg, "_model_instance", None) is not None
        assert not loaded, "GGUF model was loaded during import – will OOM on low-RAM machines!"


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 – Router Correctness
# ══════════════════════════════════════════════════════════════════════════════

_ROUTER_CASES = [
    ("what time is it",                          "TIME",                 ""),
    ("time",                                     "TIME",                 "bare word"),
    ("what is the current time",                 "TIME",                 ""),
    ("check chronal alignment",                  "TIME",                 "ELI alias"),
    ("what date is it",                          "DATE",                 ""),
    ("today's date",                             "DATE",                 ""),
    ("pause the music",                          "MEDIA_CONTROL",        ""),
    ("pause media",                              "MEDIA_CONTROL",        ""),
    ("play music",                               "MEDIA_CONTROL",        ""),
    ("resume spotify",                           "MEDIA_CONTROL",        "app-specific"),
    ("next song",                                "NEXT_MEDIA",           ""),
    ("skip track",                               "NEXT_MEDIA",           ""),
    ("previous track",                           "PREVIOUS_MEDIA",       ""),
    ("stop media",                               "STOP_MEDIA",           ""),
    ("volume up",                                "VOLUME",               ""),
    ("volume down",                              "VOLUME",               ""),
    ("raise the volume",                         "VOLUME",               ""),
    ("set volume to 50",                         "VOLUME",               ""),
    ("mute",                                     "VOLUME",               ""),
    ("unmute",                                   "VOLUME",               ""),
    ("open spotify",                             "OPEN_APP",             ""),
    ("launch code",                              "OPEN_APP",             ""),
    ("open firefox",                             "OPEN_BROWSER",         ""),
    ("search for quantum mechanics",             "OPEN_BROWSER",         ""),
    ("google.com",                               "OPEN_URL",             "bare domain"),
    ("open https://github.com",                  "OPEN_URL",             ""),
    ("remember that my favourite color is blue", "MEMORY_STORE",         ""),
    ("store memory I love physics",              "MEMORY_STORE",         ""),
    ("recall last conversation",                 "MEMORY_RECALL",        ""),
    ("recall quantum",                           "MEMORY_RECALL",        ""),
    ("access neural archive",                    "MEMORY_RECALL",        "ELI alias"),
    ("list files in /tmp",                       "LIST_DIR",             ""),
    ("show directory",                           "LIST_DIR",             ""),
    ("read file /etc/hostname",                  "READ_FILE",            ""),
    ("show /etc/hosts",                          "READ_FILE",            ""),
    ("write note about the meeting",             "WRITE_NOTE",           ""),
    ("fix file test.py",                         "FIX_FILE",             ""),
    ("open file system",                         "OPEN_FILE_SYSTEM",     ""),
    ("create a python script for sorting",       "GENERATE_SCRIPT",      ""),
    ("write a script that does X",               "GENERATE_SCRIPT",      ""),
    ("generate document about AI trends",        "GENERATE_DOCUMENT",    ""),
    ("take a screenshot",                        "SCREENSHOT",           ""),
    ("capture screen",                           "SCREENSHOT",           ""),
    ("open power settings",                      "OPEN_POWER_SETTINGS",  ""),
    ("open system settings",                     "OPEN_SYSTEM_SETTINGS", ""),
    ("open audio settings",                      "OPEN_AUDIO_SETTINGS",  ""),
    ("fabricate data construct",                 "DATA_FABRICATOR",      ""),
    ("morning report",                           "MORNING_REPORT",       ""),
    ("daily report",                             "MORNING_REPORT",       ""),
    ("analyze yourself",                         "SELF_ANALYZE",         ""),
    ("self analysis",                            "SELF_ANALYZE",         ""),
    ("improve yourself",                         "SELF_IMPROVE",         ""),
    ("get clipboard",                            "GET_CLIPBOARD",        ""),
    ("what's the weather",                       "GET_WEATHER",          ""),
    ("weather in Dublin",                        "GET_WEATHER",          ""),
    ("list my events",                           "LIST_EVENTS",          ""),
    ("show calendar",                            "LIST_EVENTS",          ""),
    ("add meeting tomorrow",                     "ADD_EVENT",            ""),
    ("list capabilities",                        "LIST_CAPABILITIES",    ""),
    ("what can you do",                          "LIST_CAPABILITIES",    ""),
]


@pytest.mark.skipif(not _ROUTER_OK, reason=f"router import failed: {_ROUTER_ERR}")
class TestS2Router:

    @pytest.mark.parametrize("text,expected,note", _ROUTER_CASES)
    def test_route_mapping(self, text, expected, note):
        result = route(text)
        got    = result.get("action", "")
        assert _route_ok(got, expected), (
            f"route({text!r}) → {got!r}, expected {expected!r}"
            + (f"  [{note}]" if note else "")
        )

    def test_route_returns_confidence(self):
        result = route("open spotify")
        conf   = result.get("confidence")
        assert isinstance(conf, (int, float)), f"confidence is {conf!r}"

    def test_unknown_input_falls_back_to_chat(self):
        result = route("xyzzy nonsense input 9z3k")
        assert result.get("action") == "CHAT"

    def test_empty_input_handled(self):
        result = route("")
        assert isinstance(result, dict) and "action" in result


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 – _KNOWN_ACTIONS Guard
# ══════════════════════════════════════════════════════════════════════════════

_ROUTER_EMITS = {
    "TIME", "DATE", "CHAT",
    "MEDIA_CONTROL", "PLAY_MEDIA", "PAUSE_MEDIA", "STOP_MEDIA",
    "NEXT_MEDIA", "PREVIOUS_MEDIA",
    "VOLUME", "SCREENSHOT", "KEYBOARD",
    "OPEN_APP", "LAUNCH_APP", "OPEN_URL", "OPEN_BROWSER",
    "OPEN_NETWORK_BROWSER", "OPEN_FILE_SYSTEM", "OPEN_COMMUNICATION_HUB",
    "OPEN_AUDIO_SETTINGS", "OPEN_POWER_SETTINGS", "OPEN_SYSTEM_SETTINGS",
    "OPEN_MEDIA_HUB",
    "MEMORY_STORE", "MEMORY_RECALL",
    "LIST_DIR", "READ_FILE", "WRITE_NOTE", "FIX_FILE",
    "GENERATE_SCRIPT", "GENERATE_DOCUMENT", "DOC_GENERATE",
    "ANALYZE_PDF", "ANALYZE_CSV",
    "DATA_FABRICATOR", "MORNING_REPORT",
    "SELF_ANALYZE", "SELF_IMPROVE",
    "GET_WEATHER", "LIST_EVENTS", "ADD_EVENT",
    "GET_CLIPBOARD", "SET_CLIPBOARD",
    "SHELL_EXEC", "BASH", "EXEC_COMMAND", "EXEC",
    "LIST_CAPABILITIES", "HELP",
    "PROACTIVE_START", "PROACTIVE_STOP", "PROACTIVE_STATUS",
    "PERSONA_LOCK_SET", "PERSONA_LOCK_STATUS", "PERSONA_LOCK_CLEAR",
    "SET_USER_NAME", "GET_STATUS", "CLEAR_CHAT_HISTORY",
}


@pytest.mark.skipif(not _EXECUTOR_OK, reason=f"executor import failed: {_EXECUTOR_ERR}")
class TestS3KnownActionsGuard:

    @pytest.fixture(autouse=True)
    def _load_known(self):
        import eli.tools.executor_enhanced as ex
        self._known = getattr(ex, "_KNOWN_ACTIONS", None) or set()

    @pytest.mark.parametrize("action", sorted(_ROUTER_EMITS))
    def test_action_in_known(self, action):
        if not self._known:
            pytest.skip("_KNOWN_ACTIONS not exported by executor")
        assert action in self._known, (
            f"'{action}' is emitted by the router but NOT in _KNOWN_ACTIONS – "
            f"executor will silently return unknown_action!"
        )

    def test_unknown_action_rejected(self):
        res = execute("COMPLETELY_UNKNOWN_ACTION_XYZ_789", {})
        assert res.get("ok") is False
        assert "unknown" in res.get("error", "").lower()

    def test_none_action_no_crash(self):
        res = execute(None, {})
        assert isinstance(res, dict)

    def test_nonstring_action_no_crash(self):
        res = execute(12345, {})
        assert isinstance(res, dict)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 – Executor: Safe / Non-Destructive Actions
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not _EXECUTOR_OK, reason=f"executor import failed: {_EXECUTOR_ERR}")
class TestS4ExecutorSafe:

    def test_time(self):
        r = execute("TIME", {})
        assert r.get("ok") is True and "content" in r

    def test_date(self):
        r = execute("DATE", {})
        assert r.get("ok") is True and "content" in r

    def test_get_time_alias(self):
        assert isinstance(execute("GET_TIME", {}), dict)

    def test_get_date_alias(self):
        assert isinstance(execute("GET_DATE", {}), dict)

    def test_list_capabilities(self):
        assert "ok" in execute("LIST_CAPABILITIES", {})

    def test_help(self):
        assert "ok" in execute("HELP", {})

    def test_read_file_existing(self):
        assert execute("READ_FILE", {"path": "/etc/hostname"}).get("ok") is True

    def test_read_file_missing(self):
        assert execute("READ_FILE", {"path": "/nonexistent_xyz_123.txt"}).get("ok") is False

    def test_read_file_no_path(self):
        assert execute("READ_FILE", {}).get("ok") is False

    def test_list_dir_tmp(self):
        assert execute("LIST_DIR", {"path": "/tmp"}).get("ok") is True

    def test_list_dir_missing(self):
        assert execute("LIST_DIR", {"path": "/nonexistent_xyz_dir"}).get("ok") is False

    def test_write_note(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ELI_ROOT", str(tmp_path))
        assert "ok" in execute("WRITE_NOTE", {"text": "test note"})

    def test_memory_store(self):
        assert execute("MEMORY_STORE", {"text": "ELI test entry"}).get("ok") is True

    def test_memory_store_with_tags(self):
        assert execute("MEMORY_STORE", {"text": "blue", "tags": ["test"]}).get("ok") is True

    def test_memory_store_empty_rejected(self):
        assert execute("MEMORY_STORE", {"text": ""}).get("ok") is False

    def test_memory_recall(self):
        assert "ok" in execute("MEMORY_RECALL", {"query": "test"})

    def test_memory_recall_empty_rejected(self):
        assert execute("MEMORY_RECALL", {"query": ""}).get("ok") is False

    def test_proactive_status(self):
        assert "ok" in execute("PROACTIVE_STATUS", {})

    def test_proactive_stop(self):
        assert "ok" in execute("PROACTIVE_STOP", {})

    def test_persona_lock_status(self):
        assert "ok" in execute("PERSONA_LOCK_STATUS", {})

    def test_persona_lock_clear(self):
        assert "ok" in execute("PERSONA_LOCK_CLEAR", {})

    def test_set_user_name(self):
        assert execute("SET_USER_NAME", {"name": "TestUser"}).get("ok") is True

    def test_set_user_name_empty_rejected(self):
        assert execute("SET_USER_NAME", {"name": ""}).get("ok") is False

    def test_get_status(self):
        assert "ok" in execute("GET_STATUS", {})

    def test_clear_chat_history(self):
        assert "ok" in execute("CLEAR_CHAT_HISTORY", {})

    def test_self_analyze(self):
        assert "ok" in execute("SELF_ANALYZE", {})

    def test_self_improve(self):
        assert "ok" in execute("SELF_IMPROVE", {})

    def test_morning_report(self):
        assert "ok" in execute("MORNING_REPORT", {})

    def test_chat_basic(self):
        assert "ok" in execute("CHAT", {"message": "Hello ELI"})

    def test_chat_empty_rejected(self):
        assert execute("CHAT", {"message": ""}).get("ok") is False

    @pytest.mark.parametrize("act", [
        "PAUSE_MEDIA", "PLAY_MEDIA", "STOP_MEDIA", "NEXT_MEDIA", "PREVIOUS_MEDIA",
    ])
    def test_media_handler_exists(self, act):
        r = execute(act, {})
        assert isinstance(r, dict) and "ok" in r

    @pytest.mark.parametrize("cmd", ["pause", "play", "next", "previous"])
    def test_media_control_dispatch(self, cmd):
        assert "ok" in execute("MEDIA_CONTROL", {"command": cmd, "type": "generic"})

    @pytest.mark.parametrize("direction", ["up", "down"])
    def test_volume_direction(self, direction):
        assert "ok" in execute("VOLUME", {"direction": direction, "delta": 5})

    def test_volume_set_level(self):
        assert "ok" in execute("VOLUME", {"direction": "set", "level": 50})

    def test_get_weather(self):
        assert "ok" in execute("GET_WEATHER", {"location": "Dublin"})

    def test_doc_generate(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ELI_ARTIFACTS_DIR", str(tmp_path))
        assert "ok" in execute("DOC_GENERATE", {"topic": "Quantum Mechanics", "format": "md"})

    def test_generate_document_alias(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ELI_ARTIFACTS_DIR", str(tmp_path))
        assert "ok" in execute("GENERATE_DOCUMENT", {"topic": "Test Topic"})

    def test_data_fabricator(self):
        assert "ok" in execute("DATA_FABRICATOR", {})

    def test_open_browser_mocked(self):
        with patch("subprocess.Popen", return_value=MagicMock()):
            r = execute("OPEN_BROWSER", {"url": "https://example.com"})
        assert isinstance(r, dict) and "ok" in r

    def test_open_app_mocked(self):
        with patch("subprocess.Popen", return_value=MagicMock()):
            r = execute("OPEN_APP", {"name": "spotify"})
        assert isinstance(r, dict) and "ok" in r


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5 – execute() Return-Value Contract
# ══════════════════════════════════════════════════════════════════════════════

_CONTRACT_CASES = [
    ("TIME",              {}),
    ("DATE",              {}),
    ("LIST_CAPABILITIES", {}),
    ("READ_FILE",         {"path": "/etc/hostname"}),
    ("MEMORY_STORE",      {"text": "contract_test_entry"}),
    ("MEMORY_RECALL",     {"query": "contract_test"}),
    ("PROACTIVE_STATUS",  {}),
    ("GET_STATUS",        {}),
    ("SELF_ANALYZE",      {}),
    ("MORNING_REPORT",    {}),
]


@pytest.mark.skipif(not _EXECUTOR_OK, reason=f"executor import failed: {_EXECUTOR_ERR}")
class TestS5ReturnContract:

    @pytest.mark.parametrize("action,args", _CONTRACT_CASES)
    def test_result_contract(self, action, args):
        r = execute(action, args)
        problems = []
        if "ok" not in r:
            problems.append("missing 'ok'")
        elif not isinstance(r["ok"], bool):
            problems.append(f"'ok' is {type(r['ok']).__name__}, not bool")
        if "content" not in r:
            problems.append("missing 'content'")
        elif not isinstance(r.get("content"), str):
            problems.append(f"'content' is {type(r.get('content')).__name__}, not str")
        if "response" not in r:
            problems.append("missing 'response'")
        elif not isinstance(r.get("response"), str):
            problems.append(f"'response' is {type(r.get('response')).__name__}, not str")
        assert not problems, f"{action} contract violations: {', '.join(problems)}"


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6 – Memory System
# ══════════════════════════════════════════════════════════════════════════════

class TestS6Memory:

    def test_store_and_recall(self):
        import eli.brain.memory as m
        m._memory_singleton = None
        mem = m.get_memory()
        tag = f"mem_test_{time.time()}"
        r   = mem.store_memory(f"Test entry: {tag}", tags=["comprehensive_test"])
        assert r.get("ok") is True, f"store_memory failed: {r}"
        hits  = mem.recall_memory(tag, limit=5)
        found = any(tag in (h.get("text", "") or "") for h in hits)
        assert found, f"stored '{tag}' but hits={hits[:2]}"

    def test_conversation_roundtrip(self):
        import eli.brain.memory as m
        m._memory_singleton = None
        mem = m.get_memory()
        mem.add_conversation_turn("user",      "Hello comprehensive test",
                                  session_id="ctest", user_id="ctest")
        mem.add_conversation_turn("assistant", "Hello back",
                                  session_id="ctest", user_id="ctest")
        conv = mem.get_recent_conversation(limit=5, user_id="ctest")
        assert len(conv) >= 1
        assert any("Hello" in (c.get("content", "") or "") for c in conv)

    def test_search_conversations(self):
        import eli.brain.memory as m
        m._memory_singleton = None
        mem = m.get_memory()
        mem.add_conversation_turn("user", "search_comprehensive_test",
                                  session_id="s1", user_id="s1")
        results = mem.search_conversations("search_comprehensive_test")
        assert isinstance(results, list)

    def test_executor_memory_roundtrip(self):
        if not _EXECUTOR_OK:
            pytest.skip("executor not available")
        sentinel = f"exec_mem_test_{int(time.time())}"
        r1 = execute("MEMORY_STORE", {"text": sentinel, "tags": ["exec_test"]})
        assert r1.get("ok") is True, str(r1)
        r2 = execute("MEMORY_RECALL", {"query": sentinel})
        content = str(r2.get("content", "")) + str(r2.get("hits", ""))
        assert sentinel.lower() in content.lower(), (
            f"stored '{sentinel}' but not found in: {content[:120]}"
        )

    def test_sqlite_tables_exist(self):
        import eli.brain.memory as m
        m._memory_singleton = None
        mem = m.get_memory()
        con    = sqlite3.connect(str(mem.db_path))
        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        con.close()
        for tbl in ("memories", "conversations"):
            assert tbl in tables, f"Required table '{tbl}' missing. Found: {tables}"


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7 – Configuration / Paths
# ══════════════════════════════════════════════════════════════════════════════

class TestS7Config:

    def test_get_config(self):
        try:
            from eli.brain.config import get_config
            cfg = get_config()
            assert cfg is not None
        except ImportError:
            pytest.skip("get_config not exported")

    def test_config_set_get_roundtrip(self):
        try:
            from eli.brain.config import get_config, set_config
        except ImportError:
            pytest.skip("set_config not exported")
        set_config("test_key_comprehensive", "test_value_xyz")
        val = get_config("test_key_comprehensive")
        assert val == "test_value_xyz", f"config round-trip failed: {val!r}"

    def test_paths_root(self):
        from eli.brain.paths import PATHS
        assert PATHS.root is not None

    def test_paths_db(self):
        from eli.brain.paths import PATHS
        assert PATHS.db is not None

    def test_paths_artifacts(self):
        from eli.brain.paths import PATHS
        assert PATHS.artifacts is not None

    def test_paths_project(self):
        from eli.brain.paths import PATHS
        # 'project' is added by apply_fixes.py; fall back to 'root' if absent
        proj = getattr(PATHS, "project", None) or getattr(PATHS, "root", None)
        assert proj is not None


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 8 – Capability Registry
# ══════════════════════════════════════════════════════════════════════════════

class TestS8CapabilityRegistry:

    def test_register_and_list(self):
        from eli.tools.capability_registry import register, list_capabilities
        CAP = "TEST_CAP_COMPREHENSIVE_XYZ"
        register(CAP, handler=lambda a: {"ok": True, "content": "", "response": ""},
                 description="test cap")
        caps = list_capabilities()
        assert isinstance(caps, list)
        found = any(
            (isinstance(c, str)  and c == CAP) or
            (isinstance(c, dict) and c.get("name") == CAP)
            for c in caps
        )
        assert found, f"{CAP} not found in {caps[:5]}"

    def test_get_capability(self):
        from eli.tools.capability_registry import register, get_capability
        CAP = "TEST_CAP_GET_XYZ"
        register(CAP, handler=lambda a: {"ok": True, "content": "", "response": ""},
                 description="get test")
        cap = get_capability(CAP)
        assert cap is not None

    def test_registered_handler_callable(self):
        from eli.tools.capability_registry import register, get_capability
        CAP    = "TEST_CAP_CALL_XYZ"
        called = []

        def _h(args):
            called.append(args)
            return {"ok": True, "content": "ok", "response": "ok"}

        register(CAP, handler=_h, description="call test")
        cap    = get_capability(CAP)
        assert cap and cap.get("handler")
        result = cap["handler"]({"x": 1})
        assert result.get("ok") is True and called


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 9 – OS Controller
# ══════════════════════════════════════════════════════════════════════════════

class TestS9OsController:

    @pytest.fixture(autouse=True)
    def _import(self):
        try:
            from eli.controllers.os_controller import (
                take_screenshot, set_volume, get_clipboard,
                set_clipboard, press_key, type_text,
            )
            self.take_screenshot = take_screenshot
            self.set_volume      = set_volume
            self.get_clipboard   = get_clipboard
        except ImportError as e:
            pytest.skip(f"os_controller not importable: {e}")

    def test_get_clipboard_no_crash(self):
        result = self.get_clipboard()
        assert result is None or isinstance(result, str)

    def test_set_volume_up(self):
        with patch("subprocess.run", return_value=MagicMock(returncode=0)):
            r = self.set_volume(direction="up", delta=5)
        assert isinstance(r, dict) and "ok" in r

    def test_take_screenshot(self):
        with patch("subprocess.run",  return_value=MagicMock(returncode=0, stderr="")), \
             patch("shutil.which",    return_value="/usr/bin/scrot"):
            r = self.take_screenshot("full")
        assert isinstance(r, dict) and "ok" in r


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 10 – Proactive Daemon
# ══════════════════════════════════════════════════════════════════════════════

class TestS10Proactive:

    def test_proactive_module_imports(self):
        import eli.brain.proactive_daemon as mod
        assert hasattr(mod, "ProactiveDaemon")
        assert hasattr(mod, "get_daemon")

    def test_daemon_singleton_callable(self):
        from eli.brain.proactive_daemon import get_daemon
        daemon = get_daemon()
        assert daemon is not None
        assert any(hasattr(daemon, name) for name in ["stop", "stop_daemon", "running", "analyze_user_patterns"])

    def test_executor_proactive_status(self):
        if not _EXECUTOR_OK:
            pytest.skip("executor not available")
        r = execute("PROACTIVE_STATUS", {})
        assert isinstance(r, dict) and "ok" in r


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 11 – Cognitive Engine
# ══════════════════════════════════════════════════════════════════════════════

class TestS11CognitiveEngine:

    def test_cognitive_engine_module_imports(self):
        import eli.brain.cognitive_engine as mod
        assert hasattr(mod, "CognitiveEngine")
        assert hasattr(mod, "get_engine")

    def test_get_engine_returns_engine(self):
        from eli.brain.cognitive_engine import get_engine
        engine = get_engine()
        assert engine is not None
        assert hasattr(engine, "process") or hasattr(engine, "process_chat")

    def test_engine_has_memory_or_context(self):
        from eli.brain.cognitive_engine import get_engine
        engine = get_engine()
        assert any(hasattr(engine, name) for name in ["memory", "_memory", "session_id", "user_id"])


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 12 – Plugins
# ══════════════════════════════════════════════════════════════════════════════

class TestS12Plugins:

    def test_register_all_plugins(self):
        from eli.plugins.base import register_all_plugins
        register_all_plugins()

    def test_weather_plugin_instantiates(self):
        from eli.plugins.weather import WeatherPlugin
        assert WeatherPlugin() is not None

    def test_calendar_plugin_instantiates(self):
        from eli.plugins.calendar import CalendarPlugin
        assert CalendarPlugin() is not None

    def test_tts_plugin_importable(self):
        from eli.plugins import tts  # noqa: F401


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 13 – Router → Executor Full Round-Trip
# ══════════════════════════════════════════════════════════════════════════════

_ROUNDTRIP_CASES = [
    ("what time is it",             "TIME",              True),
    ("what date is it",             "DATE",              True),
    ("list files in /tmp",          "LIST_DIR",          True),
    ("read /etc/hostname",          "READ_FILE",         True),
    ("remember that ELI was here",  "MEMORY_STORE",      True),
    ("recall ELI was here",         "MEMORY_RECALL",     True),
    ("list capabilities",           "LIST_CAPABILITIES", True),
    ("analyze yourself",            "SELF_ANALYZE",      True),
    ("morning report",              "MORNING_REPORT",    True),
    ("proactive status",            "PROACTIVE_STATUS",  True),
]


@pytest.mark.skipif(
    not (_ROUTER_OK and _EXECUTOR_OK),
    reason="router or executor import failed",
)
class TestS13Roundtrip:

    @pytest.mark.parametrize("text,exp_action,exp_ok", _ROUNDTRIP_CASES)
    def test_roundtrip(self, text, exp_action, exp_ok):
        routed = route(text)
        action = routed.get("action", "")
        args   = routed.get("args", {})
        result = execute(action, args)

        assert _route_ok(action, exp_action), (
            f"route({text!r}) → {action!r}, expected {exp_action!r}"
        )
        assert isinstance(result, dict) and "ok" in result
        if exp_ok:
            assert result.get("ok") is True, (
                f"execute({action!r}) failed: {result}"
            )
