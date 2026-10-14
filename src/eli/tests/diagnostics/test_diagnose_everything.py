# src/eli/tests/diagnostics/test_diagnose_everything.py
from __future__ import annotations

import os
import sys
import sqlite3
import importlib
import inspect
from pathlib import Path

import pytest


def _import(mod: str):
    try:
        return importlib.import_module(mod)
    except Exception as e:
        return e


def _file_of(mod) -> str:
    try:
        return str(Path(mod.__file__).resolve())
    except Exception:
        return "<no __file__>"


def _safe_source(fn) -> str:
    try:
        return inspect.getsource(fn)
    except Exception as e:
        return f"<no source: {e}>"


def _tables(db_path: Path) -> set[str]:
    if not db_path.exists():
        return set()
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r[0] for r in rows}


def _cols(db_path: Path, table: str) -> set[str]:
    if not db_path.exists():
        return set()
    with sqlite3.connect(str(db_path)) as conn:
        try:
            rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        except Exception:
            return set()
    return {r[1] for r in rows}


def _print_block(title: str, lines: list[str]):
    sep = "=" * 88
    print("\n" + sep)
    print(title)
    print(sep)
    for ln in lines:
        print(ln)
    print(sep + "\n")


def _looks_patched(text: str) -> bool:
    # signals from your earlier run: lambdas + Fake objects coming from tests
    signals = ("<lambda>", "Fake", "test_eli_comprehensive", "_FakeDaemon", "_FakeSI")
    return any(s in text for s in signals)


def test_00_import_origins_printed():
    mods = {
        "eli.brain.proactive_daemon": _import("eli.brain.proactive_daemon"),
        "eli.proactive.proactive_daemon": _import("eli.proactive.proactive_daemon"),
        "eli.brain.memory": _import("eli.brain.memory"),
        "eli.brain.paths": _import("eli.brain.paths"),
        "eli.brain.self_improvement": _import("eli.brain.self_improvement"),
        "eli.brain.cognitive_engine": _import("eli.brain.cognitive_engine"),
        "eli.plugins.weather": _import("eli.plugins.weather"),
    }

    lines = []
    for name, m in mods.items():
        if isinstance(m, Exception):
            lines.append(f"{name}: IMPORT ERROR -> {type(m).__name__}: {m}")
        else:
            lines.append(f"{name}: {_file_of(m)}")

    _print_block("IMPORT ORIGINS (brain vs proactive)", lines)


def test_01_env_and_db_path_resolution_printed():
    env_lines = [
        f"PYTHON: {sys.executable}",
        f"CWD: {os.getcwd()}",
        f"ELI_DB_PATH={os.getenv('ELI_DB_PATH')}",
        f"ELI_MEMORY_DB={os.getenv('ELI_MEMORY_DB')}",
        f"ELI_MEMORY_DB_PATH={os.getenv('ELI_MEMORY_DB_PATH')}",
    ]

    paths_mod = _import("eli.brain.paths")
    mem_mod = _import("eli.brain.memory")

    path_lines = []
    if isinstance(paths_mod, Exception):
        path_lines.append(f"eli.brain.paths import error: {paths_mod}")
    else:
        PATHS = getattr(paths_mod, "PATHS", None)
        path_lines.append(f"paths.py: {_file_of(paths_mod)}")
        path_lines.append(f"PATHS type: {type(PATHS)}")
        for attr in ("ELI_ROOT", "ARTIFACTS_DIR", "DB_PATH", "ELI_DB_PATH"):
            if hasattr(paths_mod, attr):
                path_lines.append(f"module.{attr} = {getattr(paths_mod, attr)}")
        if PATHS is not None:
            for attr in ("root", "artifacts", "artifacts_dir", "db_path", "db", "database"):
                if hasattr(PATHS, attr):
                    path_lines.append(f"PATHS.{attr} = {getattr(PATHS, attr)}")

    mem_lines = []
    if isinstance(mem_mod, Exception):
        mem_lines.append(f"eli.brain.memory import error: {mem_mod}")
    else:
        mem_lines.append(f"memory.py: {_file_of(mem_mod)}")
        try:
            mem_mod._memory_singleton = None  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            m = mem_mod.get_memory()  # type: ignore[attr-defined]
            mem_lines.append(f"get_memory() -> {type(m)}")
            mem_lines.append(f"Memory.db_path -> {getattr(m, 'db_path', None)}")
        except Exception as e:
            mem_lines.append(f"get_memory() ERROR -> {type(e).__name__}: {e}")

    _print_block("ENV + PATHS + MEMORY DB PATH", env_lines + [""] + path_lines + [""] + mem_lines)


def test_02_fail_if_singletons_are_patched():
    brain_pd = _import("eli.brain.proactive_daemon")
    si_mod = _import("eli.brain.self_improvement")

    lines = []
    if isinstance(brain_pd, Exception):
        lines.append(f"eli.brain.proactive_daemon import error: {brain_pd}")
    else:
        get_daemon = getattr(brain_pd, "get_daemon", None)
        lines.append(f"eli.brain.proactive_daemon: {_file_of(brain_pd)}")
        lines.append(f"get_daemon repr: {get_daemon!r}")
        if callable(get_daemon):
            src = _safe_source(get_daemon)
            lines.append("get_daemon source head:")
            lines.append(src[:500].replace("\n", "\\n"))

    lines.append("")

    if isinstance(si_mod, Exception):
        lines.append(f"eli.brain.self_improvement import error: {si_mod}")
    else:
        get_si = getattr(si_mod, "get_self_improvement", None)
        lines.append(f"eli.brain.self_improvement: {_file_of(si_mod)}")
        lines.append(f"get_self_improvement repr: {get_si!r}")
        if callable(get_si):
            src = _safe_source(get_si)
            lines.append("get_self_improvement source head:")
            lines.append(src[:500].replace("\n", "\\n"))

    _print_block("SINGLETON PATCH LEAK CHECK", lines)

    blob = "\n".join(lines)
    if _looks_patched(blob):
        pytest.fail("Singletons look patched/leaking fakes (lambda/Fake/test module detected). See output above.")


def test_03_db_schema_probe_printed():
    mem_mod = _import("eli.brain.memory")
    if isinstance(mem_mod, Exception):
        pytest.fail(f"memory import failed: {mem_mod}")

    try:
        mem_mod._memory_singleton = None  # type: ignore[attr-defined]
    except Exception:
        pass

    m = mem_mod.get_memory()  # type: ignore[attr-defined]
    db_path = Path(str(getattr(m, "db_path", ""))).expanduser().resolve()

    lines = [f"DB path resolved to: {db_path}", f"Exists: {db_path.exists()}"]
    t = _tables(db_path)
    lines.append(f"Tables ({len(t)}): {sorted(t)}")

    key_tables = [
        "habit_events",
        "habit_rules",
        "capability_proposals",
        "failures",
        "conversations",
        "memories",
        "user_patterns",
        "corrections",
        "observations",
    ]
    for table in key_tables:
        cols = _cols(db_path, table)
        lines.append(f"{table} cols: {sorted(cols) if cols else '<missing>'}")

    _print_block("DB SCHEMA PROBE", lines)


def test_04_fail_if_two_proactive_daemons_exist_and_disagree():
    """
    It's OK for eli.proactive.proactive_daemon to exist as a compatibility wrapper,
    as long as it re-exports the SAME daemon class/singleton as eli.brain.proactive_daemon.

    We only fail if the two modules produce different daemon implementations or
    different singleton objects (meaning: two daemons could run / diverge).
    """
    a = _import("eli.brain.proactive_daemon")
    b = _import("eli.proactive.proactive_daemon")

    if isinstance(a, Exception) or isinstance(b, Exception):
        return  # if one doesn't exist, no ambiguity

    a_path = _file_of(a)
    b_path = _file_of(b)

    # If they are the same file, trivially fine.
    if a_path == b_path:
        return

    # If different files, they MUST still resolve to the same implementation.
    if not (hasattr(a, "get_daemon") and hasattr(b, "get_daemon")):
        pytest.fail("Both proactive_daemon modules must expose get_daemon().")

    da = a.get_daemon()
    db = b.get_daemon()

    # Same singleton object is ideal
    if da is db:
        return

    # If not the same object, at minimum they must be the same concrete class
    # and live in the canonical module (eli.brain.proactive_daemon).
    if da.__class__ is not db.__class__:
        pytest.fail(
            "Two proactive_daemon modules return different daemon classes.\n"
            f"brain={da.__class__} vs proactive={db.__class__}"
        )

    if da.__class__.__module__ != "eli.brain.proactive_daemon":
        pytest.fail(
            "Proactive daemon class must come from eli.brain.proactive_daemon.\n"
            f"got module={da.__class__.__module__}"
        )
