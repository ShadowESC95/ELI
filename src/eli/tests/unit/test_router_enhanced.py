"""Unit tests for eli.tools.router_enhanced."""

import pytest
from eli.tools.router_enhanced import route, route_intent

def test_time_queries():
    assert route("what time is it")["action"] == "TIME"
    assert route("current time")["action"] == "TIME"
    assert route("time")["action"] == "TIME"

def test_date_queries():
    r1 = route("what date")
    assert r1["action"] in ("DATE", "GET_DATE"), f"Got {r1['action']}"
    r2 = route("today's date")
    assert r2["action"] in ("DATE", "GET_DATE"), f"Got {r2['action']}"

def test_open_app():
    r = route("open spotify")
    assert r["action"] == "OPEN_APP"
    assert r["args"]["name"] == "spotify"

def test_open_url():
    r = route("open https://example.com")
    assert r["action"] == "OPEN_URL"
    assert "example.com" in r["args"]["url"]

def test_generate_script():
    r = route("create a python script that prints hello")
    assert r["action"] == "GENERATE_SCRIPT"

def test_fix_file():
    r = route("fix the script in /home/test/script.py")
    assert r["action"] == "FIX_FILE"
    assert "script.py" in r["args"]["path"]

def test_volume():
    assert route("volume up")["action"] == "VOLUME"
    assert route("volume down")["action"] == "VOLUME"
    assert route("set volume to 50")["action"] == "VOLUME"

def test_media_controls():
    assert route("next song")["action"] == "NEXT_MEDIA"
    assert route("previous track")["action"] == "PREVIOUS_MEDIA"
    # "pause media" correctly routes to MEDIA_CONTROL with command=pause
    r = route("pause media")
    assert r["action"] in ("PAUSE_MEDIA", "MEDIA_CONTROL")
    if r["action"] == "MEDIA_CONTROL":
        assert r["args"].get("command") == "pause"

def test_chat_fallback():
    r = route("hello there")
    assert r["action"] == "CHAT"
    assert r["confidence"] == 0.6

def test_route_intent_compat():
    # route_intent should return same shape with args/confidence defaulted
    r = route_intent("time")
    assert r["action"] == "TIME"
    assert "args" in r
    assert "confidence" in r
