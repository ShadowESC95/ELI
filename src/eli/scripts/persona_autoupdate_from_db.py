#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import os, re, json, sqlite3
from datetime import datetime

from eli.brain.paths import PATHS

ROOT = Path(__file__).resolve().parents[1]
from eli.brain.persona import persona_file

PERSONA = persona_file(for_writing=True)  # this user's copy, not the one ELI ships with
LOGS = Path(PATHS.log_dir)
LOGS.mkdir(parents=True, exist_ok=True)

DB = Path(PATHS.memory_db)

HEADER = "## User Preferences (Auto-Updated)"

# Conservative patterns (only explicit prefs)
PREF_PATTERNS = [
    r"(?im)^\s*(?:don't|do not)\s+call\s+me\s+.+$",
    r"(?i)\bkeep\s+(?:answers|responses)\s+(?:short|concise)\b",
    r"(?i)\bask\s+fewer\s+questions\b",
    r"(?i)\buse\s+(?:markdown|bullet points)\b",
]

def load_persona() -> str:
    return PERSONA.read_text(encoding="utf-8") if PERSONA.exists() else ""

def save_persona(text: str) -> None:
    PERSONA.write_text(text, encoding="utf-8")

def extract_prefs(text: str) -> list[str]:
    prefs = []
    for pat in PREF_PATTERNS:
        for m in re.finditer(pat, text):
            hit = m.group(0).strip()
            if hit and not hit[0].isupper():
                hit = hit[0].upper() + hit[1:]
            if hit not in prefs:
                prefs.append(hit)
    return prefs

def propose_patch(current: str, prefs: list[str]) -> str | None:
    if not prefs:
        return None

    if HEADER not in current:
        current = current.rstrip() + "\n\n" + HEADER + "\n"

    existing = set(re.findall(r"^- (.*)$", current, flags=re.M))
    additions = [p for p in prefs if p not in existing]
    if not additions:
        return None

    return current.rstrip() + "\n" + "\n".join([f"- {a}" for a in additions]) + "\n"

def fetch_recent_user_text(conn: sqlite3.Connection, limit: int = 250) -> str:
    cols = [r[1] for r in conn.execute("PRAGMA table_info(conversation_turns)").fetchall()]
    if not cols:
        return ""

    content_col = "content" if "content" in cols else ("message" if "message" in cols else None)
    role_col = "role" if "role" in cols else None
    ts_col = "ts" if "ts" in cols else ("timestamp" if "timestamp" in cols else None)

    if not content_col:
        return ""

    sql = f"SELECT {content_col}"
    if role_col:
        sql += f", {role_col}"
    sql += " FROM conversation_turns"

    params = []
    if role_col:
        sql += f" WHERE {role_col}='user'"

    if ts_col:
        sql += f" ORDER BY {ts_col} DESC"
    sql += " LIMIT ?"
    params.append(int(limit))

    rows = conn.execute(sql, params).fetchall()
    return "\n".join([r[0] for r in rows if r and r[0]])

def main():
    if not DB.exists():
        print("DB not found:", DB)
        return

    with sqlite3.connect(DB) as conn:
        text = fetch_recent_user_text(conn, limit=250)

    prefs = extract_prefs(text)
    current = load_persona()
    patched = propose_patch(current, prefs)

    if not patched:
        print("No persona changes proposed.")
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = PERSONA.with_suffix(f".txt.bak.{ts}")
    if current:
        backup.write_text(current, encoding="utf-8")

    save_persona(patched)

    (LOGS / f"persona_update_from_db_{ts}.json").write_text(
        json.dumps({"db": str(DB), "added_preferences": prefs, "backup": str(backup)}, indent=2),
        encoding="utf-8",
    )

    print("Applied persona update from DB. Backup:", backup)

if __name__ == "__main__":
    main()
