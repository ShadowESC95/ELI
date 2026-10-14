"""
Habit learning – monitors user actions, detects patterns, and manages automation rules.
Uses unified memory.
"""

import json
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from .memory import get_memory

def log_event(event_type: str, data: dict):
    """Log an event for habit analysis."""
    mem = get_memory()
    mem.log_habit_event(event_type, data)

def detect_habits(days: int = 14, min_occurrences: int = 3):
    """
    Analyze app_launch events to detect time‑based habits.
    Creates or updates habit rules when patterns are found.
    """
    mem = get_memory()
    events = mem.get_habit_events(event_type="app_launch", days=days)

    # Group by (app, hour, minute)
    patterns = defaultdict(list)
    for e in events:
        ts = e["timestamp"]
        dt = datetime.fromtimestamp(ts)
        app = e["details"].get("app")
        if not app:
            continue
        cmd = e["details"].get("cmd")
        hour = dt.hour
        minute = dt.minute
        # Round minute to nearest 5 minutes for grouping
        minute_rounded = (minute // 5) * 5
        key = (app, hour, minute_rounded)
        patterns[key].append({
            "timestamp": ts,
            "command": cmd if isinstance(cmd, str) else " ".join(cmd) if isinstance(cmd, list) else str(cmd)
        })

    # For each pattern, check if it meets the threshold
    existing_rules = mem.get_habit_rules(enabled_only=False)
    for (app, hour, minute), occurrences in patterns.items():
        if len(occurrences) >= min_occurrences:
            # Use the most frequent command
            from collections import Counter
            cmd_counter = Counter(o["command"] for o in occurrences)
            command = cmd_counter.most_common(1)[0][0]
            name = f"Open {app} at {hour:02d}:{minute:02d}"

            # Check if a similar rule already exists
            exists = False
            for rule in existing_rules:
                if rule.get("name") == name and rule.get("hour") == hour and rule.get("minute") == minute:
                    exists = True
                    # Optionally update the command if it changed
                    if rule.get("command") != command:
                        mem.update_habit_rule(rule["id"], command=command)
                    break
            if not exists:
                mem.add_habit_rule(name, command, hour, minute, days=None)  # daily
                print(f"[HABIT] New rule created: {name}")

def schedule_detection_loop(interval_hours: int = 12):
    """Run habit detection periodically."""
    import threading
    def loop():
        while True:
            time.sleep(interval_hours * 3600)
            detect_habits()
    threading.Thread(target=loop, daemon=True).start()
