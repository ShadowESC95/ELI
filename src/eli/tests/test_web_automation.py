#!/usr/bin/env python3
"""
Test ELI's Web Automation plugin – sync version.
"""

import sys
import time
import pytest
sys.path.insert(0, ".")

pytest.importorskip("playwright", reason="the web automation plugin needs Playwright (pip install playwright)")

from eli.plugins.base import load_plugins
from eli.brain import config

def test_web():
    print("\n🌐 Testing Web Automation Plugin (sync)...")
    load_plugins()
    
    from eli.plugins.web_automation import WebAutomationPlugin
    plugin = WebAutomationPlugin()
    
    # Test navigation
    print("   📍 Navigate to example.com")
    res = plugin.navigate({"url": "https://example.com"})
    if res.get("ok"):
        print(f"      ✅ {res.get('content')}")
    else:
        print(f"      ❌ {res.get('error')}")
    
    # Test screenshot
    print("   📸 Take screenshot")
    res = plugin.screenshot({})
    if res.get("ok"):
        print(f"      ✅ {res.get('content')}")
    else:
        print(f"      ❌ {res.get('error')}")
    
    # Test extract text
    print("   📄 Extract page text")
    res = plugin.extract_text({})
    if res.get("ok"):
        preview = res.get('content', '')[:100].replace('\n', ' ')
        print(f"      ✅ Preview: {preview}...")
    else:
        print(f"      ❌ {res.get('error')}")
    
    # Test search (headless)
    config.set_web_headless(True)
    print("   🔍 Google search for 'playwright'")
    res = plugin.search({"engine": "google", "query": "playwright"})
    if res.get("ok"):
        print(f"      ✅ {res.get('content')}")
    else:
        print(f"      ❌ {res.get('error')}")
    
    # Close browser
    plugin.close({})
    print("   🚪 Browser closed.")

if __name__ == "__main__":
    print("="*60)
    print("🌐 ELI Web Automation Test (Sync)")
    print("="*60)
    test_web()
    print("\n✅ Web automation test complete.")
