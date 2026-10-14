#!/usr/bin/env python3
"""Empties ELI's memory database (keeps its tables). Usage: ./wipe_memory.sh [--yes]"""
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

def reset_db(db_path: Path):
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    con = sqlite3.connect(str(db_path))
    try:
        con.execute("PRAGMA foreign_keys=OFF;")
        con.execute("BEGIN;")

        tables = [
            row[0]
            for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
            ).fetchall()
        ]

        # Delete rows from all user tables
        for t in tables:
            con.execute(f'DELETE FROM "{t}";')

        # Reset autoincrement counters if present
        try:
            con.execute("DELETE FROM sqlite_sequence;")
        except sqlite3.OperationalError:
            pass

        con.execute("COMMIT;")
        con.execute("VACUUM;")
    finally:
        con.close()

    print(f"[OK] Wiped data, preserved schema: {db_path}")

def main():
    from eli.brain.paths import PATHS
    path = Path(PATHS.memory_db)
    if "--yes" not in sys.argv:
        answer = input(f"Delete everything ELI remembers in {path}? Type yes: ").strip().lower()
        if answer != "yes":
            print("Nothing deleted.")
            return
    reset_db(path)

if __name__ == "__main__":
    main()
