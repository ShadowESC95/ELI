# src/eli/brain/self_improvement.py
from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

from eli.brain.memory import get_agent_memory, get_memory, Memory


def _safe_str(x: Any) -> str:
    try:
        return "" if x is None else str(x)
    except Exception:
        return ""


class SelfImprovementEngine:
    """
    Self improvement runs on the AGENT DB by default (separate from user DB).
    In test mode (ELI_MEMORY_DB set), agent DB == user DB automatically.
    """

    def __init__(self, memory: Optional[Memory] = None):
        self.memory: Memory = memory or get_agent_memory()

    # ------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------

    def log_failure(self, input_text: str, error: str = "", confidence: float = 0.0, context: dict = None):
        """Log failure to both failures table and error_tracking table."""
        ctx = context or {}
        # Write to failures table via Memory
        self.memory.log_failure(input_text, error=error, confidence=confidence, context=ctx)
        # Also write to error_tracking for pattern analysis
        now = time.time()
        conn = self.memory._get_connection()
        try:
            # Dedup by (error_type, details)
            error_type = _safe_str(error) or _safe_str(input_text)
            details = json.dumps(ctx) if isinstance(ctx, dict) else str(ctx)
            row = conn.execute(
                "SELECT id, occurrence_count FROM error_tracking WHERE error_type = ? AND details = ?",
                (error_type, details),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE error_tracking SET occurrence_count = occurrence_count + 1, last_seen = ?, timestamp = ? WHERE id = ?",
                    (now, now, row[0]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO error_tracking (error_type, details, timestamp, occurrence_count, first_seen, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (error_type, details, now, 1, now, now),
                )
            conn.commit()
        finally:
            conn.close()

    def log_improvement(self, category: str, description: str, area: str = "runtime", code_before: str = "", code_after: str = ""):
        self.memory.log_improvement(category, description, area=area, code_before=code_before, code_after=code_after)

    def handle_correction(self, original: str, corrected_action: str, corrected_args: dict = None):
        self.memory.log_correction(_safe_str(original), _safe_str(corrected_action))
        return {"ok": True}

    # ------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------

    def analyze_failures(self, limit: int = 50, days=7, min_cluster_size=3) -> List[Dict[str, Any]]:
        conn = self.memory._get_connection()
        try:
            since = time.time() - (days * 86400)
            cur = conn.execute(
                """SELECT user_input, command, error, context, occurrence_count, timestamp
                   FROM failures
                   WHERE timestamp >= ?
                   ORDER BY timestamp DESC LIMIT ?""",
                (since, int(limit)),
            )
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            # Filter by min_cluster_size (occurrence count)
            if min_cluster_size > 1:
                rows = [r for r in rows if (r.get("occurrence_count") or 1) >= min_cluster_size]
            return rows
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def analyze_and_improve(self) -> Dict[str, Any]:
        failures = self.analyze_failures(limit=25, min_cluster_size=1)
        improvements: List[Dict[str, Any]] = []

        for f in failures[:10]:
            ui = _safe_str(f.get("user_input"))
            err = _safe_str(f.get("error"))
            if not ui and not err:
                continue
            improvements.append(
                {"category": "stability", "area": "runtime", "description": f"Investigate failure: {ui} → {err}".strip()}
            )

        for imp in improvements[:5]:
            try:
                self.log_improvement(imp["category"], imp["description"], area=imp.get("area", "runtime"))
            except Exception:
                pass

        return {"improvements": improvements}

    # ------------------------------------------------------------
    # Plugin stub generators (tests call these)
    # ------------------------------------------------------------

    def _generate_plugin_name(self, text):
        return self.generate_plugin_name(text)

    def _generate_plugin_stub(self, name, description="", examples=None):
        return self.generate_plugin_stub(name, description=description, examples=examples)

    def generate_plugin_name(self, idea: str) -> str:
        base = "".join(ch.lower() if ch.isalnum() else "_" for ch in (idea or "plugin").strip())
        base = "_".join([p for p in base.split("_") if p])
        if not base:
            base = "plugin"
        if base[0].isdigit():
            base = "p_" + base
        return base

    def generate_plugin_stub(self, name: str, description: str = "", examples: list = None) -> str:
        mod = self.generate_plugin_name(name)
        desc = description or "Auto-generated plugin"
        examples_str = ""
        if examples:
            examples_str = f"    examples = {examples!r}\n"
        return (
            f"# Auto-generated plugin: {mod}\n"
            "from eli.plugins.base import BasePlugin\n"
            "from eli.brain.memory import get_memory\n\n"
            f"class Plugin(BasePlugin):\n"
            f"    name = '{mod}'\n"
            f"    description = '{desc}'\n"
            f"{examples_str}"
            "\n"
            "    def run(self, args: dict) -> dict:\n"
            "        try:\n"
            f"            # Plugin logic for: {desc}\n"
            "            query = args.get('query', args.get('text', ''))\n"
            "            mem = get_memory()\n"
            "            # Search memory for relevant context\n"
            "            results = mem.recall_memory(query, limit=5) if query else []\n"
            "            context = '; '.join(r.get('text', '') for r in results[:3])\n"
            "            return {\n"
            "                'ok': True,\n"
            "                'content': f'[{self.name}] Processed: {query}. Context: {context or \"none\"}',\n"
            "                'response': f'[{self.name}] Done.',\n"
            "                'results': results,\n"
            "            }\n"
            "        except Exception as e:\n"
            "            return {'ok': False, 'error': str(e), 'content': f'Plugin error: {e}'}\n"
        )

    # ------------------------------------------------------------
    # Loop
    # ------------------------------------------------------------

    def start_self_improvement_loop(self, interval_hours: int = 24):
        def loop():
            while True:
                time.sleep(interval_hours * 3600)
                try:
                    self.analyze_and_improve()
                except Exception:
                    pass

        threading.Thread(target=loop, daemon=True).start()


_self_engine: Optional[SelfImprovementEngine] = None


def get_self_improvement() -> SelfImprovementEngine:
    global _self_engine
    if _self_engine is None:
        _self_engine = SelfImprovementEngine()
    return _self_engine
