from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Optional

from eli.brain.memory import get_memory

_SESSION_FILE = Path.home() / ".eli_session_id"


def get_or_create_session_id() -> str:
    try:
        if _SESSION_FILE.exists():
            sid = _SESSION_FILE.read_text(encoding="utf-8", errors="ignore").strip()
            if sid:
                return sid
        sid = f"session-{uuid.uuid4()}"
        _SESSION_FILE.write_text(sid, encoding="utf-8")
        return sid
    except Exception:
        return f"session-{int(time.time())}"


def ensure_schema():
    get_memory().init_db()


def append_chat_turn(session_id: str, role: str, content: str, user_id: str = "gui-user"):
    get_memory().add_conversation_turn(role=role, content=content, session_id=session_id, user_id=user_id)


def get_last_user_utterance(session_id: str) -> Optional[str]:
    turns = get_memory().get_recent_conversation(limit=20, session_id=session_id)
    for turn in turns:
        if turn.get("role") == "user":
            return turn.get("content")
    return None


def summarize_recent_window(session_id: str, window: int = 10) -> str:
    turns = list(reversed(get_memory().get_recent_conversation(limit=max(1, int(window)), session_id=session_id)))
    if not turns:
        return "No recent conversation available."
    user_facts = []
    assistant_actions = []
    for turn in turns:
        role = turn.get("role")
        content = (turn.get("content") or "").strip().replace("\n", " ")
        if not content:
            continue
        if role == "user":
            user_facts.append(content)
        else:
            assistant_actions.append(content)
    lines = [f"Recent conversation summary ({len(turns)} turns):"]
    if user_facts:
        lines.append("User said:")
        for item in user_facts[-5:]:
            lines.append(f"- {item[:180]}")
    if assistant_actions:
        lines.append("ELI replied:")
        for item in assistant_actions[-5:]:
            lines.append(f"- {item[:180]}")
    return "\n".join(lines)
