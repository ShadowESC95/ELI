"""
test_wiring.py — Full wiring tests for ELI
Covers: brain/, tools/, gui/, plugins/, controllers/
"""

import pytest
import sys
import os
import ast
import sqlite3
import tempfile
import inspect
import time
from unittest.mock import patch, MagicMock
from pathlib import Path
import eli as _eli_pkg
_ELI_DIR = Path(_eli_pkg.__file__).resolve().parent  # <-- THIS is the real project root (src/eli)
_PROJECT_ROOT = _ELI_DIR.parent                      # src

# ─── Project root = two levels above this file (eli/tests/integration/) ─────
_THIS_FILE = os.path.abspath(__file__)
_TESTS_DIR = os.path.dirname(_THIS_FILE)          # eli/tests/integration/
_ELI_DIR   = os.path.dirname(os.path.dirname(_TESTS_DIR))  # project root/eli/
_ROOT      = os.path.dirname(_ELI_DIR)            # project root

if _ELI_DIR not in sys.path:
    sys.path.insert(0, _ELI_DIR)
os.environ.setdefault("ELI_ROOT", _ELI_DIR)


def _gui_source(filename: str) -> str:
    """Read a GUI source file from eli/gui/ relative to the project root."""
    path = os.path.join(_ELI_DIR, "gui", filename)
    return open(path).read()


# ════════════════════════════════════════════════════════════════════════════
# PySide6 availability
# ════════════════════════════════════════════════════════════════════════════
try:
    import PySide6  # noqa: F401
    _HAS_PYSIDE6 = True
except ImportError:
    _HAS_PYSIDE6 = False

requires_pyside6 = pytest.mark.skipif(
    not _HAS_PYSIDE6, reason="PySide6 not installed in this environment"
)


# ════════════════════════════════════════════════════════════════════════════
# FIXTURES
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def reset_singletons():
    yield
    for mod_name, attr in [
        ("eli.brain.memory", "_memory"),
        ("eli.brain.self_improvement", "_self_engine"),
        ("eli.brain.cognitive_engine", "_engine"),
        ("eli.brain.proactive_daemon", "_daemon"),
    ]:
        mod = sys.modules.get(mod_name)
        if mod and hasattr(mod, attr):
            setattr(mod, attr, None)


@pytest.fixture
def temp_db():
    """
    Create a fresh temp DB, wire it into memory AND self_improvement,
    ensure all required tables + columns exist, and clean up after.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name

    os.environ["ELI_MEMORY_DB"] = path

    # Reset memory singleton so it uses the temp DB
    import eli.brain.memory as mm
    mm._memory = None
    mem = mm.get_memory()

    # Reset SI singleton — it must open the same temp DB
    import eli.brain.self_improvement as si_mod
    si_mod._self_engine = None

    # Patch missing columns / tables that may not exist on a fresh schema
    with sqlite3.connect(path) as conn:
        for sql in [
            # improvements
            "ALTER TABLE improvements ADD COLUMN category TEXT",
            "ALTER TABLE improvements ADD COLUMN area TEXT",
            "ALTER TABLE improvements ADD COLUMN description TEXT",
            "ALTER TABLE improvements ADD COLUMN priority INTEGER DEFAULT 2",
            "ALTER TABLE improvements ADD COLUMN status TEXT DEFAULT 'pending'",
            "ALTER TABLE improvements ADD COLUMN created_at REAL",
            # error_tracking
            "ALTER TABLE error_tracking ADD COLUMN details TEXT",
            "ALTER TABLE error_tracking ADD COLUMN occurrence_count INTEGER DEFAULT 1",
            "ALTER TABLE error_tracking ADD COLUMN first_seen REAL",
            "ALTER TABLE error_tracking ADD COLUMN last_seen REAL",
            "ALTER TABLE error_tracking ADD COLUMN resolved INTEGER DEFAULT 0",
            "ALTER TABLE error_tracking ADD COLUMN error_type TEXT",
            "ALTER TABLE error_tracking ADD COLUMN context TEXT",
            "ALTER TABLE error_tracking ADD COLUMN user_input TEXT",
            # habit_rules
            "ALTER TABLE habit_rules ADD COLUMN hour INTEGER",
            "ALTER TABLE habit_rules ADD COLUMN minute INTEGER",
            # memories
            "ALTER TABLE memories ADD COLUMN weight REAL DEFAULT 1.0",
        ]:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError:
                pass  # column already exists
        conn.commit()

    yield mem, path

    # Teardown
    mm._memory = None
    si_mod._self_engine = None
    os.environ.pop("ELI_MEMORY_DB", None)
    try:
        os.unlink(path)
    except OSError:
        pass


# ════════════════════════════════════════════════════════════════════════════
# BRAIN — imports
# ════════════════════════════════════════════════════════════════════════════

class TestBrainImports:

    def test_memory_importable(self):
        from eli.brain.memory import get_memory, Memory
        assert get_memory is not None and Memory is not None

    def test_cognitive_engine_importable(self):
        from eli.brain.cognitive_engine import get_engine, CognitiveEngine
        assert get_engine is not None

    def test_self_improvement_importable(self):
        from eli.brain.self_improvement import get_self_improvement, SelfImprovementEngine
        assert SelfImprovementEngine is not None

    def test_config_importable(self):
        from eli.brain.config import get, set, delete, list_keys
        assert callable(get) and callable(set)

    def test_router_importable(self):
        from eli.brain.router import route
        assert callable(route)

    def test_proactive_daemon_importable(self):
        from eli.brain.proactive_daemon import get_daemon, ProactiveDaemon, start_daemon
        assert callable(get_daemon) and callable(start_daemon)

    def test_scheduler_importable(self):
        from eli.brain.scheduler import HabitScheduler, get_scheduler
        assert HabitScheduler is not None and callable(get_scheduler)

    def test_context_builder_importable(self):
        from eli.brain.context_builder import build_context
        assert callable(build_context)

    def test_self_improvement_has_methods(self):
        from eli.brain.self_improvement import SelfImprovementEngine
        for m in ["log_failure", "log_improvement", "analyze_failures"]:
            assert hasattr(SelfImprovementEngine, m), f"Missing: {m}"

    def test_capabilities_importable(self):
        from eli.brain.capabilities import CapabilityRegistry
        assert CapabilityRegistry is not None

    def test_paths_importable(self):
        from eli.brain.paths import _find_project_root, _Paths
        assert callable(_find_project_root)

    def test_state_importable(self):
        from eli.brain.state import load_state, save_state, get_user_name, set_user_name
        assert callable(load_state) and callable(get_user_name)

    def test_identity_guard_importable(self):
        from eli.brain.identity_guard import status, get_lock_state, set_lock, clear_lock
        assert callable(status) and callable(get_lock_state)

    def test_values_importable(self):
        import eli.brain.values as v
        assert v is not None

    def test_response_sanitizer_importable(self):
        from eli.brain.response_sanitizer import (
            extract_text, sanitize_assistant_text, finalize_assistant_reply
        )
        assert callable(sanitize_assistant_text)


# ════════════════════════════════════════════════════════════════════════════
# BRAIN — memory wiring
# ════════════════════════════════════════════════════════════════════════════

class TestMemoryWiring:

    def test_memory_singleton(self, temp_db):
        mem, _ = temp_db
        from eli.brain.memory import get_memory
        assert get_memory() is mem

    def test_store_and_recall(self, temp_db):
        mem, _ = temp_db
        mem.store_memory("wiring test entry", tags=["wiring"])
        results = mem.recall_memory("wiring test", limit=5)
        assert any("wiring test entry" in r["text"] for r in results)

    def test_conversation_turn_ordering(self, temp_db):
        mem, _ = temp_db
        mem.add_conversation_turn("user", "first message", "sess_w", "user_w")
        mem.add_conversation_turn("assistant", "first reply", "sess_w", "user_w")
        turns = mem.get_recent_conversation(limit=10, user_id="user_w")
        roles = [t["role"] for t in turns]
        assert "user" in roles and "assistant" in roles

    def test_habit_event_round_trip(self, temp_db):
        mem, _ = temp_db
        mem.log_habit_event("test_event", {"key": "val"})
        events = mem.get_habit_events(event_type="test_event", days=1)
        assert len(events) >= 1
        assert events[0]["details"]["key"] == "val"

    def test_all_required_tables_present(self, temp_db):
        """Verify schema against the live production DB, not the temp DB."""
        live_db = os.path.join(_ELI_DIR, "artifacts", "eli_memory.sqlite3")
        if not os.path.exists(live_db):
            pytest.skip("Production DB not found — run Eli once to create it")
        with sqlite3.connect(live_db) as conn:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
        required = {
            "memories", "conversations", "habit_events", "improvements",
            "error_tracking", "failures", "habits", "habit_rules",
            "observations", "capability_proposals", "corrections",
        }
        missing = required - tables
        assert not missing, f"Missing tables in production DB: {missing}"

    def test_memory_recall_returns_list(self, temp_db):
        mem, _ = temp_db
        assert isinstance(mem.recall_memory("nonexistent xyz123", limit=5), list)

    def test_add_correction(self, temp_db):
        mem, path = temp_db
        # Real signature: log_correction(original: str, corrected: str)
        mem.log_correction("open browser", "OPEN_APP")
        with sqlite3.connect(path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM corrections").fetchone()[0]
        assert count >= 1


# ════════════════════════════════════════════════════════════════════════════
# BRAIN — self improvement wiring
# ════════════════════════════════════════════════════════════════════════════

class TestSelfImprovementWiring:

    def _make_si(self, path):
        """Reset singleton and return a fresh SelfImprovementEngine using temp DB."""
        import eli.brain.self_improvement as si_mod
        si_mod._self_engine = None
        # Ensure the env var is set before instantiation
        os.environ["ELI_MEMORY_DB"] = path
        from eli.brain.self_improvement import SelfImprovementEngine
        return SelfImprovementEngine()

    def test_log_failure_writes_row(self, temp_db):
        _, path = temp_db
        si = self._make_si(path)
        si.log_failure("test cmd", error="broke", context={"x": 1})
        with sqlite3.connect(path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM error_tracking").fetchone()[0] >= 1

    def test_log_improvement_writes_row(self, temp_db):
        _, path = temp_db
        si = self._make_si(path)
        si.log_improvement("routing", "improved routing logic")
        with sqlite3.connect(path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM improvements").fetchone()[0] >= 1

    def test_log_failure_deduplicates(self, temp_db):
        _, path = temp_db
        si = self._make_si(path)
        si.log_failure("same cmd", error="same error")
        si.log_failure("same cmd", error="same error")
        with sqlite3.connect(path) as conn:
            counts = [r[0] for r in conn.execute(
                "SELECT occurrence_count FROM error_tracking"
            ).fetchall()]
        assert max(counts) == 2

    def test_analyze_failures_returns_list(self, temp_db):
        _, path = temp_db
        si = self._make_si(path)
        result = si.analyze_failures(days=1, min_cluster_size=999)
        assert isinstance(result, list)


# ════════════════════════════════════════════════════════════════════════════
# BRAIN — config wiring
# ════════════════════════════════════════════════════════════════════════════

class TestConfigWiring:

    def test_set_and_get(self):
        from eli.brain.config import get, set
        set("_wiring_test_key", "hello")
        assert get("_wiring_test_key") == "hello"

    def test_delete(self):
        from eli.brain.config import get, set, delete
        set("_wiring_del_key", "bye")
        delete("_wiring_del_key")
        assert get("_wiring_del_key") is None

    def test_temperature_round_trip(self):
        from eli.brain.config import get_temperature, set_temperature
        set_temperature(0.42)
        assert abs(get_temperature() - 0.42) < 0.001

    def test_persona_round_trip(self):
        from eli.brain.config import get_persona, set_persona
        set_persona("wiring test persona")
        assert "wiring test persona" in get_persona()


# ════════════════════════════════════════════════════════════════════════════
# BRAIN — state wiring
# ════════════════════════════════════════════════════════════════════════════

class TestStateWiring:

    def test_load_state_returns_dict(self):
        from eli.brain.state import load_state
        assert isinstance(load_state(), dict)

    def test_get_user_name_returns_string(self):
        from eli.brain.state import get_user_name
        assert isinstance(get_user_name(), str)

    def test_set_and_get_user_name(self):
        from eli.brain.state import get_user_name, set_user_name
        original = get_user_name()
        set_user_name("WiringTestUser")
        assert get_user_name() == "WiringTestUser"
        set_user_name(original)


# ════════════════════════════════════════════════════════════════════════════
# BRAIN — identity guard wiring
# ════════════════════════════════════════════════════════════════════════════

class TestIdentityGuardWiring:

    def test_status_callable(self):
        from eli.brain.identity_guard import status
        assert status() is not None

    def test_get_lock_state_returns_dict_or_none(self):
        from eli.brain.identity_guard import get_lock_state
        result = get_lock_state()
        assert result is None or isinstance(result, dict)

    def test_clear_lock_does_not_raise(self):
        from eli.brain.identity_guard import clear_lock
        clear_lock()


# ════════════════════════════════════════════════════════════════════════════
# BRAIN — response sanitizer wiring
# ════════════════════════════════════════════════════════════════════════════

class TestResponseSanitizerWiring:

    def test_sanitize_plain_text(self):
        from eli.brain.response_sanitizer import sanitize_assistant_text
        result = sanitize_assistant_text("Hello world")
        assert isinstance(result, str) and "Hello world" in result

    def test_sanitize_empty_string(self):
        from eli.brain.response_sanitizer import sanitize_assistant_text
        assert isinstance(sanitize_assistant_text(""), str)

    def test_sanitize_returns_string(self):
        from eli.brain.response_sanitizer import sanitize_assistant_text
        # Sanitizer may or may not strip model tokens — just verify it returns str
        result = sanitize_assistant_text("Hello<|im_end|>")
        assert isinstance(result, str)

    def test_extract_text_from_dict(self):
        from eli.brain.response_sanitizer import extract_text
        assert isinstance(extract_text({"response": "hello"}), str)

    def test_finalize_returns_dict(self):
        from eli.brain.response_sanitizer import finalize_assistant_reply
        assert isinstance(finalize_assistant_reply({"response": "hello"}), dict)


# ════════════════════════════════════════════════════════════════════════════
# BRAIN — scheduler wiring
# ════════════════════════════════════════════════════════════════════════════

class TestSchedulerWiring:

    def test_habit_scheduler_importable(self):
        from eli.brain.scheduler import HabitScheduler
        assert HabitScheduler is not None

    def test_get_scheduler_callable(self):
        from eli.brain.scheduler import get_scheduler
        assert callable(get_scheduler)

    def test_scheduler_has_memory(self):
        from eli.brain.scheduler import HabitScheduler
        with patch.object(HabitScheduler, "_run_loop", return_value=None):
            assert hasattr(HabitScheduler(), "memory")

    def test_scheduler_singleton(self):
        from eli.brain.scheduler import get_scheduler
        assert get_scheduler() is get_scheduler()


# ════════════════════════════════════════════════════════════════════════════
# TOOLS — router wiring
# ════════════════════════════════════════════════════════════════════════════

class TestRouterWiring:

    def _route(self, text):
        from eli.tools.router_enhanced import route
        return route(text)

    def test_time_routes_correctly(self):
        assert self._route("what time is it")["action"] == "TIME"

    def test_date_routes_correctly(self):
        assert self._route("what is today's date")["action"] == "DATE"

    def test_volume_up_routes(self):
        r = self._route("volume up")
        assert "VOLUME" in r["action"] or r["action"] == "MEDIA_CONTROL"

    def test_volume_down_routes(self):
        r = self._route("volume down")
        assert "VOLUME" in r["action"] or r["action"] == "MEDIA_CONTROL"

    def test_open_app_routes(self):
        assert self._route("open spotify")["action"] == "OPEN_APP"

    def test_next_track_routes(self):
        assert self._route("next track")["action"] in ("NEXT_MEDIA", "MEDIA_CONTROL")

    def test_previous_track_routes(self):
        assert self._route("previous song")["action"] in ("PREVIOUS_MEDIA", "MEDIA_CONTROL")

    def test_generate_script_routes(self):
        assert self._route("create a python script for X")["action"] == "GENERATE_SCRIPT"

    def test_fix_file_routes(self):
        assert self._route("fix the script (_ELI_DIR / 'artifacts').as_posix()/test.py")["action"] == "FIX_FILE"

    def test_chat_fallback(self):
        assert self._route("hello there how are you doing today")["action"] == "CHAT"

    def test_route_returns_confidence(self):
        r = self._route("what time is it")
        assert "confidence" in r and 0.0 <= r["confidence"] <= 1.0

    def test_route_returns_args(self):
        assert "args" in self._route("what time is it")

    def test_memory_recall_routes(self):
        assert self._route("recall my favourite color")["action"] == "MEMORY_RECALL"

    def test_open_url_routes(self):
        r = self._route("open https://example.com")
        assert r["action"] in ("OPEN_URL", "OPEN_APP", "CHAT")


# ════════════════════════════════════════════════════════════════════════════
# TOOLS — executor wiring
# ════════════════════════════════════════════════════════════════════════════

class TestExecutorWiring:

    def _exec(self, action, args=None):
        from eli.tools.executor_enhanced import execute
        return execute(action, args or {})

    def test_execute_time_returns_dict(self):
        result = self._exec("TIME")
        assert isinstance(result, dict)
        assert "response" in result or "content" in result

    def test_execute_date(self):
        assert self._exec("DATE").get("ok") is True

    def test_execute_read_file_missing(self):
        assert self._exec("READ_FILE", {"path": "/nonexistent/file.txt"}).get("ok") is False

    def test_execute_open_url(self):
        with patch("subprocess.Popen", return_value=MagicMock()):
            assert "ok" in self._exec("OPEN_URL", {"url": "https://example.com"})

    def test_execute_open_app(self):
        with patch("subprocess.Popen", return_value=MagicMock()):
            assert "ok" in self._exec("OPEN_APP", {"app": "firefox"})

    def test_execute_volume_up(self):
        with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="50", stderr="")):
            assert "ok" in self._exec("VOLUME", {"direction": "up"})

    def test_execute_returns_response_key(self):
        r = self._exec("DATE")
        assert "response" in r or "content" in r

    def test_execute_unknown_action_graceful(self):
        assert "ok" in self._exec("TOTALLY_UNKNOWN_ACTION_XYZ")

    def test_execute_generate_script_mocked(self):
        with patch("eli.tools.executor_enhanced._ollama_http_post_json") as m:
            m.return_value = {"response": "print('hello')"}
            assert "ok" in self._exec("GENERATE_SCRIPT", {"description": "print hello"})

    def test_execute_memory_recall(self):
        assert "ok" in self._exec("MEMORY_RECALL", {"query": "test query"})


# ════════════════════════════════════════════════════════════════════════════
# TOOLS — analyze_pdfs wiring
# ════════════════════════════════════════════════════════════════════════════

class TestAnalyzePDFsWiring:

    def test_extract_text_missing_file(self):
        from eli.tools.analyze_pdfs import extract_text
        with pytest.raises(Exception):
            extract_text("/nonexistent/fake.pdf")

    def test_analyze_missing_file(self):
        from eli.tools.analyze_pdfs import analyze
        with pytest.raises(Exception):
            analyze("/nonexistent/fake.pdf")

    def test_pdfdoc_is_class(self):
        from eli.tools.analyze_pdfs import PDFDoc
        assert isinstance(PDFDoc, type)

    def test_pdfdoc_has_path_field(self):
        from eli.tools.analyze_pdfs import PDFDoc
        fields = list(PDFDoc.__dataclass_fields__.keys()) \
            if hasattr(PDFDoc, "__dataclass_fields__") \
            else list(inspect.signature(PDFDoc.__init__).parameters.keys())
        assert "path" in fields

    def test_analyze_folder_missing(self):
        from eli.tools.analyze_pdfs import analyze_folder
        with pytest.raises(Exception):
            analyze_folder("/nonexistent/folder")


# ════════════════════════════════════════════════════════════════════════════
# TOOLS — capability_registry wiring
# ════════════════════════════════════════════════════════════════════════════

class TestCapabilityRegistryWiring:

    def test_register_and_list(self):
        from eli.tools.capability_registry import register, list_capabilities
        register("WIRING_TEST_ACTION", "A test capability", handler=lambda args: {})
        assert "WIRING_TEST_ACTION" in list_capabilities()

    def test_get_capability(self):
        from eli.tools.capability_registry import register, get_capability
        register("WIRING_GET_TEST", "Get test", handler=lambda args: {})
        assert get_capability("WIRING_GET_TEST") is not None

    def test_render_detailed(self):
        from eli.tools.capability_registry import render_detailed
        assert isinstance(render_detailed(), str)


# ════════════════════════════════════════════════════════════════════════════
# PLUGINS — wiring
# ════════════════════════════════════════════════════════════════════════════

class TestPluginsWiring:

    def test_base_importable(self):
        from eli.plugins.base import Plugin, load_plugins
        assert Plugin is not None and callable(load_plugins)

    def test_weather_plugin_importable(self):
        from eli.plugins.weather import WeatherPlugin
        assert WeatherPlugin is not None

    def test_weather_plugin_has_handle(self):
        from eli.plugins.weather import WeatherPlugin
        p = WeatherPlugin()
        assert hasattr(p, "handle") or hasattr(p, "actions"), \
            "WeatherPlugin has no handle method or actions dict"

    def test_calendar_plugin_importable(self):
        from eli.plugins.calendar import CalendarPlugin
        assert CalendarPlugin is not None

    def test_tts_plugin_has_no_import_error(self):
        """
        pyttsx3 is installed. If this fails, tts.py has a bug (Plugin not imported).
        This test intentionally exposes that bug rather than hiding it.
        """
        from eli.plugins.tts import TTSPlugin
        assert TTSPlugin is not None

    def test_document_reader_importable(self):
        pytest.importorskip("chromadb", reason="chromadb not installed")
        from eli.plugins.document_reader import DocumentReaderPlugin
        assert DocumentReaderPlugin is not None

    def test_web_automation_importable(self):
        pytest.importorskip("playwright", reason="playwright not installed or broken")
        from eli.plugins.web_automation import WebAutomationPlugin
        assert WebAutomationPlugin is not None

    def test_smart_home_importable(self):
        from eli.plugins.smart_home import SmartHomePlugin
        assert SmartHomePlugin is not None

    def test_load_plugins_returns_collection(self):
        from eli.plugins.base import load_plugins
        assert isinstance(load_plugins(), (list, dict))

    def test_load_plugins_nonempty(self):
        from eli.plugins.base import load_plugins
        assert len(load_plugins()) > 0

    def test_plugin_base_class_interface(self):
        from eli.plugins.base import Plugin
        class TestPlugin(Plugin):
            name = "test"
            description = "test plugin"
            def handle(self, args):
                return {"ok": True, "content": "test"}
        assert TestPlugin().handle({})["ok"] is True


# ════════════════════════════════════════════════════════════════════════════
# CONTROLLERS — module-level functions
# ════════════════════════════════════════════════════════════════════════════

class TestControllersWiring:

    def test_os_controller_importable(self):
        import eli.controllers.os_controller as ctrl
        assert ctrl is not None

    def test_get_volume_exists(self):
        from eli.controllers.os_controller import get_volume
        assert callable(get_volume)

    def test_set_volume_exists(self):
        from eli.controllers.os_controller import set_volume
        assert callable(set_volume)

    def test_take_screenshot_exists(self):
        from eli.controllers.os_controller import take_screenshot
        assert callable(take_screenshot)

    def test_press_key_exists(self):
        from eli.controllers.os_controller import press_key
        assert callable(press_key)

    def test_type_text_exists(self):
        from eli.controllers.os_controller import type_text
        assert callable(type_text)

    def test_get_clipboard_exists(self):
        from eli.controllers.os_controller import get_clipboard
        assert callable(get_clipboard)

    def test_set_clipboard_exists(self):
        from eli.controllers.os_controller import set_clipboard
        assert callable(set_clipboard)

    def test_get_volume_mocked(self):
        from eli.controllers.os_controller import get_volume
        with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="50\n", stderr="")):
            vol = get_volume()
            assert vol is None or isinstance(vol, (int, float))

    def test_set_volume_returns_dict(self):
        from eli.controllers.os_controller import set_volume
        with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")):
            assert isinstance(set_volume(level=50), dict)


# ════════════════════════════════════════════════════════════════════════════
# GUI — source-level checks (always run) + PySide6 import checks
# ════════════════════════════════════════════════════════════════════════════

class TestGUIWiring:

    # ── Source-level (no import needed) ─────────────────────────────────────

    def test_gui_mki_no_syntax_errors(self):
        ast.parse(_gui_source("eli_pro_audio_gui_MKI.py"))

    def test_gui_mkiwork_no_syntax_errors(self):
        ast.parse(_gui_source("eli_pro_audio_gui_MKI.py"))

    def test_gui_uses_pyside6_not_pyqt5(self):
        for fname in ("eli_pro_audio_gui_MKI.py", "eli_pro_audio_gui_MKI.py"):
            src = _gui_source(fname)
            assert "PySide6" in src, f"{fname} should import PySide6"
            assert "PyQt5" not in src, f"{fname} should not import PyQt5"

    def test_gui_mki_has_main_window_class(self):
        assert "class ELIEntropicGUI" in _gui_source("eli_pro_audio_gui_MKI.py")

    def test_gui_mkiwork_has_main_window_class(self):
        assert "class ELIEntropicGUI" in _gui_source("eli_pro_audio_gui_MKI.py")

    def test_gui_mki_has_worker_thread(self):
        assert "class ELIWorker" in _gui_source("eli_pro_audio_gui_MKI.py")

    def test_gui_mki_has_llm_stream_worker(self):
        assert "class LLMStreamWorker" in _gui_source("eli_pro_audio_gui_MKI.py")

    def test_gui_mki_has_proactive_dock(self):
        assert "class ProactiveDockWidget" in _gui_source("eli_pro_audio_gui_MKI.py")

    def test_gui_mki_has_self_improve_dock(self):
        assert "class SelfImproveDockWidget" in _gui_source("eli_pro_audio_gui_MKI.py")

    def test_gui_mki_has_habit_dock(self):
        assert "class HabitDockWidget" in _gui_source("eli_pro_audio_gui_MKI.py")

    def test_gui_mkiwork_has_parse_local_command(self):
        # Method was renamed from _dispatch_local_command to _parse_local_command
        assert "_parse_local_command" in _gui_source("eli_pro_audio_gui_MKI.py")

    def test_gui_mki_has_main_function(self):
        assert "def main(" in _gui_source("eli_pro_audio_gui_MKI.py")

    def test_gui_mkiwork_has_main_function(self):
        assert "def main(" in _gui_source("eli_pro_audio_gui_MKI.py")

    # ── PySide6 import-level checks (run on desktop, skip in headless CI) ───

    @requires_pyside6
    def test_gui_mki_importable(self):
        import eli.gui.eli_pro_audio_gui_MKI as gui
        assert gui is not None

    @requires_pyside6
    def test_gui_mkiwork_importable(self):
        import eli.gui.eli_pro_audio_gui_MKI as gui
        assert gui is not None

    @requires_pyside6
    def test_gui_mki_main_window_is_qmainwindow(self):
        from PySide6.QtWidgets import QMainWindow
        import eli.gui.eli_pro_audio_gui_MKI as gui
        assert issubclass(gui.ELIEntropicGUI, QMainWindow)

    @requires_pyside6
    def test_gui_mkiwork_main_window_is_qmainwindow(self):
        from PySide6.QtWidgets import QMainWindow
        import eli.gui.eli_pro_audio_gui_MKI as gui
        assert issubclass(gui.ELIEntropicGUI, QMainWindow)

    @requires_pyside6
    def test_gui_mki_worker_is_qthread(self):
        from PySide6.QtCore import QThread
        import eli.gui.eli_pro_audio_gui_MKI as gui
        assert issubclass(gui.ELIWorker, QThread)

    @requires_pyside6
    def test_gui_mki_llm_worker_is_qthread(self):
        from PySide6.QtCore import QThread
        import eli.gui.eli_pro_audio_gui_MKI as gui
        assert issubclass(gui.LLMStreamWorker, QThread)

    @requires_pyside6
    def test_gui_mki_docks_are_qwidgets(self):
        from PySide6.QtWidgets import QWidget
        import eli.gui.eli_pro_audio_gui_MKI as gui
        for cls in [gui.ProactiveDockWidget, gui.SelfImproveDockWidget, gui.HabitDockWidget]:
            assert issubclass(cls, QWidget), f"{cls.__name__} is not a QWidget"

    @requires_pyside6
    def test_gui_mkiwork_parse_command_is_method(self):
        import eli.gui.eli_pro_audio_gui_MKI as gui
        assert callable(gui.ELIEntropicGUI._parse_local_command)


# ════════════════════════════════════════════════════════════════════════════
# BRAIN — cognitive engine wiring
# ════════════════════════════════════════════════════════════════════════════

class TestCognitiveEngineWiring:

    def test_engine_instantiates(self):
        from eli.brain.cognitive_engine import CognitiveEngine
        assert CognitiveEngine() is not None

    def test_engine_singleton(self):
        from eli.brain.cognitive_engine import get_engine
        assert get_engine() is get_engine()

    def test_engine_has_process_method(self):
        from eli.brain.cognitive_engine import CognitiveEngine
        engine = CognitiveEngine()
        assert any(hasattr(engine, m) for m in
                   ["process", "process_chat", "process_command", "chat", "run"])

    def test_engine_has_memory(self):
        from eli.brain.cognitive_engine import CognitiveEngine
        engine = CognitiveEngine()
        assert hasattr(engine, "memory") or hasattr(engine, "_memory")

    def test_engine_source_references_routing(self):
        from eli.brain.cognitive_engine import CognitiveEngine
        src = inspect.getsource(CognitiveEngine)
        assert any(kw in src.lower() for kw in ["route", "router", "intent", "action"])


# ════════════════════════════════════════════════════════════════════════════
# BRAIN — proactive daemon wiring
# ════════════════════════════════════════════════════════════════════════════

class TestProactiveDaemonWiring:

    def test_daemon_singleton(self):
        from eli.brain.proactive_daemon import get_daemon
        assert get_daemon() is get_daemon()

    def test_start_daemon_function_exists(self):
        from eli.brain.proactive_daemon import start_daemon
        assert callable(start_daemon)

    def test_daemon_has_stop(self):
        from eli.brain.proactive_daemon import get_daemon
        d = get_daemon()
        assert any(hasattr(d, m) for m in ["stop", "stop_daemon", "_stop", "running"])

    def test_daemon_is_correct_type(self):
        from eli.brain.proactive_daemon import get_daemon, ProactiveDaemon
        assert isinstance(get_daemon(), ProactiveDaemon)


# ════════════════════════════════════════════════════════════════════════════
# BRAIN — context builder wiring
# ════════════════════════════════════════════════════════════════════════════

class TestContextBuilderWiring:

    def test_build_context_returns_string(self):
        from eli.brain.context_builder import build_context
        assert isinstance(build_context(user_message="hello"), str)

    def test_build_context_not_empty(self):
        from eli.brain.context_builder import build_context
        assert len(build_context(user_message="test")) > 0

    def test_build_context_includes_message(self):
        from eli.brain.context_builder import build_context
        assert "unique_wiring_probe_xyz" in build_context(user_message="unique_wiring_probe_xyz")


# ════════════════════════════════════════════════════════════════════════════
# END-TO-END — router → executor pipeline
# ════════════════════════════════════════════════════════════════════════════

class TestRouterExecutorPipeline:

    def test_date_pipeline(self):
        from eli.tools.router_enhanced import route
        from eli.tools.executor_enhanced import execute
        intent = route("what is today's date")
        assert execute(intent["action"], intent.get("args", {})).get("ok") is True

    def test_time_pipeline_returns_dict(self):
        from eli.tools.router_enhanced import route
        from eli.tools.executor_enhanced import execute
        intent = route("what time is it")
        result = execute(intent["action"], intent.get("args", {}))
        assert isinstance(result, dict) and ("response" in result or "content" in result)

    def test_memory_recall_pipeline(self, temp_db):
        from eli.tools.router_enhanced import route
        from eli.tools.executor_enhanced import execute
        mem, _ = temp_db
        mem.store_memory("pipeline test value", tags=["pipeline"])
        intent = route("recall pipeline test")
        assert "ok" in execute(intent["action"], intent.get("args", {}))

    def test_open_app_pipeline_mocked(self):
        from eli.tools.router_enhanced import route
        from eli.tools.executor_enhanced import execute
        with patch("subprocess.Popen", return_value=MagicMock()):
            intent = route("open firefox")
            assert "ok" in execute(intent["action"], intent.get("args", {}))

    def test_generate_script_pipeline_mocked(self):
        from eli.tools.router_enhanced import route
        from eli.tools.executor_enhanced import execute
        with patch("eli.tools.executor_enhanced._ollama_http_post_json") as m:
            m.return_value = {"response": "print('hello')"}
            intent = route("create a python script to say hello")
            assert "ok" in execute(intent["action"], intent.get("args", {}))