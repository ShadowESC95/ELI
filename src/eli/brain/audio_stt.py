# src/eli/tools/audio_stt.py
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional, Iterable

import speech_recognition as sr

from eli.tools.audio_stt import transcribe


@dataclass
class AudioSTTConfig:
    # Wake words
    wake_words: tuple[str, ...] = ("eli", "computer")

    # How long we wait AFTER wake for user to start speaking
    command_start_timeout_s: float = 8.0

    # Maximum length of a single command utterance (safety cap)
    command_phrase_time_limit_s: float = 20.0

    # The key requirement:
    # command finalizes only after this much silence after speech ends.
    end_silence_s: float = 2.0

    # Ambient noise calibration
    calibrate_seconds: float = 1.0

    # Tuning
    dynamic_energy: bool = True
    energy_threshold: Optional[int] = None  # None -> let SR calibrate

    # Debug logging
    debug: bool = True


# Global state
_recognizer = sr.Recognizer()
_microphone: Optional[sr.Microphone] = None
_listen_thread: Optional[threading.Thread] = None
_stop_flag = threading.Event()

_callback: Optional[Callable[[str], None]] = None

_cfg = AudioSTTConfig(
    wake_words=tuple(
        w.strip().lower()
        for w in (os.getenv("ELI_WAKE_WORDS", "eli,computer").split(","))
        if w.strip()
    )
)

# Allow env overrides without editing code
_cfg.command_start_timeout_s = float(os.getenv("ELI_WAKE_CMD_START_TIMEOUT", str(_cfg.command_start_timeout_s)))
_cfg.command_phrase_time_limit_s = float(os.getenv("ELI_WAKE_CMD_PHRASE_LIMIT", str(_cfg.command_phrase_time_limit_s)))
_cfg.end_silence_s = float(os.getenv("ELI_WAKE_END_SILENCE", str(_cfg.end_silence_s)))
_cfg.debug = os.getenv("ELI_AUDIO_DEBUG", "1").strip() not in ("0", "false", "False", "no", "NO")


def _log(msg: str) -> None:
    if _cfg.debug:
        print(msg, flush=True)


def _ensure_mic() -> sr.Microphone:
    global _microphone
    if _microphone is None:
        _microphone = sr.Microphone()
    return _microphone


def _calibrate(rec: sr.Recognizer, mic: sr.Microphone) -> None:
    _log("[AUDIO] Calibrating microphone for ambient noise...")
    with mic as source:
        if _cfg.dynamic_energy:
            rec.dynamic_energy_threshold = True
        else:
            rec.dynamic_energy_threshold = False
        if _cfg.energy_threshold is not None:
            rec.energy_threshold = int(_cfg.energy_threshold)
        rec.adjust_for_ambient_noise(source, duration=_cfg.calibrate_seconds)
    _log("[AUDIO] Microphone calibration complete")


def _normalize_text(t: str) -> str:
    return (t or "").strip()


def _contains_wake(text: str) -> bool:
    low = (text or "").lower()
    return any(w in low.split() or low.startswith(w + " ") or low.endswith(" " + w) or low == w for w in _cfg.wake_words)


def _strip_wake(text: str) -> str:
    """Remove wake word token if present (best-effort)."""
    low = (text or "").strip()
    toks = low.split()
    if not toks:
        return ""
    # remove leading wake word
    if toks[0].lower() in _cfg.wake_words:
        return " ".join(toks[1:]).strip()
    # also remove 'eli,' / 'eli:' patterns
    for w in _cfg.wake_words:
        if low.lower().startswith(w + ","):
            return low[len(w) + 1 :].strip()
        if low.lower().startswith(w + ":"):
            return low[len(w) + 1 :].strip()
    return low.strip()


def listen_for_command(rec: sr.Recognizer, mic: sr.Microphone) -> Optional[str]:
    """
    After wake word, capture a single command.

    Requirement:
    - The "timer" starts after the user stops speaking.
    - We finalize only after ~2s silence (pause_threshold).
    """
    # IMPORTANT: these thresholds control end-of-speech, not a fixed timer.
    rec.pause_threshold = float(_cfg.end_silence_s)      # <-- this is your requirement
    rec.phrase_threshold = 0.3                           # minimal speech before we consider phrase started
    rec.non_speaking_duration = 0.5                      # how much silence we keep around speech

    with mic as source:
        _log("🎧 [AUDIO] Wake-only detected. Listening for command...")
        try:
            audio = rec.listen(
                source,
                timeout=float(_cfg.command_start_timeout_s),
                phrase_time_limit=float(_cfg.command_phrase_time_limit_s),
            )
        except sr.WaitTimeoutError:
            _log("[AUDIO] No command started within timeout window.")
            return None

    try:
        cmd = transcribe(audio)
        cmd = _normalize_text(cmd)
        return cmd if cmd else None
    except sr.UnknownValueError:
        _log("[AUDIO] Could not understand audio")
        return None
    except Exception as e:
        _log(f"[AUDIO] STT error: {e!r}")
        return None


def _listen_loop() -> None:
    rec = _recognizer
    mic = _ensure_mic()

    _calibrate(rec, mic)
    _log("[AUDIO] Microphone ready")
    _log("👂 [AUDIO] Listening... (wake word + command, or wake then command)")

    while not _stop_flag.is_set():
        # Use shorter pause threshold for wake detection so it’s snappy
        rec.pause_threshold = 0.8
        rec.phrase_threshold = 0.3
        rec.non_speaking_duration = 0.3

        with mic as source:
            try:
                audio = rec.listen(source, timeout=1.0, phrase_time_limit=4.0)
            except sr.WaitTimeoutError:
                continue

        try:
            text = transcribe(audio)
            text = _normalize_text(text)
            if not text:
                continue
            _log(f"👂 [AUDIO] Heard: '{text}'")

            # If wake+command in one utterance:
            if _contains_wake(text):
                _log(f"🔊 [AUDIO] Wake word detected")
                cmd_inline = _strip_wake(text)
                if cmd_inline:
                    _log(f"🎤 [AUDIO] Command (inline): '{cmd_inline}'")
                    if _callback:
                        _log("   ↳ CALLBACK IS SET, invoking now")
                        _callback(cmd_inline)
                    continue

                # Wake-only: capture command with the correct end-of-speech behavior
                cmd = listen_for_command(rec, mic)
                if cmd:
                    _log(f"🎤 [AUDIO] Command: '{cmd}'")
                    _log("   ↳ Sending to ELI for processing...")
                    if _callback:
                        _log("   ↳ CALLBACK IS SET, invoking now")
                        _callback(cmd)
                continue

            # Optional: if no wake word required, you can forward all speech
            # but you probably don't want that.
        except sr.UnknownValueError:
            _log("[AUDIO] Could not understand audio")
        except Exception as e:
            _log(f"[AUDIO] Listen loop error: {e!r}")

    _log("[AUDIO] Stopped listening")


def start_audio_listening(callback: Callable[[str], None]) -> None:
    """Start background listener thread; callback receives transcript strings."""
    global _listen_thread, _callback
    _callback = callback
    if _listen_thread and _listen_thread.is_alive():
        return
    _stop_flag.clear()
    _listen_thread = threading.Thread(target=_listen_loop, daemon=True)
    _listen_thread.start()
    _log("[AUDIO] Started listening for voice commands")


def stop_audio_listening() -> None:
    """Stop background listener thread."""
    _stop_flag.set()
    _log("[AUDIO] Stopped listening")
