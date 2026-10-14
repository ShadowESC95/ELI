#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import json
import re
from datetime import datetime

from eli.brain.paths import PATHS

ROOT = Path(__file__).resolve().parents[1]
PERSONA = ROOT / "brain" / "persona.txt"
NOTES = Path(PATHS.notes_dir)
LOGS = Path(PATHS.log_dir)

NOTES.mkdir(parents=True, exist_ok=True)
LOGS.mkdir(parents=True, exist_ok=True)

RECENT_FEEDBACK = NOTES / "recent_user_feedback.txt"
HEADER = "## User Preferences (Auto-Updated)"

# NOTE: "call me X" MUST NOT trigger inside "don't call me X"
PREF_PATTERNS = [
    r"\b(don't|do not)\s+call\s+me\s+.+",
    r"\bkeep\s+(answers|responses)\s+(short|concise)\b",
    r"\bask\s+fewer\s+questions\b",
    r"\buse\s+(markdown|bullet points)\b",
    r"(?<!don't\s)(?<!do not\s)\bcall\s+me\s+[A-Za-z0-9 _-]{1,40}\b",
]

def load_persona() -> str:
    return PERSONA.read_text(encoding="utf-8") if PERSONA.exists() else ""

def save_persona(text: str) -> None:
    PERSONA.write_text(text, encoding="utf-8")

def _normalize_pref(line: str) -> str:
    # Normalize spacing/case a bit, keep user intent.
    x = (line or "").strip()
    # Ensure capitalized first letter for consistency
    if x and not x[0].isupper():
        x = x[0].upper() + x[1:]
    # Ensure trailing period for "Don't call me ..." style (optional)
    if re.match(r"(?i)^(don't|do not)\s+call\s+me\b", x) and not x.endswith("."):
        x += "."
    return x

def extract_prefs(text: str) -> list[str]:
    t = text or ""

    # First, find explicit "don't call me X" targets so we can block "call me X"
    dont_targets = []
    for m in re.finditer(r"(?im)^(?:don't|do not)\s+call\s+me\s+(.+?)\s*\.?\s*$", t):
        dont_targets.append(m.group(1).strip().strip(".! "))

    prefs: list[str] = []
    for pat in PREF_PATTERNS:
        for m in re.finditer(pat, t, flags=re.I | re.M):
            hit = m.group(0).strip()

            # Block "call me X" if X is in dont_targets
            m2 = re.match(r"(?i)^call\s+me\s+(.+)$", hit)
            if m2:
                name = m2.group(1).strip().strip(".! ")
                if any(name.lower() == d.lower() for d in dont_targets):
                    continue

            prefs.append(_normalize_pref(hit))

    # De-dupe preserving order
    out: list[str] = []
    for p2 in prefs:
        if p2 and p2 not in out:
            out.append(p2)
    return out

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

def main():
    current = load_persona()
    recent = RECENT_FEEDBACK.read_text(encoding="utf-8") if RECENT_FEEDBACK.exists() else ""

    prefs = extract_prefs(recent)
    patched = propose_patch(current, prefs)

    if not patched:
        print("No persona changes proposed.")
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = PERSONA.with_suffix(f".txt.bak.{ts}")
    if current:
        backup.write_text(current, encoding="utf-8")

    save_persona(patched)

    (LOGS / f"persona_update_{ts}.json").write_text(
        json.dumps({"added_preferences": prefs, "backup": str(backup) if current else None}, indent=2),
        encoding="utf-8",
    )

    print("Applied persona update.")
    if current:
        print("Backup:", backup)

if __name__ == "__main__":
    main()
