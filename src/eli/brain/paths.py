from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Any

try:
    from platformdirs import user_data_dir, user_config_dir, user_cache_dir, user_log_dir
except Exception:  # pragma: no cover
    user_data_dir = user_config_dir = user_cache_dir = user_log_dir = None  # type: ignore

# ELI's own folder name: ~/.local/share/eli-ai, ~/.config/eli-ai (later ELI versions use other names)
APP_NAME = "eli-ai"
APP_AUTHOR = "eli-ai"


def _env_path(key: str) -> Optional[Path]:
    v = os.environ.get(key)
    return Path(v).expanduser().resolve() if v else None


def _find_project_root() -> Path:
    pr = os.environ.get("ELI_PROJECT_ROOT") or os.environ.get("ELI_ROOT")
    if pr:
        return Path(pr).expanduser().resolve()
    here = Path(__file__).resolve()
    return here.parents[4] if len(here.parents) >= 5 else here.parents[-1]


@dataclass(frozen=True)
class EliPaths:
    project_root: Path
    data_dir: Path
    config_dir: Path
    cache_dir: Path
    log_dir: Path
    artifacts_dir: Path
    conversations_dir: Path
    proactive_dir: Path
    notes_dir: Path
    models_dir: Path
    memory_db: Path
    user_db: Path
    agent_db: Path

    @property
    def root(self) -> Path:
        return self.data_dir

    @property
    def artifacts(self) -> Path:
        return self.artifacts_dir

    @property
    def db(self) -> Path:
        return self.memory_db

    @property
    def db_path(self) -> Path:
        return self.memory_db

    @property
    def database(self) -> Path:
        return self.memory_db

    @property
    def model(self) -> Path:
        p = _env_path("ELI_GGUF_MODEL_PATH")
        if p and p.exists():
            return p
        name = os.environ.get("ELI_GGUF_MODEL")
        if name:
            cand = (self.models_dir / name).expanduser().resolve()
            if cand.exists():
                return cand
        # Otherwise any .gguf put in the models folder (the newest if there are several)
        try:
            found = sorted(self.models_dir.glob("*.gguf"), key=lambda f: f.stat().st_mtime, reverse=True)
        except OSError:
            found = []
        if found:
            return found[0]
        # Running as an AppImage: a model saved in the same folder as the AppImage
        appimage = os.environ.get("APPIMAGE")
        if appimage:
            try:
                beside = sorted(Path(appimage).parent.glob("*.gguf"), key=lambda f: f.stat().st_mtime, reverse=True)
            except OSError:
                beside = []
            if beside:
                return beside[0]
        # The model the app ships with
        shipped = _env_path("ELI_DEFAULT_MODEL")
        if shipped and shipped.exists():
            return shipped
        return self.models_dir / "model.gguf"


_Paths = EliPaths


def get_paths() -> EliPaths:
    project_root = _find_project_root()
    portable = _env_path("ELI_PORTABLE_DIR")
    if portable:
        data_dir = (portable / "data").resolve()
        config_dir = (portable / "config").resolve()
        cache_dir = (portable / "cache").resolve()
        log_dir = (portable / "logs").resolve()
        artifacts_dir = (data_dir / "artifacts").resolve()
        models_dir = (_env_path("ELI_MODELS_DIR") or (portable / "models")).resolve()
    else:
        data_dir = _env_path("ELI_DATA_DIR")
        config_dir = _env_path("ELI_CONFIG_DIR")
        cache_dir = _env_path("ELI_CACHE_DIR")
        log_dir = _env_path("ELI_LOG_DIR")
        if user_data_dir is None:
            home = Path.home()
            data_dir = data_dir or (home / ".local" / "share" / APP_NAME)
            config_dir = config_dir or (home / ".config" / APP_NAME)
            cache_dir = cache_dir or (home / ".cache" / APP_NAME)
            log_dir = log_dir or (home / ".local" / "state" / APP_NAME / "logs")
        else:
            data_dir = data_dir or Path(user_data_dir(APP_NAME, APP_AUTHOR))
            config_dir = config_dir or Path(user_config_dir(APP_NAME, APP_AUTHOR))
            cache_dir = cache_dir or Path(user_cache_dir(APP_NAME, APP_AUTHOR))
            log_dir = log_dir or Path(user_log_dir(APP_NAME, APP_AUTHOR))
        artifacts_dir = _env_path("ELI_ARTIFACTS_DIR") or _env_path("ELI_ARTIFACTS") or (data_dir / "artifacts")
        models_dir = _env_path("ELI_MODELS_DIR") or (data_dir / "models")

    conversations_dir = artifacts_dir / "conversations"
    proactive_dir = artifacts_dir / "proactive"
    notes_dir = artifacts_dir / "notes"

    explicit_user = _env_path("ELI_USER_DB") or _env_path("ELI_USER_DB_PATH")
    explicit_agent = _env_path("ELI_AGENT_DB") or _env_path("ELI_AGENT_DB_PATH")
    legacy_single = _env_path("ELI_DB_PATH") or _env_path("ELI_MEMORY_DB") or _env_path("ELI_MEMORY_DB_PATH")

    if legacy_single and not explicit_user and not explicit_agent:
        memory_db = user_db = agent_db = legacy_single
    else:
        memory_db = legacy_single or (data_dir / "eli_memory.sqlite3")
        user_db = explicit_user or (data_dir / "user.sqlite3")
        agent_db = explicit_agent or (data_dir / "agent.sqlite3")

    return EliPaths(
        project_root=project_root,
        data_dir=data_dir.resolve(),
        config_dir=config_dir.resolve(),
        cache_dir=cache_dir.resolve(),
        log_dir=log_dir.resolve(),
        artifacts_dir=artifacts_dir.resolve(),
        conversations_dir=conversations_dir.resolve(),
        proactive_dir=proactive_dir.resolve(),
        notes_dir=notes_dir.resolve(),
        models_dir=models_dir.resolve(),
        memory_db=memory_db.resolve(),
        user_db=user_db.resolve(),
        agent_db=agent_db.resolve(),
    )


def ensure_dirs(p: Optional[EliPaths] = None) -> EliPaths:
    p = p or get_paths()
    for d in [p.data_dir, p.config_dir, p.cache_dir, p.log_dir, p.artifacts_dir, p.conversations_dir, p.proactive_dir, p.notes_dir, p.models_dir]:
        d.mkdir(parents=True, exist_ok=True)
    for db in [p.memory_db, p.user_db, p.agent_db]:
        db.parent.mkdir(parents=True, exist_ok=True)
    return p


class _PathProxy:
    def __init__(self, attr: str):
        self.attr = attr

    def _value(self) -> Path:
        return getattr(get_paths(), self.attr)

    def __fspath__(self) -> str:
        return str(self._value())

    def __str__(self) -> str:
        return str(self._value())

    def __repr__(self) -> str:
        return repr(self._value())

    def __truediv__(self, other: Any):
        return self._value() / other

    def __getattr__(self, name: str):
        return getattr(self._value(), name)

    def __eq__(self, other: object) -> bool:
        try:
            return self._value() == other
        except Exception:
            return False


class _PathsProxy:
    def __getattr__(self, name: str):
        return getattr(get_paths(), name)

    def __repr__(self) -> str:
        return repr(get_paths())


PROJECT_ROOT: Path = _find_project_root()
ELI_ROOT = _PathProxy("project_root")
PATHS = _PathsProxy()
ARTIFACTS_DIR = _PathProxy("artifacts_dir")
CONVERSATIONS_DIR = _PathProxy("conversations_dir")
MODELS_DIR = _PathProxy("models_dir")
DB_PATH = _PathProxy("memory_db")

__all__ = [
    "EliPaths", "_Paths", "_find_project_root", "get_paths", "ensure_dirs",
    "PROJECT_ROOT", "ELI_ROOT", "PATHS", "ARTIFACTS_DIR", "CONVERSATIONS_DIR", "MODELS_DIR", "DB_PATH",
]
