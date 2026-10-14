from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# IMPORTANT:
# - user_db is "who the user is"
# - agent_db is "what the agent does/learns internally"
#
# Priority (highest -> lowest):
#   1) ELI_USER_DB_PATH / ELI_AGENT_DB_PATH
#   2) ELI_DB_PATH_USER / ELI_DB_PATH_AGENT (compat)
#   3) ELI_DB_PATH (single override -> used for BOTH if set)
#   4) default in artifacts/

@dataclass(frozen=True)
class DBPaths:
    user_db: Path
    agent_db: Path

def _artifacts_dir_fallback() -> Path:
    # ELI's data folder (never its own code folder, which is read-only when packaged).
    # paths.py imports nothing from eli, so importing it here makes no cycle.
    from eli.brain.paths import get_paths
    return Path(get_paths().data_dir)

def resolve_db_paths() -> DBPaths:
    artifacts = _artifacts_dir_fallback()
    artifacts.mkdir(parents=True, exist_ok=True)

    single = os.environ.get("ELI_DB_PATH")

    user = (
        os.environ.get("ELI_USER_DB_PATH")
        or os.environ.get("ELI_DB_PATH_USER")
        or single
        or str(artifacts / "user_memory.sqlite3")
    )
    agent = (
        os.environ.get("ELI_AGENT_DB_PATH")
        or os.environ.get("ELI_DB_PATH_AGENT")
        or single
        or str(artifacts / "agent_state.sqlite3")
    )

    return DBPaths(user_db=Path(user), agent_db=Path(agent))
