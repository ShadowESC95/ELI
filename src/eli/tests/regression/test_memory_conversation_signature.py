def test_add_conversation_turn_accepts_session_and_user(tmp_path, monkeypatch):
    # Adjust import to your actual module path
    from eli.brain import paths
    from eli.brain.memory import Memory

    db_path = tmp_path / "eli_memory.sqlite3"
    monkeypatch.setenv("ELI_MEMORY_DB", str(db_path))

    m = Memory()
    m.add_conversation_turn("user", "hello", "sess-1", "user-1")  # must not crash

    recent = m.get_recent_conversation(limit=5)
    assert recent
    assert recent[-1]["role"] == "user"
    assert recent[-1]["content"] == "hello"
