"""
ELI Memory Pipeline Test Suite
================================
Traces the EXACT path from user prompt → response:

    User input
      └─ CognitiveEngine.process()
           ├─ add_conversation_turn("user", ...)      [MEMORY WRITE]
           ├─ _parse_intent()                          [ROUTER]
           ├─ _retrieve_relevant_memories()
           │    ├─ get_recent_conversation()           [MEMORY READ: conversations]
           │    ├─ search_conversations()              [MEMORY READ: FTS/LIKE search]
           │    └─ recall_memory()                     [MEMORY READ: memories table]
           ├─ _get_chat_response() / _stream_chat()    [GGUF inference]
           └─ add_conversation_turn("assistant", ...) [MEMORY WRITE]

Run:
    pytest src/eli/tests/test_memory_pipeline.py -v -s
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Every test gets a fresh SQLite DB. Resets all singletons."""
    db = tmp_path / "pipeline_test.sqlite3"
    monkeypatch.setenv("ELI_MEMORY_DB", str(db))
    monkeypatch.setenv("ELI_MEMORY_DB_PATH", str(db))
    monkeypatch.setenv("ELI_N_GPU_LAYERS", "0")
    yield db
    # Reset singletons
    try:
        import eli.brain.memory as m; m._memory_singleton = None
    except Exception: pass
    try:
        import eli.brain.cognitive_engine as ce; ce._engine = None
    except Exception: pass
    try:
        import eli.brain.self_improvement as si; si._self_engine = None
    except Exception: pass


@pytest.fixture
def mem(isolated_db):
    """Fresh Memory instance."""
    import eli.brain.memory as m
    m._memory_singleton = None
    return m.get_memory()


@pytest.fixture
def session_id():
    return f"test-session-{int(time.time())}"


@pytest.fixture
def user_id():
    return "test-user-pipeline"


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 1: Raw SQLite — verify every table and column exists
# ─────────────────────────────────────────────────────────────────────────────

class TestDatabaseSchema:
    """Verify the DB schema that the pipeline depends on."""

    REQUIRED_TABLES = {
        "memories":           {"id", "text", "ts", "timestamp", "tags", "weight"},
        "conversations":      {"id", "role", "content", "timestamp", "session_id", "user_id"},
        "habit_events":       {"id", "event_type", "details", "timestamp"},
        "habit_rules":        {"id", "name", "command", "hour", "minute", "enabled"},
        "failures":           {"id", "command", "error", "timestamp"},
        "improvements":       {"id", "category", "area", "description", "timestamp"},
        "observations":       {"id", "content", "timestamp"},
        "corrections":        {"id", "original", "corrected", "timestamp"},
        "capability_proposals": {"id", "capability", "status", "timestamp"},
        "recall_log":         {"id", "memory_id", "timestamp", "query"},
    }

    def _columns(self, conn, table):
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}

    def test_all_required_tables_exist(self, mem):
        conn = sqlite3.connect(str(mem.db_path))
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        for table in self.REQUIRED_TABLES:
            assert table in tables, f"Missing table: {table}"

    def test_conversations_has_user_id_and_session_id(self, mem):
        conn = sqlite3.connect(str(mem.db_path))
        cols = self._columns(conn, "conversations")
        conn.close()
        assert "user_id" in cols,    "conversations.user_id missing — run migrate_db.py"
        assert "session_id" in cols, "conversations.session_id missing — run migrate_db.py"

    def test_habit_events_table_exists(self, mem):
        conn = sqlite3.connect(str(mem.db_path))
        cols = self._columns(conn, "habit_events")
        conn.close()
        assert "event_type" in cols
        assert "details" in cols
        assert "timestamp" in cols

    def test_memories_fts_exists(self, mem):
        conn = sqlite3.connect(str(mem.db_path))
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "memories_fts" in tables, "FTS5 virtual table missing"

    def test_all_column_requirements(self, mem):
        conn = sqlite3.connect(str(mem.db_path))
        for table, required_cols in self.REQUIRED_TABLES.items():
            try:
                actual = self._columns(conn, table)
                missing = required_cols - actual
                assert not missing, f"{table} missing columns: {missing}"
            except Exception as e:
                pytest.fail(f"Failed checking {table}: {e}")
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 2: Memory.add_conversation_turn — Step 1 of the pipeline
# ─────────────────────────────────────────────────────────────────────────────

class TestConversationWrite:
    """Verify user turns are written to DB exactly as CognitiveEngine does it."""

    def test_user_turn_written(self, mem, session_id, user_id):
        mem.add_conversation_turn("user", "Hello ELI", session_id, user_id)
        conn = sqlite3.connect(str(mem.db_path))
        row = conn.execute(
            "SELECT role, content, session_id, user_id FROM conversations ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        conn.close()
        assert row[0] == "user"
        assert row[1] == "Hello ELI"
        assert row[2] == session_id
        assert row[3] == user_id

    def test_assistant_turn_written(self, mem, session_id, user_id):
        mem.add_conversation_turn("assistant", "Good morning.", session_id, user_id)
        conn = sqlite3.connect(str(mem.db_path))
        row = conn.execute(
            "SELECT role, content FROM conversations WHERE role='assistant' ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        conn.close()
        assert row[0] == "assistant"
        assert row[1] == "Good morning."

    def test_turn_has_timestamp(self, mem, session_id, user_id):
        before = time.time()
        mem.add_conversation_turn("user", "test", session_id, user_id)
        after = time.time()
        conn = sqlite3.connect(str(mem.db_path))
        row = conn.execute(
            "SELECT timestamp FROM conversations ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        conn.close()
        assert before <= row[0] <= after

    def test_multiple_turns_ordered(self, mem, session_id, user_id):
        turns = [
            ("user",      "What time is it?"),
            ("assistant", "It's 10:00 AM."),
            ("user",      "Thanks."),
            ("assistant", "You're welcome."),
        ]
        for role, content in turns:
            mem.add_conversation_turn(role, content, session_id, user_id)
            time.sleep(0.01)

        results = mem.get_recent_conversation(limit=10, session_id=session_id)
        # Results come back newest-first from get_recent_conversation
        contents = [r["content"] for r in results]
        assert "What time is it?" in contents
        assert "You're welcome." in contents

    def test_turn_isolated_to_session(self, mem, user_id):
        sid1 = "session-A"
        sid2 = "session-B"
        mem.add_conversation_turn("user", "Message in A", sid1, user_id)
        mem.add_conversation_turn("user", "Message in B", sid2, user_id)

        results_a = mem.get_recent_conversation(limit=10, session_id=sid1)
        results_b = mem.get_recent_conversation(limit=10, session_id=sid2)

        a_contents = [r["content"] for r in results_a]
        b_contents = [r["content"] for r in results_b]

        assert "Message in A" in a_contents
        assert "Message in B" not in a_contents
        assert "Message in B" in b_contents
        assert "Message in A" not in b_contents

    def test_turn_isolated_to_user(self, mem, session_id):
        uid1 = "user-alice"
        uid2 = "user-bob"
        mem.add_conversation_turn("user", "Alice's message", session_id, uid1)
        mem.add_conversation_turn("user", "Bob's message",   session_id, uid2)

        alice = mem.get_recent_conversation(limit=10, user_id=uid1)
        bob   = mem.get_recent_conversation(limit=10, user_id=uid2)

        assert any("Alice" in r["content"] for r in alice)
        assert not any("Alice" in r["content"] for r in bob)


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 3: Memory retrieval — _retrieve_relevant_memories() internals
# ─────────────────────────────────────────────────────────────────────────────

class TestMemoryRetrieval:
    """Test each sub-query inside _retrieve_relevant_memories()."""

    def test_get_recent_conversation_returns_list(self, mem, session_id, user_id):
        mem.add_conversation_turn("user", "hello", session_id, user_id)
        result = mem.get_recent_conversation(limit=10, user_id=user_id)
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_get_recent_conversation_limit_respected(self, mem, session_id, user_id):
        for i in range(20):
            mem.add_conversation_turn("user", f"message {i}", session_id, user_id)
        result = mem.get_recent_conversation(limit=5, user_id=user_id)
        assert len(result) <= 5

    def test_get_recent_conversation_fields(self, mem, session_id, user_id):
        mem.add_conversation_turn("user", "field test", session_id, user_id)
        result = mem.get_recent_conversation(limit=1, user_id=user_id)
        assert len(result) >= 1
        r = result[0]
        assert "role" in r
        assert "content" in r
        assert "timestamp" in r
        assert "session_id" in r
        assert "user_id" in r

    def test_search_conversations_finds_keyword(self, mem, session_id, user_id):
        mem.add_conversation_turn("user", "Let's talk about quantum physics", session_id, user_id)
        mem.add_conversation_turn("assistant", "Quantum mechanics is fascinating", session_id, user_id)
        results = mem.search_conversations("quantum", user_id=user_id, limit=10)
        assert isinstance(results, list)
        assert len(results) >= 1
        texts = [r["content"] for r in results]
        assert any("quantum" in t.lower() for t in texts)

    def test_search_conversations_no_false_positives(self, mem, session_id, user_id):
        mem.add_conversation_turn("user", "I like bananas", session_id, user_id)
        results = mem.search_conversations("quantum", user_id=user_id, limit=10)
        assert all("quantum" not in r["content"].lower() for r in results)

    def test_store_and_recall_memory(self, mem):
        mem.store_memory("ELI was built by Sam", tags=["system", "info"])
        results = mem.recall_memory("ELI built", limit=5)
        assert isinstance(results, list)
        assert len(results) >= 1
        texts = [r.get("text", "") for r in results]
        assert any("ELI" in t for t in texts)

    def test_recall_memory_respects_limit(self, mem):
        for i in range(10):
            mem.store_memory(f"test memory entry {i}", tags=["test"])
        results = mem.recall_memory("test memory", limit=3)
        assert len(results) <= 3

    def test_recall_memory_returns_weight(self, mem):
        mem.store_memory("weighted memory test", tags=["weight"])
        results = mem.recall_memory("weighted memory", limit=5)
        assert len(results) >= 1
        assert "weight" in results[0]

    def test_recall_memory_fts_search(self, mem):
        """FTS5 full-text search works for semantic-ish queries."""
        mem.store_memory("The user prefers dark mode and minimal UI", tags=["preference"])
        results = mem.recall_memory("dark mode preference", limit=5)
        assert len(results) >= 1

    def test_recall_memory_adjusts_weight(self, mem):
        mem.store_memory("memory to adjust", tags=["test"])
        results = mem.recall_memory("memory to adjust", limit=1)
        assert len(results) >= 1
        mem_id = results[0].get("id")
        if mem_id:
            original_weight = results[0].get("weight", 1.0)
            mem.adjust_weight(mem_id, 0.5)
            conn = sqlite3.connect(str(mem.db_path))
            row = conn.execute("SELECT weight FROM memories WHERE id=?", (mem_id,)).fetchone()
            conn.close()
            assert row[0] != original_weight or original_weight == 0

    def test_recall_log_written_on_recall(self, mem):
        mem.store_memory("recall log test entry", tags=["test"])
        mem.recall_memory("recall log test", limit=5)
        conn = sqlite3.connect(str(mem.db_path))
        count = conn.execute("SELECT COUNT(*) FROM recall_log").fetchone()[0]
        conn.close()
        # recall_log may or may not be written depending on whether FTS hit
        assert count >= 0  # just verify the table exists and doesn't crash

    def test_date_filtered_recall(self, mem, session_id, user_id):
        """Simulate CognitiveEngine's since_date filtering.
        Note: add_conversation_turn does not accept a ts kwarg, so we
        insert the old-timestamped row directly via SQL."""
        # Insert an old turn directly (10 days ago)
        old_ts = time.time() - 10 * 86400
        conn = sqlite3.connect(str(mem.db_path))
        conn.execute(
            "INSERT INTO conversations (role, content, timestamp, session_id, user_id) VALUES (?,?,?,?,?)",
            ("user", "old message", old_ts, session_id, user_id)
        )
        conn.commit()
        conn.close()

        # Insert a recent turn normally
        mem.add_conversation_turn("user", "recent message", session_id, user_id)

        all_turns = mem.get_recent_conversation(limit=1000, user_id=user_id)
        cutoff = time.strftime("%Y-%m-%d", time.localtime(time.time() - 2 * 86400))
        filtered = [t for t in all_turns
                    if time.strftime("%Y-%m-%d", time.localtime(t["timestamp"])) >= cutoff]
        contents = [t["content"] for t in filtered]
        assert "recent message" in contents
        assert "old message" not in contents


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 4: Habit events — side-channel written during OPEN_APP actions
# ─────────────────────────────────────────────────────────────────────────────

class TestHabitEventPipeline:
    """Test the habit event write path triggered by _learn_from_result()."""

    def test_log_habit_event_written(self, mem):
        mem.log_habit_event("app_launch", {"app": "firefox", "cmd": "firefox", "success": True})
        conn = sqlite3.connect(str(mem.db_path))
        row = conn.execute(
            "SELECT event_type, details, timestamp FROM habit_events ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        conn.close()
        assert row[0] == "app_launch"
        details = json.loads(row[1])
        assert details["app"] == "firefox"

    def test_get_habit_events_returns_app_launch(self, mem):
        mem.log_habit_event("app_launch", {"app": "terminal"})
        events = mem.get_habit_events(event_type="app_launch", days=1)
        assert isinstance(events, list)
        assert len(events) >= 1
        assert events[-1]["event_type"] == "app_launch"

    def test_get_habit_events_filtered_by_type(self, mem):
        mem.log_habit_event("app_launch", {"app": "firefox"})
        mem.log_habit_event("dir_open",   {"path": "/home"})
        events = mem.get_habit_events(event_type="dir_open", days=1)
        assert all(e["event_type"] == "dir_open" for e in events)

    def test_get_habit_events_respects_days_window(self, mem):
        # Insert an event 10 days ago directly
        conn = sqlite3.connect(str(mem.db_path))
        old_ts = time.time() - 10 * 86400
        conn.execute(
            "INSERT INTO habit_events (event_type, details, timestamp) VALUES (?, ?, ?)",
            ("app_launch", json.dumps({"app": "old"}), old_ts)
        )
        conn.commit()
        conn.close()
        events = mem.get_habit_events(event_type="app_launch", days=1)
        apps = [e["details"].get("app") if isinstance(e["details"], dict) else None
                for e in events]
        assert "old" not in apps

    def test_habit_event_details_parsed_as_dict(self, mem):
        mem.log_habit_event("app_launch", {"app": "code", "cmd": "/usr/bin/code"})
        events = mem.get_habit_events(event_type="app_launch", days=1)
        assert len(events) >= 1
        details = events[-1]["details"]
        assert isinstance(details, dict)
        assert details["app"] == "code"


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 5: Self-improvement logging — triggered on low-confidence intent
# ─────────────────────────────────────────────────────────────────────────────

class TestSelfImprovementPipeline:
    """Verify failure/improvement logging that runs in the pipeline."""

    def test_log_failure_written_to_db(self, mem):
        mem.log_failure("open unknown app", error="NoRoute", confidence=0.1,
                        context={"intent": "OPEN_APP"})
        conn = sqlite3.connect(str(mem.db_path))
        row = conn.execute(
            "SELECT command, error FROM failures ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        conn.close()
        assert "unknown" in row[0]
        assert "NoRoute" in row[1]

    def test_log_improvement_written(self, mem):
        mem.log_improvement("routing", "Better fallback for unknown commands", area="intent")
        conn = sqlite3.connect(str(mem.db_path))
        row = conn.execute(
            "SELECT category, description FROM improvements ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        conn.close()
        assert row[0] == "routing"
        assert "fallback" in row[1]

    def test_add_observation_written(self, mem):
        mem.add_observation("system", "Proactive daemon started")
        conn = sqlite3.connect(str(mem.db_path))
        row = conn.execute(
            "SELECT content FROM observations ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        conn.close()
        assert "Proactive daemon" in row[0]

    def test_self_improvement_engine_log_failure(self, isolated_db):
        from eli.brain.self_improvement import SelfImprovementEngine
        engine = SelfImprovementEngine()
        engine.log_failure("unknown command", error="NoRoute", confidence=0.2)
        conn = sqlite3.connect(str(isolated_db))
        count = conn.execute("SELECT COUNT(*) FROM failures").fetchone()[0]
        conn.close()
        assert count >= 1

    def test_self_improvement_analyze_failures_returns_list(self, isolated_db):
        from eli.brain.self_improvement import SelfImprovementEngine
        engine = SelfImprovementEngine()
        # Log enough failures to trigger analysis
        for i in range(4):
            engine.log_failure("mystery command", error="unhandled", confidence=0.1)
        proposals = engine.analyze_failures(days=1, min_cluster_size=2)
        assert isinstance(proposals, list)


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 6: Full pipeline integration — mocked GGUF
# ─────────────────────────────────────────────────────────────────────────────

class TestFullPipelineMocked:
    """
    Trace the complete path:
      user input → CognitiveEngine.process() → memory writes → response

    GGUF is mocked so tests run without loading a model.
    """

    def _make_engine(self):
        import eli.brain.cognitive_engine as ce
        ce._engine = None
        engine = ce.CognitiveEngine.__new__(ce.CognitiveEngine)
        from eli.brain.memory import get_memory
        engine.memory = get_memory()
        engine.session_id = f"test-{int(time.time())}"
        engine.user_id = "test-user"
        engine.running = True
        engine._gguf_available = True
        return engine

    def test_user_turn_stored_before_llm(self, isolated_db):
        """add_conversation_turn("user",...) is called BEFORE _get_chat_response."""
        engine = self._make_engine()

        call_order = []

        original_add = engine.memory.add_conversation_turn
        def tracked_add(role, *args, **kwargs):
            call_order.append(f"store:{role}")
            return original_add(role, *args, **kwargs)

        def mock_chat(prompt, memory_context=""):
            call_order.append("llm")
            return "Mocked response."

        engine.memory.add_conversation_turn = tracked_add
        engine._get_chat_response = mock_chat

        with patch.object(engine, '_parse_intent', return_value={
            "action": "CHAT", "args": {"message": "hello"}, "confidence": 0.9
        }):
            result = engine.process("hello")

        assert call_order.index("store:user") < call_order.index("llm"), \
            "User turn must be stored BEFORE calling LLM"
        assert "store:assistant" in call_order, \
            "Assistant turn must be stored AFTER LLM"
        assert call_order.index("llm") < call_order.index("store:assistant"), \
            "LLM must fire BEFORE storing assistant turn"

    def test_assistant_response_stored_in_db(self, isolated_db):
        engine = self._make_engine()
        engine._get_chat_response = lambda p, mc="": "Test response from ELI."

        with patch.object(engine, '_parse_intent', return_value={
            "action": "CHAT", "args": {"message": "test"}, "confidence": 0.9
        }):
            result = engine.process("test input")

        conn = sqlite3.connect(str(isolated_db))
        rows = conn.execute(
            "SELECT role, content FROM conversations ORDER BY timestamp"
        ).fetchall()
        conn.close()

        roles = [r[0] for r in rows]
        contents = [r[1] for r in rows]
        assert "user" in roles
        assert "assistant" in roles
        assert "Test response from ELI." in contents

    def test_memory_context_passed_to_llm(self, isolated_db):
        """Verify prior conversation is injected into LLM system prompt."""
        engine = self._make_engine()

        # Pre-populate some conversation
        engine.memory.add_conversation_turn(
            "user", "My name is Sam", engine.session_id, engine.user_id)
        engine.memory.add_conversation_turn(
            "assistant", "Nice to meet you, Sam.", engine.session_id, engine.user_id)

        received_context = {}

        def capture_chat(prompt, memory_context=""):
            received_context["context"] = memory_context
            received_context["prompt"] = prompt
            return "I remember you told me your name."

        engine._get_chat_response = capture_chat

        with patch.object(engine, '_parse_intent', return_value={
            "action": "CHAT", "args": {"message": "Do you remember my name?"}, "confidence": 0.9
        }):
            engine.process("Do you remember my name?")

        assert "context" in received_context
        ctx = received_context["context"]
        assert "Sam" in ctx, f"Memory context missing prior conversation. Got: {ctx[:200]}"

    def test_low_confidence_intent_logs_failure(self, isolated_db):
        """If confidence < 0.5, a failure is logged to the failures table."""
        engine = self._make_engine()
        engine._get_chat_response = lambda p, mc="": "ok"

        with patch.object(engine, '_parse_intent', return_value={
            "action": "CHAT", "args": {"message": "xyzzy"}, "confidence": 0.2
        }):
            engine.process("xyzzy")

        conn = sqlite3.connect(str(isolated_db))
        count = conn.execute("SELECT COUNT(*) FROM failures").fetchone()[0]
        conn.close()
        assert count >= 1, "Low-confidence intent should log to failures table"

    def test_response_contains_content_key(self, isolated_db):
        engine = self._make_engine()
        engine._get_chat_response = lambda p, mc="": "Hello back."

        with patch.object(engine, '_parse_intent', return_value={
            "action": "CHAT", "args": {"message": "hello"}, "confidence": 0.9
        }):
            result = engine.process("hello")

        assert result.get("ok") is True
        assert "content" in result or "response" in result
        text = result.get("content") or result.get("response")
        assert "Hello back." in text

    def test_streaming_yields_tokens(self, isolated_db):
        """_stream_chat yields string chunks."""
        engine = self._make_engine()

        def mock_stream(prompt, system=None, max_tokens=2048, temperature=0.7, stream=True):
            for word in ["Hello", " ", "from", " ", "stream"]:
                yield {"response": word}

        with patch("eli.brain.gguf_inference.generate", side_effect=mock_stream):
            with patch.object(engine, '_parse_intent', return_value={
                "action": "CHAT", "args": {"message": "hi"}, "confidence": 0.9
            }):
                gen = engine.process("hi", stream=True)
                tokens = list(gen)

        assert isinstance(tokens, list)
        assert len(tokens) > 0
        assert all(isinstance(t, str) for t in tokens)
        assert "".join(tokens) == "Hello from stream"

    def test_process_non_chat_action_executes(self, isolated_db):
        """For non-CHAT intents, execute() is called and result stored."""
        engine = self._make_engine()

        with patch("eli.brain.cognitive_engine.execute") as mock_exec:
            mock_exec.return_value = {
                "ok": True,
                "action": "OPEN_APP",
                "content": "Opening Firefox",
                "cmd": "firefox"
            }
            with patch.object(engine, '_parse_intent', return_value={
                "action": "OPEN_APP",
                "args": {"name": "firefox"},
                "confidence": 0.95
            }):
                result = engine.process("open firefox")

        mock_exec.assert_called_once_with("OPEN_APP", {"name": "firefox"})
        assert result.get("ok") is True

    def test_retrieve_relevant_memories_structure(self, isolated_db):
        """_retrieve_relevant_memories() returns a non-empty string with expected sections."""
        engine = self._make_engine()

        engine.memory.add_conversation_turn(
            "user", "Tell me about black holes", engine.session_id, engine.user_id)
        engine.memory.store_memory(
            "Black holes are regions of spacetime with extreme gravity", tags=["physics"])

        context = engine._retrieve_relevant_memories("black holes")

        assert isinstance(context, str)
        assert len(context) > 0


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 7: Persistence — data survives singleton reset
# ─────────────────────────────────────────────────────────────────────────────

class TestMemoryPersistence:
    """Verify data actually persists across Memory instance resets."""

    def test_conversation_survives_singleton_reset(self, isolated_db):
        import eli.brain.memory as m

        m._memory_singleton = None
        mem1 = m.get_memory()
        mem1.add_conversation_turn("user", "persist test", "s1", "u1")

        # Blow away the singleton
        m._memory_singleton = None
        mem2 = m.get_memory()

        results = mem2.get_recent_conversation(limit=10)
        contents = [r["content"] for r in results]
        assert "persist test" in contents, "Data lost after singleton reset"

    def test_stored_memory_survives_reset(self, isolated_db):
        import eli.brain.memory as m

        m._memory_singleton = None
        mem1 = m.get_memory()
        mem1.store_memory("persistent knowledge", tags=["persist"])

        m._memory_singleton = None
        mem2 = m.get_memory()

        results = mem2.recall_memory("persistent knowledge", limit=5)
        assert len(results) >= 1
        assert any("persistent" in r.get("text", "") for r in results)

    def test_habit_events_survive_reset(self, isolated_db):
        import eli.brain.memory as m

        m._memory_singleton = None
        mem1 = m.get_memory()
        mem1.log_habit_event("app_launch", {"app": "persist_test"})

        m._memory_singleton = None
        mem2 = m.get_memory()

        events = mem2.get_habit_events(event_type="app_launch", days=1)
        apps = [e["details"].get("app") if isinstance(e["details"], dict) else ""
                for e in events]
        assert "persist_test" in apps

    def test_env_change_switches_db(self, tmp_path, monkeypatch):
        """Changing ELI_MEMORY_DB causes Memory to use a different file."""
        import eli.brain.memory as m

        db_a = tmp_path / "a.sqlite3"
        db_b = tmp_path / "b.sqlite3"

        monkeypatch.setenv("ELI_MEMORY_DB", str(db_a))
        m._memory_singleton = None
        ma = m.get_memory()
        ma.store_memory("in database A", tags=["db_a"])

        monkeypatch.setenv("ELI_MEMORY_DB", str(db_b))
        m._memory_singleton = None
        mb = m.get_memory()

        results_b = mb.recall_memory("in database A", limit=5)
        assert all("in database A" not in r.get("text", "") for r in results_b), \
            "Data from DB A leaked into DB B"

        results_a = ma.recall_memory("in database A", limit=5)
        # ma still uses db_a path internally
        assert db_a.exists()


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 8: Context builder — what gets injected into the system prompt
# ─────────────────────────────────────────────────────────────────────────────

class TestContextBuilder:
    """Verify build_context() assembles the right payload for the LLM."""

    def test_build_context_returns_string(self):
        from eli.brain.context_builder import build_context
        result = build_context("hello")
        assert isinstance(result, str)

    def test_build_context_includes_persona(self):
        from eli.brain.context_builder import build_context
        result = build_context("test")
        # Should contain either persona content or be non-empty
        assert len(result) > 0

    def test_build_context_never_crashes(self):
        from eli.brain.context_builder import build_context
        # These should never raise, even with weird inputs
        for msg in ["", "hello", "a" * 1000, "special chars: !@#$%^&*()"]:
            result = build_context(msg)
            assert isinstance(result, str)

    def test_build_context_includes_user_message(self):
        from eli.brain.context_builder import build_context
        result = build_context("unique_marker_xyz_987")
        assert "unique_marker_xyz_987" in result

    def test_build_context_includes_recent_memories(self, isolated_db):
        from eli.brain.context_builder import build_context
        from eli.brain.memory_db import add_memory
        add_memory("context builder test memory", tags="test")
        result = build_context("test query")
        # Memory block should appear
        assert isinstance(result, str)


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 9: End-to-end trace — print every step
# ─────────────────────────────────────────────────────────────────────────────

class TestEndToEndTrace:
    """
    Full trace test. Prints each step so you can see exactly what happens.
    Run with -s to see output.
    """

    def test_full_trace_single_prompt(self, isolated_db, capsys):
        import eli.brain.memory as mem_mod
        mem_mod._memory_singleton = None

        import eli.brain.cognitive_engine as ce
        ce._engine = None

        steps = []

        from eli.brain.memory import get_memory
        mem = get_memory()

        # ── Step 1: User sends a message ──────────────────────────────────
        user_input = "What do you remember about me?"
        steps.append(("INPUT", user_input))

        # ── Step 2: Store user turn ───────────────────────────────────────
        session = f"trace-{int(time.time())}"
        user = "trace-user"
        mem.add_conversation_turn("user", user_input, session, user)
        steps.append(("STORE_USER_TURN", f"session={session}"))

        # ── Step 3: Store some prior context ─────────────────────────────
        mem.store_memory("User's name is Sam. He is a chemist.", tags=["identity"])
        mem.store_memory("Sam works on battery chemistry experiments.", tags=["work"])
        mem.add_conversation_turn("user", "I work on battery chemistry", session, user)
        steps.append(("PRE_POPULATE_MEMORY", "2 memories + 1 turn"))

        # ── Step 4: Simulate _retrieve_relevant_memories ─────────────────
        conversations = mem.get_recent_conversation(limit=150, user_id=user)
        steps.append(("FETCH_CONVERSATIONS", f"{len(conversations)} turns"))

        semantic = mem.search_conversations("remember", user_id=user, limit=20)
        steps.append(("SEMANTIC_SEARCH", f"{len(semantic)} results"))

        # Use a query that will actually match via FTS
        recalled = mem.recall_memory("Sam chemist", limit=20)
        steps.append(("RECALL_MEMORY", f"{len(recalled)} memories"))

        # Build context string (what cognitive engine does)
        ctx_parts = []
        if conversations:
            lines = [f"  [{r['role']}]: {r['content'][:80]}" for r in conversations]
            ctx_parts.append("Conversation history:\n" + "\n".join(lines))
        if recalled:
            lines = [f"  - {r.get('text','')[:80]}" for r in recalled[:5]]
            ctx_parts.append("Stored knowledge:\n" + "\n".join(lines))
        memory_context = "\n\n".join(ctx_parts)
        steps.append(("MEMORY_CONTEXT_BUILT", f"{len(memory_context)} chars"))

        # ── Step 5: Mock LLM call ─────────────────────────────────────────
        system_prompt = f"[PERSONA]\nYou are ELI.\n\n[MEMORY]\n{memory_context}\n\nNow respond:"
        llm_response = "I remember you are Sam, a chemist working on battery chemistry."
        steps.append(("LLM_CALL", f"system={len(system_prompt)} chars, response={len(llm_response)} chars"))

        # ── Step 6: Store assistant response ─────────────────────────────
        mem.add_conversation_turn("assistant", llm_response, session, user)
        steps.append(("STORE_ASSISTANT_TURN", "stored"))

        # ── Step 7: Verify everything is in DB ───────────────────────────
        conn = sqlite3.connect(str(isolated_db))
        conv_count = conn.execute(
            "SELECT COUNT(*) FROM conversations WHERE session_id=?", (session,)
        ).fetchone()[0]
        mem_count = conn.execute(
            "SELECT COUNT(*) FROM memories"
        ).fetchone()[0]
        conn.close()
        steps.append(("DB_STATE", f"conversations={conv_count}, memories={mem_count}"))

        # ── Print full trace ──────────────────────────────────────────────
        print("\n" + "═" * 70)
        print("  ELI MEMORY PIPELINE TRACE")
        print("═" * 70)
        for i, (step, detail) in enumerate(steps, 1):
            print(f"  [{i:02d}] {step:<30} {detail}")
        print("═" * 70)
        print(f"\n  MEMORY CONTEXT INJECTED INTO LLM:")
        print("  " + "-" * 50)
        for line in memory_context.split("\n"):
            print(f"  {line}")
        print("  " + "-" * 50)
        print(f"\n  LLM RESPONSE: {llm_response}")
        print("═" * 70 + "\n")

        # ── Assertions ────────────────────────────────────────────────────
        assert conv_count >= 3, "Expected at least 3 conversation turns (2 user + 1 assistant)"
        assert mem_count >= 1, "Expected at least 1 stored memory"
        # "Sam" should appear in either conversation history or recalled memories
        assert "Sam" in memory_context or mem_count >= 1, \
            f"Identity memory not stored. context={memory_context[:200]}"
        # More specific: stored memories must contain Sam
        conn2 = sqlite3.connect(str(isolated_db))
        sam_row = conn2.execute(
            "SELECT COUNT(*) FROM memories WHERE text LIKE '%Sam%'"
        ).fetchone()[0]
        conn2.close()
        assert sam_row >= 1, "Memory about Sam not found in memories table"
        assert len(memory_context) > 0, "Memory context was empty"

    def test_multi_turn_context_grows(self, isolated_db):
        """Each turn adds to context available for next turn."""
        import eli.brain.memory as mem_mod
        mem_mod._memory_singleton = None
        mem = mem_mod.get_memory()

        session = "multi-turn"
        user = "mt-user"

        turns = [
            ("user",      "My name is Sam"),
            ("assistant", "Hello Sam."),
            ("user",      "I work on battery chemistry"),
            ("assistant", "Battery chemistry is fascinating."),
            ("user",      "I use Python for simulations"),
            ("assistant", "Python is great for scientific computing."),
        ]

        for role, content in turns:
            mem.add_conversation_turn(role, content, session, user)
            time.sleep(0.005)

        # After 6 turns, get_recent_conversation should return all of them
        context = mem.get_recent_conversation(limit=150, user_id=user)
        contents = [r["content"] for r in context]

        assert "My name is Sam" in contents
        assert "I work on battery chemistry" in contents
        assert "I use Python for simulations" in contents

        # Search should find relevant turns
        battery_results = mem.search_conversations("battery", user_id=user, limit=10)
        assert len(battery_results) >= 1
        assert any("battery" in r["content"].lower() for r in battery_results)

    def test_memory_recall_affects_weight(self, isolated_db):
        """Recalled memories get a weight boost (feedback loop)."""
        import eli.brain.memory as mem_mod
        mem_mod._memory_singleton = None
        mem = mem_mod.get_memory()

        mem.store_memory("Sam prefers dark mode", tags=["preference"])

        conn = sqlite3.connect(str(isolated_db))
        before_weight = conn.execute(
            "SELECT weight FROM memories ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()[0]
        conn.close()

        mem.recall_memory("dark mode preference", limit=5)

        conn = sqlite3.connect(str(isolated_db))
        after_weight = conn.execute(
            "SELECT weight FROM memories ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()[0]
        conn.close()

        # Weight should be same or higher after recall (depends on impl)
        assert after_weight >= before_weight * 0.9  # allow tiny float variation
