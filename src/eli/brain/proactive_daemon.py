#!/usr/bin/env python3
"""
ELI Proactive Daemon - Self-Improvement & Intelligence System
==============================================================

Option B (TWO DBs):
- Reads user-facing memories/conversations from USER DB
- Writes proactive observations/improvements/errors to AGENT DB
"""

import os
import sys
import time
import subprocess
import json
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
import threading
import queue

# IMPORTANT: don't force sys.path unless you're running this file directly.
# In normal package use, PYTHONPATH/src handles it.
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # points at src/

from eli.brain.memory import (
    get_memory,
    get_agent_memory,
    resolve_db_paths,
)

class ProactiveDaemon:
    """
    Self-improving proactive intelligence daemon
    - READS: user DB
    - WRITES: agent DB
    """

    def __init__(self):
        self.project_root = Path(__file__).resolve().parents[2]  # src/eli -> parents[2] == src
        self.running = False
        self.suggestion_queue = queue.Queue()

        # Two DB handles
        self.user_mem = get_memory()
        self.agent_mem = get_agent_memory()

        # Keep db_path attribute for legacy code paths that still use sqlite3 directly
        # (but this should always refer to AGENT DB in Option B)
        self.db_path = Path(self.agent_mem.db_path)

        print("[PROACTIVE] Daemon initialized")
        print(f"[PROACTIVE] USER DB  : {self.user_mem.db_path}")
        print(f"[PROACTIVE] AGENT DB : {self.agent_mem.db_path}")

    # ------------------------------
    # Low-level helpers (agent DB)
    # ------------------------------

    def _safe_execute_query(self, query, params=(), fetch_all=True):
        """
        Executes query against AGENT DB (proactive/internal).
        Missing tables -> empty result.
        """
        try:
            con = sqlite3.connect(str(self.db_path))
            cur = con.cursor()
            cur.execute(query, params)
            result = cur.fetchall() if fetch_all else cur.fetchone()
            con.close()
            return result
        except sqlite3.OperationalError as e:
            if "no such table" in str(e):
                return [] if fetch_all else None
            raise

    # ------------------------------
    # Reads: USER DB
    # Writes: AGENT DB
    # ------------------------------

    def analyze_user_patterns(self) -> List[Dict[str, Any]]:
        """
        Analyze user-facing memories for patterns (READ USER DB).
        """
        patterns: List[Dict[str, Any]] = []

        # Pull from USER DB via SQL directly (fast) but against user_mem.db_path
        user_db = Path(self.user_mem.db_path)
        if not user_db.exists():
            return patterns

        try:
            con = sqlite3.connect(str(user_db))
            cur = con.cursor()
            cur.execute(
                "SELECT ts, text, tags FROM memories WHERE ts > ? ORDER BY ts DESC LIMIT 100",
                (time.time() - (7 * 24 * 60 * 60),),
            )
            memories = cur.fetchall()
            con.close()
        except sqlite3.OperationalError:
            return patterns

        if not memories:
            return patterns

        # Pattern 1: Repeated bi-grams
        query_counts: Dict[str, int] = {}
        for ts, text, tags in memories:
            if not text:
                continue
            words = str(text).lower().split()
            for i in range(len(words) - 1):
                phrase = f"{words[i]} {words[i+1]}"
                query_counts[phrase] = query_counts.get(phrase, 0) + 1

        for phrase, count in query_counts.items():
            if count >= 3:
                patterns.append({
                    "type": "repeated_query",
                    "phrase": phrase,
                    "count": count,
                    "suggestion": f"Create shortcut for '{phrase}'"
                })

        # Pattern 2: Peak activity hour
        hour_actions: Dict[int, int] = {}
        for ts, text, tags in memories:
            try:
                hour = datetime.fromtimestamp(float(ts)).hour
                hour_actions[hour] = hour_actions.get(hour, 0) + 1
            except Exception:
                continue

        if hour_actions:
            peak_hour = max(hour_actions, key=hour_actions.get)
            patterns.append({
                "type": "time_habit",
                "peak_hour": peak_hour,
                "suggestion": f"Most active at {peak_hour}:00 - optimize for this time"
            })

        # Pattern 3: PDF analysis usage
        try:
            con = sqlite3.connect(str(user_db))
            cur = con.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM memories WHERE tags LIKE '%pdf_analysis%' AND ts > ?",
                (time.time() - (30 * 24 * 60 * 60),),
            )
            pdf_count = cur.fetchone()
            con.close()
            if pdf_count and pdf_count[0] and pdf_count[0] > 10:
                patterns.append({
                    "type": "high_pdf_usage",
                    "count": int(pdf_count[0]),
                    "suggestion": "Create automated PDF research pipeline"
                })
        except sqlite3.OperationalError:
            pass

        # Write a lightweight observation into AGENT DB
        if patterns:
            try:
                self.agent_mem.add_observation(
                    category="proactive_patterns",
                    observation="pattern_batch",
                    content=json.dumps(patterns)[:5000],
                )
            except Exception:
                pass

        return patterns

    def analyze_code_quality(self) -> List[Dict[str, Any]]:
        """
        Analyze ELI's own code for improvements (WRITE to AGENT DB)
        """
        improvements: List[Dict[str, Any]] = []

        code_files = [
            self.project_root / "eli/tools/executor_enhanced.py",
            self.project_root / "eli/tools/router_enhanced.py",
            self.project_root / "eli/brain/cognitive_engine.py",
        ]

        for file_path in code_files:
            if not file_path.exists():
                continue

            try:
                content = file_path.read_text()
                lines = content.split("\n")

                # Duplicate lines heuristic
                line_counts: Dict[str, int] = {}
                for line in lines:
                    stripped = line.strip()
                    if len(stripped) > 20:
                        line_counts[stripped] = line_counts.get(stripped, 0) + 1
                duplicates = {k: v for k, v in line_counts.items() if v > 2}
                if duplicates:
                    improvements.append({
                        "file": file_path.name,
                        "type": "duplicate_code",
                        "count": len(duplicates),
                        "priority": 2,
                        "suggestion": f"Found {len(duplicates)} duplicate code blocks - consider refactoring"
                    })

                # Long functions heuristic
                in_function = False
                function_line_count = 0
                function_name = ""

                for line in lines:
                    if line.strip().startswith("def "):
                        if function_line_count > 100:
                            improvements.append({
                                "file": file_path.name,
                                "type": "long_function",
                                "function": function_name,
                                "lines": function_line_count,
                                "priority": 3,
                                "suggestion": f"Function '{function_name}' is {function_line_count} lines - consider splitting"
                            })
                        in_function = True
                        function_line_count = 0
                        function_name = line.strip().split("(")[0].replace("def ", "")
                    elif in_function:
                        function_line_count += 1

                # TODO/FIXME comments
                todos = [line for line in lines if "TODO" in line or "FIXME" in line]
                if todos:
                    improvements.append({
                        "file": file_path.name,
                        "type": "todos",
                        "count": len(todos),
                        "priority": 4,
                        "suggestion": f"Found {len(todos)} TODO/FIXME comments"
                    })

            except Exception as e:
                print(f"[PROACTIVE] Code analysis error for {file_path.name}: {e}")

        # Store improvements summary into AGENT DB
        for item in improvements:
            try:
                self.agent_mem.log_improvement("code_quality", json.dumps(item)[:4000])
            except Exception:
                pass

        return improvements

    def track_error(self, error_type: str, error_message: str, context: str):
        """
        Track recurring errors (WRITE AGENT DB).
        """
        try:
            # Use Memory’s failure logger (dedup + occurrence_count)
            self.agent_mem.log_failure(
                user_input=context or error_message,
                error=f"{error_type}: {error_message}",
                confidence=1.0,
                context={"context": context},
                command=error_type,
            )
        except Exception as e:
            print(f"[PROACTIVE] Error tracking failed: {e}")

    def generate_morning_report(self) -> str:
        """
        Morning report should read:
          - USER DB: conversations/memories
          - AGENT DB: improvements/errors/observations
        """
        hour = datetime.now().hour
        greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"

        user_db = Path(self.user_mem.db_path)
        agent_db = Path(self.agent_mem.db_path)
        window = time.time() - (24 * 60 * 60)

        def fetch_all(db: Path, query: str, params=()):
            try:
                con = sqlite3.connect(str(db))
                cur = con.cursor()
                cur.execute(query, params)
                rows = cur.fetchall()
                con.close()
                return rows
            except sqlite3.OperationalError:
                return []

        def fetch_one(db: Path, query: str, params=()):
            try:
                con = sqlite3.connect(str(db))
                cur = con.cursor()
                cur.execute(query, params)
                row = cur.fetchone()
                con.close()
                return row
            except sqlite3.OperationalError:
                return None

        # USER DB: interactions/convs/memories
        interaction_count = 0
        count_row = fetch_one(user_db, "SELECT COUNT(*) FROM conversations WHERE timestamp > ?", (window,))
        if count_row:
            interaction_count = int(count_row[0])

        recent_convs = fetch_all(
            user_db,
            "SELECT role, content FROM conversations WHERE timestamp > ? ORDER BY timestamp DESC LIMIT 20",
            (window,),
        )
        recent_mems = fetch_all(
            user_db,
            "SELECT text, tags FROM memories ORDER BY ts DESC LIMIT 30",
        )

        # AGENT DB: failures/improvements/observations
        errors = fetch_all(
            agent_db,
            "SELECT user_input, error, occurrence_count FROM failures ORDER BY timestamp DESC LIMIT 5",
        )
        improvements = fetch_all(
            agent_db,
            "SELECT category, detail FROM improvements ORDER BY timestamp DESC LIMIT 5",
        )

        ctx_parts = []
        if recent_convs:
            conv_text = "\n".join([f"{r}: {c[:120]}" for r, c in recent_convs[:10]])
            ctx_parts.append(f"Recent conversations:\n{conv_text}")
        if recent_mems:
            mem_text = "\n".join([f"[{t}] {m[:100]}" for m, t in recent_mems[:15]])
            ctx_parts.append(f"Knowledge base:\n{mem_text}")
        if errors:
            ctx_parts.append("Recent failures (agent):\n" + "\n".join([f"{e[:80]} (x{n})" for _, e, n in errors]))
        if improvements:
            ctx_parts.append("Recent improvements (agent):\n" + "\n".join([f"[{c}] {d[:100]}" for c, d in improvements]))

        context = "\n\n".join(ctx_parts) if ctx_parts else "No recent activity."

        prompt = f"""You are ELI. Generate a specific, data-driven briefing based ONLY on the actual content below.
No generic openers. No filler. Reference specific topics, files, errors, or patterns from the data.
Be direct and analytical. Flag anything that needs attention.
Date: {datetime.now().strftime("%A %B %d %H:%M")} | Interactions last 24h: {interaction_count}

{context}

3-5 specific actionable points. No fluff."""

        try:
            from eli.brain.gguf_inference import chat_completion
            import concurrent.futures as _cf

            with _cf.ThreadPoolExecutor(max_workers=1) as _ex:
                _fut = _ex.submit(
                    chat_completion,
                    prompt,
                    system="You are ELI. Reference actual data only. Write 5 detailed points, "
                           "each 3-4 sentences with full reasoning. No one-liners.",
                    max_tokens=1500,
                    temperature=0.3,
                )
                briefing = _fut.result(timeout=120)

            return f"🌅 {greeting}\n\n{briefing.strip()}"
        except Exception:
            # fallback summary
            lines_out = [f"🌅 {greeting} — {datetime.now().strftime('%A %B %d')}"]
            lines_out.append(f"📊 {interaction_count} interactions in last 24h")
            if errors:
                lines_out.append(f"⚠️  {len(errors)} recent failures — top: {errors[0][1][:60]}")
            if improvements:
                lines_out.append(f"💡 {len(improvements)} recent improvements — top: {improvements[0][1][:60]}")
            if recent_mems:
                lines_out.append(f"🧠 Last memory: {recent_mems[0][0][:80]}")
            return "\n".join(lines_out)

    def run(self):
        """
        Main proactive daemon loop
        """
        self.running = True
        print("[PROACTIVE] Daemon started - continuous learning active")

        last_analysis = time.time()
        last_report = datetime.now().date()

        while self.running:
            try:
                # Run analysis every 10 minutes
                if time.time() - last_analysis > 600:
                    patterns = self.analyze_user_patterns()
                    improvements = self.analyze_code_quality()

                    for pattern in patterns:
                        self.suggestion_queue.put(("pattern", pattern))
                    for improvement in improvements:
                        self.suggestion_queue.put(("improvement", improvement))

                    last_analysis = time.time()

                # Generate morning report once per day between 6-10
                current_date = datetime.now().date()
                current_hour = datetime.now().hour
                if current_date > last_report and 6 <= current_hour <= 10:
                    report = self.generate_morning_report()
                    print(f"\n{report}\n")
                    last_report = current_date

                _maybe_update_persona_from_db()
                time.sleep(60)

            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"[PROACTIVE] Daemon error: {e}")
                time.sleep(60)

        print("[PROACTIVE] Daemon stopped")

    def stop(self):
        self.running = False


# Singleton instance
_daemon = None
_daemon_started = False

def get_daemon() -> ProactiveDaemon:
    global _daemon
    if _daemon is None:
        _daemon = ProactiveDaemon()
    return _daemon

def start_daemon():
    global _daemon_started
    daemon = get_daemon()
    if _daemon_started:
        return daemon
    _daemon_started = True
    thread = threading.Thread(target=daemon.run, daemon=True)
    thread.start()
    return daemon


# _ELI_PERSONA_DB_AUTOUPDATE_HOOK_V1
_LAST_PERSONA_UPDATE = 0.0

def _maybe_update_persona_from_db():
    global _LAST_PERSONA_UPDATE
    now = time.time()
    if now - _LAST_PERSONA_UPDATE < 60.0:
        return
    _LAST_PERSONA_UPDATE = now

    try:
        import importlib.util
        module = "eli.scripts.persona_autoupdate_from_db"
        if importlib.util.find_spec(module) is None:
            return

        env = dict(os.environ)
        # Avoid hardcoded paths; point legacy ELI_DB_PATH to AGENT DB for persona tooling.
        # (If that script should use USER db instead, change agent_db -> user_db here.)
        paths = resolve_db_paths()
        env.setdefault("ELI_DB_PATH", str(paths.agent_db))

        # `-m` works with Python and with the packaged app, whose launcher runs the module the same way
        subprocess.run([sys.executable, "-m", module], env=env, check=False,
                       capture_output=True, text=True)
    except Exception:
        return


def main():
    """eli-daemon: run the background loop in the foreground until stopped."""
    daemon = get_daemon()
    try:
        daemon.run()
    except KeyboardInterrupt:
        daemon.stop()


if __name__ == "__main__":
    daemon = ProactiveDaemon()

    print("\n" + "=" * 70)
    print("Testing Proactive Daemon")
    print("=" * 70 + "\n")

    print("Analyzing user patterns...")
    patterns = daemon.analyze_user_patterns()
    print(f"Found {len(patterns)} patterns:")
    for p in patterns:
        print(f"  • {p}")

    print("\nAnalyzing code quality...")
    improvements = daemon.analyze_code_quality()
    print(f"Found {len(improvements)} improvements:")
    for i in improvements[:5]:
        print(f"  • {i}")

    print("\nGenerating morning report...")
    report = daemon.generate_morning_report()
    print(report)

    print("\n" + "=" * 70)
    print("Proactive Daemon Test Complete")
    print("=" * 70)
