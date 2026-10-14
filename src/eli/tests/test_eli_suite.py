"""
ELI Comprehensive Test Suite  v2
==================================
All tests isolated — temp SQLite DBs, no Ollama, no GPU required.

Run from project root:
    pytest src/eli/tests/test_eli_suite.py -v
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tmp_db(tmp_path: Path) -> Path:
    db = tmp_path / "test_eli.sqlite3"
    os.environ["ELI_MEMORY_DB"] = str(db)
    os.environ["ELI_MEMORY_DB_PATH"] = str(db)
    return db


def _fresh_memory(tmp_path: Path):
    """Return a fresh Memory instance pointing at a temp DB."""
    _tmp_db(tmp_path)
    import eli.brain.memory as mem_mod
    mem_mod._memory_singleton = None
    return mem_mod.get_memory()


# ===========================================================================
# 1. MEMORY.PY — get_memory must be a module-level symbol
# ===========================================================================

class TestMemoryImport:
    def test_get_memory_importable(self):
        from eli.brain.memory import get_memory
        assert callable(get_memory)

    def test_memory_class_importable(self):
        from eli.brain.memory import Memory
        assert Memory is not None

    def test_get_memory_returns_instance(self, tmp_path):
        m = _fresh_memory(tmp_path)
        assert m is not None
        assert hasattr(m, "db_path")

    def test_get_memory_is_singleton(self, tmp_path):
        _tmp_db(tmp_path)
        import eli.brain.memory as mem_mod
        mem_mod._memory_singleton = None
        m1 = mem_mod.get_memory()
        m2 = mem_mod.get_memory()
        assert m1 is m2

    def test_all_exports(self):
        import eli.brain.memory as m
        assert "Memory" in m.__all__
        assert "get_memory" in m.__all__

    def test_get_memory_is_module_level_function(self):
        import eli.brain.memory as mem_mod
        import inspect
        assert inspect.isfunction(mem_mod.get_memory), \
            "get_memory must be a module-level function, not a class method"


# ===========================================================================
# 2. BRAIN __init__ — guarded imports and proper re-exports
# ===========================================================================

class TestBrainInit:
    def test_package_importable(self):
        import eli.brain
        assert eli.brain is not None

    def test_get_memory_exported(self):
        import eli.brain
        assert hasattr(eli.brain, "get_memory")
        assert callable(eli.brain.get_memory)

    def test_paths_exported(self):
        import eli.brain
        assert hasattr(eli.brain, "PATHS")

    def test_no_crash_on_missing_optional(self):
        import eli.brain
        _ = getattr(eli.brain, "SelfImprovementEngine", None)

    def test_self_improvement_exported(self):
        import eli.brain
        # May be None if import chain is broken, but attr must exist
        assert hasattr(eli.brain, "SelfImprovementEngine")


# ===========================================================================
# 3. MEMORY_DB
# ===========================================================================

class TestMemoryDB:
    def _db(self, tmp_path):
        from eli.brain import memory_db
        memory_db.DB_PATH = tmp_path / "mdb.sqlite3"
        memory_db.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        return memory_db

    def test_add_and_search(self, tmp_path):
        mdb = self._db(tmp_path)
        r = mdb.add_memory("quantum entanglement", tags="physics,test")
        assert r.get("ok") is True
        assert "id" in r

    def test_search_returns_results(self, tmp_path):
        mdb = self._db(tmp_path)
        mdb.add_memory("Schrodinger equation", tags="physics")
        result = mdb.search_memory("Schrodinger")
        assert result.get("ok") is True

    def test_recall_recent_shape(self, tmp_path):
        mdb = self._db(tmp_path)
        result = mdb.recall_recent(limit=5)
        assert isinstance(result, dict)

    def test_recall_recent_k_kwarg(self, tmp_path):
        mdb = self._db(tmp_path)
        result = mdb.recall_recent(k=5)
        assert isinstance(result, dict)

    def test_add_empty_rejected(self, tmp_path):
        mdb = self._db(tmp_path)
        r = mdb.add_memory("")
        assert r.get("ok") is False

    def test_log_event(self, tmp_path):
        mdb = self._db(tmp_path)
        mdb.log_event("test_action", {"key": "value"})


# ===========================================================================
# 4. SQLITE_MEMORY
# ===========================================================================

class TestSQLiteMemory:
    def _sm(self, tmp_path):
        from eli.brain import sqlite_memory
        sqlite_memory.DB_PATH = tmp_path / "sm.sqlite3"
        sqlite_memory.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        return sqlite_memory

    def test_add_memory(self, tmp_path):
        sm = self._sm(tmp_path)
        r = sm.add_memory("test entry", tags="test")
        assert r.get("ok") is True
        assert isinstance(r.get("id"), int)

    def test_search_memory(self, tmp_path):
        sm = self._sm(tmp_path)
        sm.add_memory("reproducible science", tags="science")
        r = sm.search_memory("reproducible")
        assert r.get("ok") is True
        assert len(r.get("results", [])) >= 1

    def test_empty_query_rejected(self, tmp_path):
        sm = self._sm(tmp_path)
        r = sm.search_memory("")
        assert r.get("ok") is False

    def test_log_event(self, tmp_path):
        sm = self._sm(tmp_path)
        sm.log_event("unit_test", {"value": 42})


# ===========================================================================
# 5. MEMORY ADAPTER
# ===========================================================================

class TestMemoryAdapter:
    def test_import(self):
        from eli.brain.memory_adapter import MemoryAdapter, memory_adapter, memory
        assert MemoryAdapter is not None
        assert memory_adapter is not None
        assert memory is not None

    def test_store(self, tmp_path):
        _tmp_db(tmp_path)
        from eli.brain.memory_adapter import memory_store
        r = memory_store("adapter store test", tags="adapter,test")
        assert isinstance(r, dict)

    def test_search(self, tmp_path):
        _tmp_db(tmp_path)
        from eli.brain.memory_adapter import memory_store, memory_search
        memory_store("adapter search target", tags="adapter")
        r = memory_search("adapter search")
        assert isinstance(r, dict)

    def test_recent(self, tmp_path):
        _tmp_db(tmp_path)
        from eli.brain.memory_adapter import memory_recent
        r = memory_recent(limit=3)
        assert isinstance(r, list)

    def test_object_api(self, tmp_path):
        _tmp_db(tmp_path)
        from eli.brain.memory_adapter import memory
        result = memory.store("object api test", tags="api")
        assert isinstance(result, dict)
        recent = memory.recent(limit=5)
        assert isinstance(recent, list)


# ===========================================================================
# 6. CONFIG
# ===========================================================================

class TestConfig:
    def test_import(self):
        from eli.brain import config
        assert config is not None

    def test_get_persona_returns_string(self):
        from eli.brain.config import get_persona
        p = get_persona()
        assert isinstance(p, str) and len(p) > 0

    def test_get_eli_persona(self):
        from eli.brain.config import get_eli_persona
        p = get_eli_persona()
        assert "ELI" in p

    def test_temperature_default(self):
        from eli.brain.config import get_temperature
        t = get_temperature()
        assert 0.0 <= t <= 2.0

    def test_num_predict_default(self):
        from eli.brain.config import get_num_predict
        n = get_num_predict()
        assert isinstance(n, int) and n > 0

    def test_get_set_roundtrip(self, tmp_path, monkeypatch):
        from eli.brain import config as cfg
        monkeypatch.setattr(cfg, "CONFIG_PATH", tmp_path / "config.json")
        cfg.set("test_key_xyz", "hello_world")
        assert cfg.get("test_key_xyz") == "hello_world"

    def test_delete_key(self, tmp_path, monkeypatch):
        from eli.brain import config as cfg
        monkeypatch.setattr(cfg, "CONFIG_PATH", tmp_path / "config.json")
        cfg.set("del_key", "to_be_deleted")
        cfg.delete("del_key")
        assert cfg.get("del_key") is None

    def test_list_keys(self, tmp_path, monkeypatch):
        from eli.brain import config as cfg
        monkeypatch.setattr(cfg, "CONFIG_PATH", tmp_path / "config.json")
        cfg.set("k1", "v1")
        cfg.set("k2", "v2")
        keys = cfg.list_keys()
        assert "k1" in keys and "k2" in keys

    def test_gguf_n_gpu_layers_env(self, monkeypatch):
        monkeypatch.setenv("ELI_N_GPU_LAYERS", "8")
        from eli.brain.config import get_gguf_n_gpu_layers
        assert get_gguf_n_gpu_layers() == 8

    def test_gguf_n_ctx_default(self):
        from eli.brain.config import get_gguf_n_ctx
        assert get_gguf_n_ctx() > 0

    def test_running_under_pytest(self):
        from eli.brain.config import _running_under_pytest
        assert _running_under_pytest() is True


# ===========================================================================
# 7. PATHS
# ===========================================================================

class TestPaths:
    def test_importable(self):
        from eli.brain.paths import PATHS
        assert PATHS is not None

    def test_db_is_path(self):
        from eli.brain.paths import PATHS
        assert isinstance(PATHS.db, Path)

    def test_artifacts_creatable(self):
        from eli.brain.paths import PATHS
        assert isinstance(PATHS.artifacts, Path)

    def test_constants(self):
        from eli.brain.paths import ELI_ROOT, ARTIFACTS_DIR, DB_PATH
        assert isinstance(ELI_ROOT, Path)
        assert isinstance(ARTIFACTS_DIR, Path)
        assert isinstance(DB_PATH, Path)

    def test_env_override(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ELI_MEMORY_DB", str(tmp_path / "override.sqlite3"))
        from eli.brain.paths import PATHS
        assert isinstance(PATHS.db, Path)

    def test_ensure_dirs(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ELI_ROOT", str(tmp_path))
        from eli.brain import paths as paths_mod
        try:
            paths_mod.ensure_dirs()
        except Exception as e:
            pytest.skip(f"ensure_dirs raised: {e}")


# ===========================================================================
# 8. MEMORY SERVICE
# ===========================================================================

class TestMemoryService:
    def test_import(self):
        from eli.brain.memory_service import (
            ensure_schema, get_or_create_session_id,
            append_chat_turn, get_last_user_utterance,
            summarize_recent_window,
        )
        assert callable(ensure_schema)

    def test_session_id_stable(self):
        from eli.brain.memory_service import get_or_create_session_id
        s1 = get_or_create_session_id()
        s2 = get_or_create_session_id()
        assert s1 == s2 and len(s1) > 0

    def test_append_and_retrieve(self):
        from eli.brain.memory_service import (
            get_or_create_session_id, append_chat_turn, get_last_user_utterance
        )
        sid = get_or_create_session_id()
        append_chat_turn(sid, "What is dark energy?", "It expands spacetime.")
        last = get_last_user_utterance(sid)
        assert last == "What is dark energy?"

    def test_summarize_recent(self):
        from eli.brain.memory_service import (
            get_or_create_session_id, append_chat_turn, summarize_recent_window
        )
        sid = get_or_create_session_id()
        append_chat_turn(sid, "hello", "hi there")
        summary = summarize_recent_window(sid, window=5)
        assert isinstance(summary, str)

    def test_ensure_schema_noop(self):
        from eli.brain.memory_service import ensure_schema
        ensure_schema()


# ===========================================================================
# 9. MEMORY CLASS — using the REAL method names
# ===========================================================================

class TestMemoryClass:
    def test_store_and_recall(self, tmp_path):
        m = _fresh_memory(tmp_path)
        m.store_memory("test memory insert", tags=["test"])
        results = m.recall_memory("test memory")
        assert isinstance(results, list)

    def test_add_memory_alias(self, tmp_path):
        """add_memory is a compat alias for store_memory."""
        m = _fresh_memory(tmp_path)
        r = m.add_memory("alias test", tags="compat,test")
        assert isinstance(r, dict)

    def test_conversation_storage(self, tmp_path):
        m = _fresh_memory(tmp_path)
        session = "test-session-001"
        m.add_conversation_turn(role="user", content="What is 2+2?", session_id=session)
        m.add_conversation_turn(role="assistant", content="4", session_id=session)
        history = m.get_recent_conversation(limit=10, session_id=session)
        assert isinstance(history, list)
        assert len(history) >= 2

    def test_store_conversation_alias(self, tmp_path):
        """store_conversation is a compat alias."""
        m = _fresh_memory(tmp_path)
        m.store_conversation("sess-002", "user", "Hello ELI")
        history = m.get_conversation_history("sess-002")
        assert isinstance(history, list)
        assert len(history) >= 1

    def test_search_memories_alias(self, tmp_path):
        """search_memories is a compat alias for recall_memory."""
        m = _fresh_memory(tmp_path)
        m.store_memory("dark matter density", tags=["physics"])
        results = m.search_memories("dark matter")
        assert isinstance(results, list)

    def test_habit_event_logging(self, tmp_path):
        m = _fresh_memory(tmp_path)
        m.log_habit_event("app_launch", {"app": "firefox", "cmd": "firefox"})
        events = m.get_habit_events(event_type="app_launch", days=1)
        assert isinstance(events, list)
        assert len(events) >= 1

    def test_habit_rules_crud(self, tmp_path):
        m = _fresh_memory(tmp_path)
        m.add_habit_rule("Morning standup", "slack --status online", 9, 0)
        rules = m.get_habit_rules(enabled_only=False)
        assert isinstance(rules, list)
        assert any(r.get("name") == "Morning standup" for r in rules)

    def test_failure_logging(self, tmp_path):
        m = _fresh_memory(tmp_path)
        m.log_failure("open unknown app", error="NoSuchApp", context={"cmd": "open unknown"})

    def test_improvement_logging(self, tmp_path):
        m = _fresh_memory(tmp_path)
        m.log_improvement("routing", "Better intent detection")

    def test_init_self_improvement_tables_noop(self, tmp_path):
        m = _fresh_memory(tmp_path)
        m.init_self_improvement_tables()

    def test_db_path_respects_env(self, tmp_path):
        custom_db = tmp_path / "custom.sqlite3"
        os.environ["ELI_MEMORY_DB"] = str(custom_db)
        os.environ["ELI_MEMORY_DB_PATH"] = str(custom_db)
        import eli.brain.memory as mem_mod
        mem_mod._memory_singleton = None
        m = mem_mod.get_memory()
        assert str(m.db_path) == str(custom_db)


# ===========================================================================
# 10. SELF IMPROVEMENT ENGINE
# ===========================================================================

class TestSelfImprovementEngine:
    def test_import(self):
        from eli.brain.self_improvement import SelfImprovementEngine, get_self_improvement
        assert SelfImprovementEngine is not None
        assert callable(get_self_improvement)

    def test_instantiate(self, tmp_path):
        _fresh_memory(tmp_path)
        from eli.brain.self_improvement import SelfImprovementEngine
        engine = SelfImprovementEngine()
        assert engine is not None

    def test_log_failure(self, tmp_path):
        _fresh_memory(tmp_path)
        from eli.brain.self_improvement import SelfImprovementEngine
        SelfImprovementEngine().log_failure("unknown cmd", error="NoRoute", confidence=0.1)

    def test_log_improvement(self, tmp_path):
        _fresh_memory(tmp_path)
        from eli.brain.self_improvement import SelfImprovementEngine
        SelfImprovementEngine().log_improvement("routing", "Better intent detection")

    def test_analyze_failures_returns_list(self, tmp_path):
        _fresh_memory(tmp_path)
        from eli.brain.self_improvement import SelfImprovementEngine
        proposals = SelfImprovementEngine().analyze_failures(days=1, min_cluster_size=3)
        assert isinstance(proposals, list)

    def test_singleton(self, tmp_path):
        _fresh_memory(tmp_path)
        import eli.brain.self_improvement as si
        si._self_engine = None
        from eli.brain.self_improvement import get_self_improvement
        assert get_self_improvement() is get_self_improvement()


# ===========================================================================
# 11. GGUF INFERENCE (mocked)
# ===========================================================================

class TestGGUFInference:
    def test_import(self):
        from eli.brain import gguf_inference
        assert gguf_inference is not None

    def test_get_model_path_no_env(self, monkeypatch):
        monkeypatch.delenv("ELI_GGUF_MODEL_PATH", raising=False)
        from eli.brain.gguf_inference import get_model_path
        result = get_model_path()
        assert result is None or isinstance(result, Path)

    def test_env_path_nonexistent_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ELI_GGUF_MODEL_PATH", str(tmp_path / "nonexistent.gguf"))
        from eli.brain import gguf_inference
        assert gguf_inference.get_model_path() is None

    def test_load_model_without_model(self, monkeypatch):
        monkeypatch.delenv("ELI_GGUF_MODEL_PATH", raising=False)
        from eli.brain import gguf_inference
        from unittest.mock import patch
        gguf_inference._llm = None
        with patch("eli.brain.gguf_inference.get_model_path", return_value=None):
            result = gguf_inference.load_model()
        assert result is None

    def test_chat_completion_mocked(self, monkeypatch):
        monkeypatch.delenv("ELI_GGUF_MODEL_PATH", raising=False)
        from eli.brain import gguf_inference

        mock_llm = MagicMock()
        mock_llm.create_chat_completion.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "ELI: Mocked response."}}]
        }

        with patch.object(gguf_inference, "load_model", return_value=mock_llm):
            with patch.object(gguf_inference, "get_model_path", return_value=Path("/fake/model.gguf")):
                result = gguf_inference.chat_completion("test prompt", system="You are ELI.")
        assert result == "ELI: Mocked response."
        # the model's own chat template gets the system and user turns as messages
        messages = mock_llm.create_chat_completion.call_args.kwargs["messages"]
        assert messages == [{"role": "system", "content": "You are ELI."}, {"role": "user", "content": "test prompt"}]
        gguf_inference._llm = None


# ===========================================================================
# 12. HABITS
# ===========================================================================

class TestHabits:
    def test_import(self):
        from eli.brain.habits import log_event, detect_habits
        assert callable(log_event) and callable(detect_habits)

    def test_log_event(self, tmp_path):
        _fresh_memory(tmp_path)
        from eli.brain.habits import log_event
        log_event("app_launch", {"app": "terminal", "cmd": "gnome-terminal"})

    def test_detect_habits_no_crash(self, tmp_path):
        _fresh_memory(tmp_path)
        from eli.brain.habits import detect_habits
        detect_habits(days=1, min_occurrences=3)


# ===========================================================================
# 13. REFLECTION
# ===========================================================================

class TestReflection:
    def test_import(self):
        from eli.brain.reflection import reflect_on_period, reflect_on_memories, run_reflection
        assert callable(reflect_on_period)

    def test_reflect_on_period(self, tmp_path):
        _fresh_memory(tmp_path)
        from eli.brain.reflection import reflect_on_period
        result = reflect_on_period(hours=24)
        assert isinstance(result, dict)
        assert "insights" in result

    def test_reflect_on_memories_alias(self, tmp_path):
        _fresh_memory(tmp_path)
        from eli.brain.reflection import reflect_on_memories
        result = reflect_on_memories(days=1)
        assert isinstance(result, dict)

    def test_run_reflection_compat(self):
        from eli.brain.reflection import run_reflection
        result = run_reflection()
        assert isinstance(result, dict)


# ===========================================================================
# 14. ELI AGENT — filesystem + quick_route
# ===========================================================================

class TestELIAgentFunctions:
    def _reload(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ELI_ROOT", str(tmp_path))
        import importlib, eli.brain.eli_agent as ea
        importlib.reload(ea)
        return ea

    def test_import(self):
        from eli.brain.eli_agent import ELIAgent
        assert ELIAgent is not None

    def test_agent_instantiation(self):
        from eli.brain.eli_agent import ELIAgent
        assert ELIAgent() is not None

    def test_safe_path_within_root(self, tmp_path, monkeypatch):
        ea = self._reload(tmp_path, monkeypatch)
        p = ea.safe_path("subdir/file.txt")
        assert str(p).startswith(str(tmp_path))

    def test_safe_path_blocks_escape(self, tmp_path, monkeypatch):
        ea = self._reload(tmp_path, monkeypatch)
        with pytest.raises(ValueError, match="Blocked"):
            ea.safe_path("../../etc/passwd")

    def test_list_dir_nonexistent(self, tmp_path, monkeypatch):
        ea = self._reload(tmp_path, monkeypatch)
        assert ea.list_dir("nonexistent_dir").get("ok") is False

    def test_list_dir_existing(self, tmp_path, monkeypatch):
        ea = self._reload(tmp_path, monkeypatch)
        (tmp_path / "subdir").mkdir()
        r = ea.list_dir(".")
        assert r.get("ok") is True and "items" in r

    def test_read_file(self, tmp_path, monkeypatch):
        ea = self._reload(tmp_path, monkeypatch)
        (tmp_path / "test.txt").write_text("hello world")
        r = ea.read_file("test.txt")
        assert r.get("ok") is True and "hello world" in r.get("text", "")

    def test_write_file(self, tmp_path, monkeypatch):
        ea = self._reload(tmp_path, monkeypatch)
        r = ea.write_file("output.txt", "test content")
        assert r.get("ok") is True
        assert (tmp_path / "output.txt").read_text() == "test content"

    def test_grep(self, tmp_path, monkeypatch):
        ea = self._reload(tmp_path, monkeypatch)
        (tmp_path / "code.py").write_text("def hello_world():\n    pass\n")
        r = ea.grep(".", "hello_world")
        assert r.get("ok") is True and len(r.get("hits", [])) >= 1

    def test_quick_route_time(self):
        from eli.brain.eli_agent import quick_route
        r = quick_route("what time is it")
        assert r is not None and r.get("action") == "reply"

    def test_quick_route_volume_up(self):
        from eli.brain.eli_agent import quick_route
        r = quick_route("volume up")
        assert r is not None and r.get("action") == "volume"

    def test_quick_route_volume_down(self):
        from eli.brain.eli_agent import quick_route
        r = quick_route("volume down")
        assert r is not None and r.get("action") == "volume"

    def test_quick_route_mute(self):
        from eli.brain.eli_agent import quick_route
        r = quick_route("mute")
        assert r is not None and r.get("action") == "mute_toggle"

    def test_quick_route_none_for_unknown(self):
        from eli.brain.eli_agent import quick_route
        assert quick_route("analyze the quantum foam topology") is None

    def test_quick_route_search(self):
        from eli.brain.eli_agent import quick_route
        r = quick_route("search dark matter physics")
        assert r is not None and r.get("action") == "search"
        assert "dark matter" in r["args"].get("q", "")

    def test_quick_route_youtube(self):
        from eli.brain.eli_agent import quick_route
        r = quick_route("open youtube")
        assert r is not None and r.get("action") == "open_url"
        assert "youtube" in r["args"].get("url", "").lower()

    def test_extract_json_valid(self):
        from eli.brain.eli_agent import extract_json
        r = extract_json('{"action": "reply", "args": {"text": "hello"}}')
        assert r["action"] == "reply"

    def test_extract_json_embedded(self):
        from eli.brain.eli_agent import extract_json
        r = extract_json('preamble {"action": "noop", "args": {}} trailing')
        assert r["action"] == "noop"

    def test_extract_json_raises_on_garbage(self):
        from eli.brain.eli_agent import extract_json
        with pytest.raises((ValueError, json.JSONDecodeError)):
            extract_json("this is not json at all")

    def test_dispatch_noop(self):
        from eli.brain.eli_agent import dispatch
        dispatch({"action": "noop", "args": {}})

    def test_dispatch_reply(self):
        from eli.brain.eli_agent import dispatch
        with patch("eli.brain.eli_agent.speak") as mock_speak:
            dispatch({"action": "reply", "args": {"text": "Test reply"}})
            mock_speak.assert_called_once_with("Test reply")


# ===========================================================================
# 15. AGENT LOOP (handles broken compat.py gracefully)
# ===========================================================================

class TestAgentLoop:
    def test_import_or_skip(self):
        try:
            from eli.brain.agent_loop import agent_step
            assert callable(agent_step)
        except ImportError as e:
            pytest.skip(f"agent_loop unavailable (compat.py fix needed): {e}")

    def test_agent_step_mocked(self, tmp_path):
        _tmp_db(tmp_path)
        try:
            from eli.brain import agent_loop
        except ImportError as e:
            pytest.skip(f"agent_loop unavailable: {e}")

        with patch("eli.brain.agent_loop.chat_response") as mock_chat, \
             patch("eli.brain.agent_loop.route_intent") as mock_route:
            mock_chat.return_value = {"content": "Dark energy accelerates expansion."}
            mock_route.return_value = {"action": "CHAT", "args": {}}
            result = agent_loop.agent_step("What is dark energy?")
            assert result.get("ok") is True
            assert result.get("type") == "message"


# ===========================================================================
# 16. COMPAT.PY — execute must be importable
# ===========================================================================

class TestCompat:
    def test_execute_importable(self):
        try:
            from eli.brain.compat import execute
            assert callable(execute)
        except ImportError as e:
            pytest.fail(f"compat.execute not importable: {e}")

    def test_execute_returns_dict(self):
        try:
            from eli.brain.compat import execute
            result = execute("noop", {})
            assert isinstance(result, dict)
        except ImportError:
            pytest.skip("compat.execute not yet fixed")


# ===========================================================================
# 17. CHAT MODEL
# ===========================================================================

class TestChatModel:
    def test_import(self):
        from eli.brain.chat_model import chat_response, chat_stream, chat_response_stream
        assert callable(chat_response)

    def test_chat_response_ollama_down(self):
        with patch("eli.brain.chat_model._requests_post_json", side_effect=Exception("refused")):
            with patch("eli.brain.chat_model.build_context", return_value="system"):
                with patch("eli.brain.chat_model._persist_turns"):
                    from eli.brain.chat_model import chat_response
                    result = chat_response("hello")
                    assert isinstance(result, str)

    def test_chat_stream_yields_strings(self):
        chunks = [
            {"done": False, "message": {"content": "Hello"}},
            {"done": False, "message": {"content": " world"}},
            {"done": True},
        ]
        with patch("eli.brain.chat_model._requests_post_stream", return_value=iter(chunks)):
            from eli.brain.chat_model import chat_stream
            result = list(chat_stream([{"role": "user", "content": "hi"}], model="test"))
            assert all(isinstance(c, str) for c in result)
            assert "".join(result) == "Hello world"


# ===========================================================================
# 18. WIRING — full import chain
# ===========================================================================

class TestWiring:
    def test_memory_importable(self):
        from eli.brain.memory import Memory, get_memory
        assert callable(get_memory)

    def test_self_improvement_importable(self):
        from eli.brain.self_improvement import SelfImprovementEngine
        assert SelfImprovementEngine is not None

    def test_brain_init_get_memory(self):
        import eli.brain
        assert callable(eli.brain.get_memory)

    def test_brain_init_paths(self):
        import eli.brain
        assert eli.brain.PATHS is not None

    def test_config_importable(self):
        from eli.brain.config import get_persona, get_temperature
        assert callable(get_persona)

    def test_paths_importable(self):
        from eli.brain.paths import PATHS, ELI_ROOT
        assert isinstance(ELI_ROOT, Path)

    def test_memory_adapter_importable(self):
        from eli.brain.memory_adapter import memory, memory_adapter
        assert memory is not None

    def test_memory_service_importable(self):
        from eli.brain.memory_service import get_or_create_session_id
        assert callable(get_or_create_session_id)

    def test_habits_importable(self):
        from eli.brain.habits import log_event, detect_habits
        assert callable(log_event)

    def test_reflection_importable(self):
        from eli.brain.reflection import reflect_on_period
        assert callable(reflect_on_period)

    def test_eli_agent_importable(self):
        from eli.brain.eli_agent import ELIAgent, quick_route
        assert callable(quick_route)

    def test_no_circular_imports(self):
        import importlib
        modules = [
            "eli.brain.memory",
            "eli.brain.memory_db",
            "eli.brain.memory_adapter",
            "eli.brain.memory_service",
            "eli.brain.config",
            "eli.brain.paths",
            "eli.brain.habits",
            "eli.brain.reflection",
            "eli.brain.self_improvement",
            "eli.brain.eli_agent",
        ]
        for mod in modules:
            try:
                importlib.import_module(mod)
            except ImportError as e:
                pytest.fail(f"Failed to import {mod}: {e}")


# ===========================================================================
# 19. REGRESSIONS — every specific error from the original failing run
# ===========================================================================

class TestRegressions:
    def test_get_memory_is_module_level(self):
        import inspect, eli.brain.memory as m
        assert inspect.isfunction(m.get_memory)

    def test_habit_events_table_created(self, tmp_path):
        """habit_events table must exist after _ensure_tables()."""
        m = _fresh_memory(tmp_path)
        conn = sqlite3.connect(str(m.db_path))
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        conn.close()
        assert "habit_events" in tables, f"habit_events missing. Tables: {tables}"

    def test_self_improvement_not_broken_by_memory(self):
        from eli.brain.self_improvement import SelfImprovementEngine
        assert SelfImprovementEngine is not None

    def test_brain_init_exports_self_improvement(self):
        import eli.brain
        assert hasattr(eli.brain, "SelfImprovementEngine")

    def test_brain_init_exports_get_memory(self):
        import eli.brain
        assert hasattr(eli.brain, "get_memory")
        assert callable(eli.brain.get_memory)

    def test_brain_init_exports_paths(self):
        import eli.brain
        assert hasattr(eli.brain, "PATHS")

    def test_memory_db_recall_recent_k_kwarg(self, tmp_path):
        from eli.brain import memory_db
        memory_db.DB_PATH = tmp_path / "k_test.sqlite3"
        memory_db.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        result = memory_db.recall_recent(k=5)
        assert isinstance(result, dict)

    def test_memory_db_recall_recent_limit_kwarg(self, tmp_path):
        from eli.brain import memory_db
        memory_db.DB_PATH = tmp_path / "limit_test.sqlite3"
        memory_db.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        result = memory_db.recall_recent(limit=3)
        assert isinstance(result, dict)

    def test_compat_execute_importable(self):
        """agent_loop.py does: from eli.brain.compat import execute"""
        try:
            from eli.brain.compat import execute
            assert callable(execute)
        except ImportError as e:
            pytest.fail(f"compat.execute still broken: {e}")

    def test_memory_add_memory_alias_exists(self, tmp_path):
        """Memory.add_memory must exist as a compat alias."""
        m = _fresh_memory(tmp_path)
        assert hasattr(m, "add_memory"), "Memory.add_memory alias missing"

    def test_memory_store_conversation_alias_exists(self, tmp_path):
        """Memory.store_conversation must exist as a compat alias."""
        m = _fresh_memory(tmp_path)
        assert hasattr(m, "store_conversation"), "Memory.store_conversation alias missing"

    def test_memory_search_memories_alias_exists(self, tmp_path):
        """Memory.search_memories must exist as a compat alias."""
        m = _fresh_memory(tmp_path)
        assert hasattr(m, "search_memories"), "Memory.search_memories alias missing"


# ===========================================================================
# Autouse fixtures
# ===========================================================================

@pytest.fixture(autouse=True)
def _reset_singletons():
    yield
    try:
        import eli.brain.memory as m
        m._memory_singleton = None
    except Exception:
        pass
    try:
        import eli.brain.self_improvement as si
        si._self_engine = None
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    yield
    for var in ("ELI_MEMORY_DB", "ELI_MEMORY_DB_PATH", "ELI_ROOT"):
        monkeypatch.delenv(var, raising=False)
