#!/usr/bin/env python3
"""
ELI Cognitive Diagnostic – Checks core modules, memory, proactive feed, and integration.
"""

import os
import sys
import importlib
import time
import sqlite3
from pathlib import Path

# Add project root to path
root_dir = Path(__file__).parent
sys.path.insert(0, str(root_dir))

# ----------------------------------------------------------------------
# Color codes
# ----------------------------------------------------------------------
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
CYAN = '\033[96m'
BOLD = '\033[1m'
END = '\033[0m'

def print_header(text):
    print(f"\n{BOLD}{CYAN}{'='*60}{END}")
    print(f"{BOLD}{CYAN}{text}{END}")
    print(f"{BOLD}{CYAN}{'='*60}{END}")

def print_success(text):
    print(f"{GREEN}✅ {text}{END}")

def print_warning(text):
    print(f"{YELLOW}⚠️  {text}{END}")

def print_error(text):
    print(f"{RED}❌ {text}{END}")

def print_info(text):
    print(f"ℹ️  {text}")

# ----------------------------------------------------------------------
# 1. COGNITIVE CORE MODULES
# ----------------------------------------------------------------------
print_header("🔍 COGNITIVE CORE MODULES")

modules = [
    ("eli.brain.memory", "get_memory"),
    ("eli.brain.system_index", "SystemIndex"),
    ("eli.brain.reflection", "reflect_on_memories"),
    ("eli.brain.habits", "detect_habits"),
    ("eli.brain.context_builder", "build_context"),
    ("eli.brain.agent_loop", None),
    ("eli.brain.eli_agent", "ELIAgent"),
    ("eli.proactive.proactive_daemon", "proactive_status"),
    ("eli.tools.executor_enhanced", "execute"),
    ("eli.tools.router_enhanced", "route"),
]

for module_name, attr in modules:
    try:
        mod = importlib.import_module(module_name)
        if attr:
            if hasattr(mod, attr):
                print_success(f"{module_name:<35} found at {mod.__file__}, has '{attr}'")
            else:
                print_error(f"{module_name:<35} found but missing '{attr}'")
        else:
            print_success(f"{module_name:<35} found at {mod.__file__}")
    except Exception as e:
        print_error(f"{module_name:<35} import failed: {e}")

# ----------------------------------------------------------------------
# 2. MEMORY BACKEND USAGE
# ----------------------------------------------------------------------
print_header("🔍 MEMORY BACKEND USAGE")

# Check executor_enhanced for memory usage
try:
    from eli.tools import executor_enhanced
    src = Path(executor_enhanced.__file__).read_text()
    if '.eli_app_map.json' in src:
        print_success("executor_enhanced uses local JSONL memory")
    if 'memory_adapter' in src:
        print_success("executor_enhanced uses SQLite memory_adapter")
    if 'memory_db' in src:
        print_success("executor_enhanced uses memory_db")
    if 'system_index' in src:
        print_success("executor_enhanced queries system index")
except Exception as e:
    print_error(f"Could not analyze executor_enhanced: {e}")

# ----------------------------------------------------------------------
# 3. SELF‑LEARNING APP MAP
# ----------------------------------------------------------------------
print_header("🔍 SELF‑LEARNING APP MAP")

try:
    from eli.brain.memory import get_memory
    mem = get_memory()
    app_map = mem._load_app_map()
    print_success(f"App map has {len(app_map)} entries")
    sample = list(app_map.items())[:2]
    print(f"   Sample: {sample}")
except Exception as e:
    print_error(f"Could not read app map: {e}")

# ----------------------------------------------------------------------
# 4. REFLECTION & HABITS INTEGRATION
# ----------------------------------------------------------------------
print_header("🔍 REFLECTION & HABITS INTEGRATION")

# Search for calls to log_event and detect_habits
logs = 0
try:
    for pyfile in Path("eli").rglob("*.py"):
        if "__pycache__" in str(pyfile):
            continue
        text = pyfile.read_text()
        if "log_event" in text:
            print_success(f"Found call to log_event in {pyfile}")
            logs += 1
        if "detect_habits" in text:
            print_success(f"Found call to detect_habits in {pyfile}")
except Exception as e:
    print_error(f"Error scanning files: {e}")

# ----------------------------------------------------------------------
# 5. PROACTIVE COGNITION FEED
# ----------------------------------------------------------------------
print_header("🔍 PROACTIVE COGNITION FEED")

proactive_ok = False
try:
    from eli.brain.cognitive_engine import get_engine
    from eli.brain.memory import get_memory
    engine = get_engine()
    memory = get_memory()
    
    if hasattr(engine, 'proactive_daemon') and engine.proactive_daemon:
        status = engine.proactive_daemon.get_status()
        if status.get('running', False):
            # Daemon is running – check for observations in last 60 seconds
            try:
                db_path = memory.db_path
                with sqlite3.connect(db_path) as conn:
                    cur = conn.execute(
                        "SELECT COUNT(*) FROM observations WHERE timestamp > ?",
                        (time.time() - 60,)
                    )
                    count = cur.fetchone()[0]
                    if count > 0:
                        proactive_ok = True
                        print_success(f"Proactive daemon is running and sent {count} observation(s) in the last minute")
                    else:
                        print_warning("Proactive daemon is running but no observations in the last minute")
            except Exception as e:
                print_warning(f"Could not verify observations: {e}")
        else:
            print_info("Proactive daemon is present but not running")
    else:
        print_info("Proactive daemon not loaded")
except Exception as e:
    print_error(f"Could not analyze proactive daemon: {e}")

if not proactive_ok:
    # Still show a neutral message instead of a scary warning
    print_info("Proactive feed check: no recent observations (may be normal if just started)")

# ----------------------------------------------------------------------
# 6. GUI COGNITIVE INTEGRATION
# ----------------------------------------------------------------------
print_header("🔍 GUI COGNITIVE INTEGRATION")

gui_files = list(Path("eli/gui").glob("*.py"))
cognitive_used = False
for gui in gui_files:
    if "cognitive_engine" in gui.read_text():
        cognitive_used = True
        print_success(f"GUI uses cognitive engine ({gui.name})")
        break
if not cognitive_used:
    print_warning("No GUI file imports cognitive_engine")

# ----------------------------------------------------------------------
# 7. DIAGNOSTIC COMPLETE
# ----------------------------------------------------------------------
print_header("🔍 DIAGNOSTIC COMPLETE")
print_info("Review the output above. Red ❌ indicates missing components.")
print_info("Yellow ⚠️ indicates components exist but are not wired.")
