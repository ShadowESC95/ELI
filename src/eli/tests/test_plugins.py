#!/usr/bin/env python3
"""
Test the ELI plugin system.
"""

import sys
sys.path.insert(0, ".")

from eli.plugins.base import load_plugins, get_plugin
from eli.brain import config

def test_weather():
    print("\n🌤️  Testing Weather Plugin...")
    plugin = get_plugin("weather")
    if not plugin:
        print("   ❌ Weather plugin not loaded.")
        return

    # Check for API key
    key = config.get("openweather_api_key")
    if not key:
        print("   ⚠️  No OpenWeatherMap API key set.")
        print("      Set it with: python3 -c \"from eli.brain import config; config.set('openweather_api_key', 'YOUR_KEY')\"")
        return

    result = plugin.execute("current", {"city": "London"})
    if result.get("ok"):
        print(f"   ✅ Weather in London: {result.get('content')}")
    else:
        print(f"   ❌ Weather failed: {result.get('error')}")

def test_calendar():
    print("\n📅  Testing Calendar Plugin...")
    plugin = get_plugin("calendar")
    if not plugin:
        print("   ❌ Calendar plugin not loaded.")
        return

    # Test list
    result = plugin.execute("list", {"days": 7})
    if result.get("ok"):
        print(f"   ✅ Calendar list:\n{result.get('content')}")
    else:
        print(f"   ❌ Calendar list failed: {result.get('error')}")

    # Test add (optional)
    # result = plugin.execute("add", {"summary": "Test event", "date": "2026-02-12", "time": "14:00"})
    # print(result)

def test_smart_home():
    print("\n🏠  Testing Smart Home Plugin (placeholder)...")
    plugin = get_plugin("smart_home")
    if not plugin:
        print("   ❌ Smart Home plugin not loaded.")
        return
    result = plugin.execute("on", {"device": "living room light"})
    print(f"   {result.get('content')}")

if __name__ == "__main__":
    print("="*60)
    print("🔌 ELI Plugin System Test")
    print("="*60)
    load_plugins()
    test_weather()
    test_calendar()
    test_smart_home()
    print("\n✅ Plugin tests complete.")
