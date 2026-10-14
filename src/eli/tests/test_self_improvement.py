#!/usr/bin/env python3
"""
Test ELI's Self‑Improvement Engine.
"""

import sys
import time
sys.path.insert(0, ".")

from eli.brain.self_improvement import get_self_improvement
from eli.brain.memory import get_memory

def generate_sample_failures():
    mem = get_memory()
    mem.init_self_improvement_tables()
    
    # Simulate repeated failures for a missing capability
    failures = [
        "convert mp4 to gif",
        "convert video file to gif",
        "turn this video into a gif",
        "make a gif from my mp4",
        "create animated gif from video"
    ]
    for cmd in failures:
        mem.log_failure(cmd, error="No plugin for video conversion", confidence=0.3)
    print("✅ Sample failures logged.")

def test_analysis():
    si = get_self_improvement()
    proposals = si.analyze_failures(days=1, min_cluster_size=3)
    print(f"🔍 Analysis found {len(proposals)} proposals.")
    for name, desc, ex in proposals:
        print(f"   - {name}: {desc}")
        print(f"     Example: {ex[0]}")
    return proposals

if __name__ == "__main__":
    print("="*60)
    print("🧬 ELI Self‑Improvement Test")
    print("="*60)
    generate_sample_failures()
    proposals = test_analysis()
    if proposals:
        # Generate the first plugin
        pid = get_memory().get_pending_proposals()[0]['id']
        si = get_self_improvement()
        path = si.generate_plugin_from_proposal(pid)
        print(f"✅ Generated plugin: {path}")
        print("   Activate with: si.activate_plugin('convert_video_plugin')")
    print("\n✅ Self‑improvement test complete.")
