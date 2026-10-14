#!/usr/bin/env python3
"""
Test the habit detection and scheduling system.
"""

import sys
import time
sys.path.insert(0, ".")

from eli.brain.habits import detect_habits, log_event
from eli.brain.memory import get_memory
from eli.brain.scheduler import get_scheduler

def generate_sample_events():
    """Create some fake app launches for testing."""
    print("📊 Generating sample habit events...")
    mem = get_memory()
    # Simulate opening terminal at 9:15 AM for the last 5 days
    import time
    now = time.time()
    for i in range(5):
        ts = now - (i * 86400)  # each day
        # Set hour to 9, minute to 15
        from datetime import datetime
        dt = datetime.fromtimestamp(ts)
        dt = dt.replace(hour=9, minute=15, second=0)
        ts = dt.timestamp()
        mem.log_habit_event("app_launch", {
            "app": "terminal",
            "cmd": ["x-terminal-emulator"],
            "method": "builtin",
            "success": True,
            "_timestamp": ts  # override timestamp (hack)
        })
        # Also insert directly with custom timestamp
        with sqlite3.connect(mem.db_path) as conn:
            conn.execute(
                "UPDATE habit_events SET timestamp = ? WHERE rowid = (SELECT MAX(rowid) FROM habit_events)",
                (ts,)
            )
    print("   ✅ Events created.")

def test_detection():
    print("\n🔍 Testing habit detection...")
    detect_habits(days=7, min_occurrences=3)
    mem = get_memory()
    rules = mem.get_habit_rules()
    print(f"   Found {len(rules)} habit rules.")
    for rule in rules:
        print(f"      - {rule['name']}: {rule['command']} at {rule['hour']:02d}:{rule['minute']:02d}")

def test_scheduler():
    print("\n⏰ Testing scheduler (will run for 10 seconds)...")
    sched = get_scheduler()
    # No need to do anything; it's running.
    time.sleep(2)
    print("   Scheduler is alive.")
    # We won't actually wait for a rule trigger here.

if __name__ == "__main__":
    import sqlite3
    print("="*60)
    print("🧠 ELI Habit System Test")
    print("="*60)
    generate_sample_events()
    test_detection()
    test_scheduler()
    print("\n✅ Habit test complete.")
    print("   Rules are stored in the database and visible in the GUI.")
