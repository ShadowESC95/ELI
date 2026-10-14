
# tts_router.py — per-response TTS control

def maybe_speak(response, tts_engine, enabled=False):
    if enabled and response.get("tts_available"):
        tts_engine.speak(response.get("full_text", ""))
