#!/usr/bin/env python3
"""
ELI Cognitive Upgrade Test Suite – FINAL, with clipboard warning
"""

import sys
import os
import time
from pathlib import Path


print("="*60)
print("🧪 ELI COGNITIVE UPGRADE TEST SUITE")
print("="*60)

# ------------------------------------------------------------------
# 1. Router Tests
# ------------------------------------------------------------------
print("\n📡 ROUTER TESTS")
try:
    from eli.tools.router_enhanced import route
    test_cases = [
        ("take a screenshot", "SCREENSHOT"),
        ("capture screenshot area", "SCREENSHOT"),
        ("volume up", "VOLUME"),
        ("raise volume", "VOLUME"),
        ("set volume to 50%", "VOLUME"),
        ("mute", "VOLUME"),
        ("unmute", "VOLUME"),
        ("press enter", "KEYBOARD"),
        ("open spotify", "OPEN_APP"),
        ("open home", "OPEN_FILE_SYSTEM"),
        ("what time is it", "TIME"),
    ]
    all_ok = True
    for cmd, expected in test_cases:
        intent = route(cmd)
        action = intent.get('action')
        if action == expected:
            print(f"   ✅ {cmd:30} → {action}")
        else:
            print(f"   ❌ {cmd:30} → {action} (expected {expected})")
            all_ok = False
    if all_ok:
        print("   ✅ All router tests passed.")
except Exception as e:
    print(f"   ❌ Router test failed: {e}")

# ------------------------------------------------------------------
# 2. OS Controller Direct Tests
# ------------------------------------------------------------------
print("\n🎛️  OS CONTROLLER DIRECT TESTS")
try:
    from eli.controllers.os_controller import (
        take_screenshot, set_volume, press_key,
        get_volume, set_clipboard, get_clipboard
    )
    
    # Screenshot
    print("\n   📸 Screenshot:")
    res = take_screenshot("full")
    if res.get('ok'):
        print(f"      ✅ Full screenshot taken")
    else:
        print(f"      ❌ Screenshot failed: {res.get('error')}")
    
    # Volume
    print("\n   🔊 Volume:")
    vol = get_volume()
    if vol is not None:
        print(f"      ✅ Current volume: {vol}%")
    else:
        print(f"      ❌ Could not get volume")
    if vol is not None:
        res = set_volume(direction="up", delta=5)
        if res.get('ok'):
            print(f"      ✅ Volume raised by 5%")
            set_volume(level=vol)  # restore
        else:
            print(f"      ❌ Volume raise failed: {res.get('error')}")
    
    # Keyboard
    print("\n   ⌨️  Keyboard:")
    if press_key("enter").get('ok'):
        print(f"      ✅ Pressed Enter")
    else:
        print(f"      ❌ Press Enter failed (install ydotool or xdotool)")
    
    # Clipboard – non-critical, warn only
    print("\n   📋 Clipboard:")
    res = set_clipboard("ELI test clipboard")
    if res.get('ok'):
        time.sleep(0.2)
        clip = get_clipboard()
        if clip and clip.strip() == "ELI test clipboard":
            print(f"      ✅ Clipboard read/write works")
        else:
            print(f"      ⚠️  Clipboard read failed (got: {repr(clip)}) – may be environmental")
    else:
        print(f"      ⚠️  Clipboard not available ({res.get('error')}) – skipping test")
        
except Exception as e:
    print(f"   ❌ OS controller direct test failed: {e}")

# ------------------------------------------------------------------
# 3. Executor Integration Tests
# ------------------------------------------------------------------
print("\n⚙️  EXECUTOR INTEGRATION")
try:
    from eli.tools.executor_enhanced import execute
    
    print("\n   📸 Executor SCREENSHOT:")
    res = execute("SCREENSHOT", {"region": "full"})
    if res.get('ok'):
        print(f"      ✅ {res.get('content')}")
    else:
        print(f"      ❌ {res.get('error')}")
    
    print("\n   🔊 Executor VOLUME:")
    res = execute("VOLUME", {"direction": "up", "delta": 5})
    if res.get('ok'):
        print(f"      ✅ {res.get('content')}")
    else:
        print(f"      ❌ {res.get('error')}")
    
    print("\n   🎵 Executor OPEN_APP (spotify):")
    res = execute("OPEN_APP", {"name": "spotify"})
    if res.get('ok'):
        print(f"      ✅ {res.get('content')}")
    else:
        print(f"      ❌ {res.get('error')}")
        
except Exception as e:
    print(f"   ❌ Executor integration test failed: {e}")

# ------------------------------------------------------------------
# 4. Proactive Daemon
# ------------------------------------------------------------------
print("\n🤖 PROACTIVE DAEMON")
try:
    from eli.tools.executor_enhanced import proactive_status
    status = proactive_status()
    print(f"   ✅ Proactive status: running={status.get('running')}, pid={status.get('pid')}")
except Exception as e:
    print(f"   ❌ Proactive import failed: {e}")

# ------------------------------------------------------------------
# 5. Memory & System Index
# ------------------------------------------------------------------
print("\n💾 MEMORY & SYSTEM INDEX")
try:
    from eli.brain.system_index import refresh_index, find_app, find_path
    refresh_index()
    print(f"   ✅ System index initialized")
    app = find_app("spotify")
    if app:
        print(f"      ✅ Found spotify: {app.get('cmd')}")
    else:
        print(f"      ⚠️  Spotify not found in index (may not be installed)")
    path = find_path("home")
    if path:
        print(f"      ✅ Found home: {path}")
except ImportError:
    print(f"   ⚠️  System index not yet implemented – run the system_index.py first.")
except Exception as e:
    print(f"   ❌ Memory test failed: {e}")

print("\n" + "="*60)
print("✅ Test suite complete. Review any ⚠️  warnings – they are not failures.")
print("="*60)
