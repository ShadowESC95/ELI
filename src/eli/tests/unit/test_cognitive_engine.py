import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def engine():
    """Fresh cognitive engine — reset singleton before each test."""
    import eli.brain.cognitive_engine as ce_mod
    ce_mod._engine = None
    from eli.brain.cognitive_engine import get_engine
    return get_engine()


@patch("eli.brain.cognitive_engine.gguf_inference.chat_completion")
def test_process_chat_nonstream(mock_chat, engine):
    mock_chat.return_value = "mock response"
    engine.memory = MagicMock()
    engine.memory.get_recent_conversation.return_value = []
    engine.memory.recall_memory.return_value = []
    engine.memory.search_conversations.return_value = []
    engine.memory.add_conversation_turn = MagicMock()

    result = engine.process("hello", stream=False)
    assert result["ok"] is True
    assert result["content"] == "mock response"


@patch("eli.brain.cognitive_engine.gguf_inference.generate")
def test_process_chat_stream(mock_generate, engine):
    def mock_gen(**kwargs):
        yield {"response": "Hello"}
        yield {"response": " world"}
    mock_generate.side_effect = mock_gen
    engine.memory = MagicMock()
    engine.memory.get_recent_conversation.return_value = []
    engine.memory.recall_memory.return_value = []
    engine.memory.search_conversations.return_value = []

    gen = engine.process("hello", stream=True)
    tokens = list(gen)
    assert tokens == ["Hello", " world"]
