from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from eli.brain.db_paths import resolve_db_paths
from eli.brain.memory import get_memory

@dataclass(frozen=True)
class Stores:
    user: object   # Memory instance
    agent: object  # Memory instance

_STORES = {}  # key: (user_db, agent_db) -> Stores

def get_stores(user_db: str | Path | None = None, agent_db: str | Path | None = None) -> Stores:
    """
    Returns a pair of Memory instances:
      - user: stable user memory
      - agent: internal agent state / proactive logs / self-reflection
    """
    global _STORES

    resolved = resolve_db_paths()
    user_db = Path(user_db) if user_db is not None else resolved.user_db
    agent_db = Path(agent_db) if agent_db is not None else resolved.agent_db

    user_db = user_db.expanduser().resolve()
    agent_db = agent_db.expanduser().resolve()

    key = (str(user_db), str(agent_db))
    if key not in _STORES:
        _STORES[key] = Stores(
            user=get_memory(user_db),
            agent=get_memory(agent_db),
        )

    return _STORES[key]
