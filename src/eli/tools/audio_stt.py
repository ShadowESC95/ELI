"""
ELI Audio STT (backward-compatible) + volume ducking with exact restore.

Exports required by GUI:
- get_audio_stt()
- start_audio_listening(callback=None)
- stop_audio_listening()
- listen_for_command(timeout=5)

Behavior:
- Listens continuously (wake-word optional; disabled by default)
- If wake word detected with no inline command -> short follow-up command window
- Ducks system volume during command capture, restores to prior value (not hard-coded)

FIXED:
- Uses environment variable ELI_MIC_DEVICE_INDEX to select specific microphone
- Silences ALSA/JACK flood by not probing every possible device
- Added debug prints to confirm callback invocation
"""

import re
import time
import queue
import threading
import subprocess
import speech_recognition as sr
import os


# ----------------------------------------------------------------------
# Speech to text on this machine (Whisper through faster-whisper); recordings never leave it.
# ELI_WHISPER (model size, default base), ELI_WHISPER_DEVICE (cpu/cuda), ELI_WHISPER_LANG (default en; empty = detect)
# ----------------------------------------------------------------------
_whisper = None
_whisper_lock = threading.Lock()


def _whisper_model():
    global _whisper
    with _whisper_lock:
        if _whisper is None:
            from faster_whisper import WhisperModel
            _whisper = WhisperModel(
                os.environ.get("ELI_WHISPER", "base"),
                device=os.environ.get("ELI_WHISPER_DEVICE", "cpu"),
                compute_type=os.environ.get("ELI_WHISPER_COMPUTE", "int8"),
            )
        return _whisper


def transcribe(audio: sr.AudioData) -> str:
    """The words in a recording. Raises sr.UnknownValueError when nothing was said and
    sr.RequestError when the speech model cannot load, as SpeechRecognition's recognizers do."""
    import numpy as np
    try:
        model = _whisper_model()
    except Exception as e:
        raise sr.RequestError(f"local speech model unavailable: {e}") from e
    pcm = audio.get_raw_data(convert_rate=16000, convert_width=2)
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    segments, _info = model.transcribe(samples, language=os.environ.get("ELI_WHISPER_LANG", "en") or None,
                                       vad_filter=True)
    text = " ".join(seg.text.strip() for seg in segments).strip()
    if not text:
        raise sr.UnknownValueError()
    return text

# ----------------------------------------------------------------------
# Routing helper (fixes VOICE commands being sent to CHAT)
# ----------------------------------------------------------------------

def process_transcript(text: str):
    """Route a transcript through router_enhanced and execute it.

    Use this from GUI/voice handlers so single-word commands like
    'play', 'pause', 'resume' are executed as MEDIA_CONTROL rather than
    being sent to LLM chat.
    """
    try:
        from eli.tools.router_enhanced import route
        from eli.tools.executor_enhanced import execute
        intent = route(text)
        return execute(intent.get('action') or 'CHAT', intent.get('args') or {'message': text})
    except Exception as e:
        return {'ok': False, 'action': 'VOICE_ROUTE', 'error': str(e), 'content': 'Voice routing failed', 'response': 'Voice routing failed'}



# ----------------------------
# Wake words & tuning (optional mode)
# ----------------------------
WAKE_WORDS = [
    "hey eli", "hey computer", "eli", "computer",
]

DUCK_LEVEL = "15%"          # volume during command window
RESTORE_DELAY_S = 0.25      # allow PipeWire routing/callback audio to settle

MAIN_TIMEOUT = 15.0       # max time to wait for speech to start
MAIN_PHRASE_LIMIT = 30.0  # max phrase length (safety limit)

FOLLOWUP_TIMEOUT = 8.0    # time to wait for follow-up speech
FOLLOWUP_PHRASE_LIMIT = 30.0  # max follow-up length

WAKE_DEBOUNCE_S = 0.7
ELI_DISABLE_WAKE_WORD = os.environ.get('ELI_DISABLE_WAKE_WORD', '0').lower() in ('1','true','yes','on')


def _cleanup(text: str) -> str:
    t = (text or "").strip().lower()
    t = re.sub(r'^[,\s\-:;.]+', '', t).strip()

    # strip common leading fluff
    prefixes = ["comma", "please", "could you", "can you", "would you", "will you", "hey", "okay", "ok"]
    for p in prefixes:
        if t.startswith(p + " "):
            t = t[len(p) + 1:].strip()
    return re.sub(r'^[,\s\-:;.]+', '', t).strip()


# ----------------------------
# Volume control helpers
# ----------------------------
_VOL_RE = re.compile(r"(\d+)%")

def _get_current_volume() -> str | None:
    """Return current @DEFAULT_SINK@ volume as 'NN%'."""
    try:
        out = subprocess.check_output(
            ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
            stderr=subprocess.DEVNULL,
            text=True
        )
        m = _VOL_RE.search(out)
        if m:
            return f"{m.group(1)}%"
    except Exception:
        pass
    return None

def _set_volume(level: str) -> None:
    try:
        subprocess.Popen(
            ["pactl", "set-sink-volume", "@DEFAULT_SINK@", str(level)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception:
        pass

def _duck(prev_vol: str | None) -> None:
    _set_volume(DUCK_LEVEL)

def _restore(prev_vol: str | None) -> None:
    if prev_vol:
        _set_volume(prev_vol)

def _restore_later(prev_vol: str | None, delay_s: float = RESTORE_DELAY_S) -> None:
    threading.Timer(delay_s, _restore, args=(prev_vol,)).start()


# ----------------------------
# STT Engine
# ----------------------------
class ELIAudioSTT:
    def __init__(self):
        self.recognizer = sr.Recognizer()

        # ----- FIX: Use environment variable to select microphone device -----
        device_index = os.environ.get("ELI_MIC_DEVICE_INDEX")
        if device_index is not None:
            try:
                self.microphone = sr.Microphone(device_index=int(device_index))
                print(f"[AUDIO] Using microphone device index {device_index}")
            except Exception as e:
                print(f"[AUDIO] Failed to set device index {device_index}: {e}, falling back to default")
                self.microphone = sr.Microphone()
        else:
            self.microphone = sr.Microphone()
        # ---------------------------------------------------------------------

        # tuning to reduce false triggers in noisy/music environment
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.energy_threshold = 400
        self.recognizer.pause_threshold = 0.5   # 0.5s silence = end of utterance
        self.recognizer.non_speaking_duration = 0.4  # how long silence must last

        self.is_listening = False
        self.callback = None
        self.audio_queue = queue.Queue()
        self.last_transcript = ""

        self._last_wake_ts = 0.0

        print("[AUDIO] Calibrating microphone for ambient noise...")
        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=1.5)
        print("[AUDIO] Microphone calibration complete")

    def start_listening(self, callback=None):
        if self.is_listening:
            print("[AUDIO] Already listening")
            return
        self.is_listening = True
        self.callback = callback
        t = threading.Thread(target=self._listen_loop, daemon=True)
        t.start()
        print("[AUDIO] Started listening for voice commands")

    def stop_listening(self):
        self.is_listening = False
        print("[AUDIO] Stopped listening")

    def listen_once(self, timeout=5) -> str:
        """One-shot listen (used by listen_for_command)."""
        try:
            with self.microphone as source:
                audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=10)
            text = transcribe(audio).lower().strip()
            text = _cleanup(text)
            self.last_transcript = text
            return text
        except sr.WaitTimeoutError:
            return ""
        except sr.UnknownValueError:
            return ""
        except Exception:
            return ""

    def _recognize(self, audio) -> str:
        try:
            t = transcribe(audio).lower().strip()
            return t
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as e:
            print(f"[AUDIO] Recognition error: {e}")
            return ""
        except Exception:
            return ""

    def _detect_wake(self, transcript: str):
        if not transcript:
            return None, ""

        wake = None
        for w in sorted(WAKE_WORDS, key=len, reverse=True):
            if w in transcript:
                wake = w
                break

        if not wake:
            return None, ""

        after = transcript.split(wake, 1)[-1]
        after = _cleanup(after)
        return wake, after

    def _emit(self, cmd: str):
        cmd = _cleanup(cmd)
        if not cmd:
            return
        print(f"🎤 [AUDIO] Command: '{cmd}'")
        print("   ↳ Sending to ELI for processing...")
        self.last_transcript = cmd
        if self.callback:
            print("   ↳ CALLBACK IS SET, invoking now")   # <-- FIX: debug
            self.callback(cmd)
        else:
            print("   ↳ NO CALLBACK SET")                 # <-- FIX: debug

    def _followup_command(self, source) -> str:
        """After wake-only, listen briefly for the command."""
        try:
            print("🎧 [AUDIO] Wake-only detected. Listening for command...")
            audio2 = self.recognizer.listen(
                source,
                timeout=FOLLOWUP_TIMEOUT,
            )
            t2 = self._recognize(audio2)
            return _cleanup(t2)
        except sr.WaitTimeoutError:
            return ""
        except Exception:
            return ""

    def _listen_loop(self):
        with self.microphone as source:
            print("[AUDIO] Microphone ready")
            while self.is_listening:
                try:
                    print("👂 [AUDIO] Listening... (wake word + command, or wake then command)")
                    audio = self.recognizer.listen(
                        source,
                        timeout=MAIN_TIMEOUT,
                    )
                    transcript = self._recognize(audio)
                    if not transcript:
                        print("[AUDIO] Could not understand audio")
                        continue

                    print(f"👂 [AUDIO] Heard: '{transcript}'")
                    self.audio_queue.put(transcript)

                    # Short command whitelist — no wake word needed
                    SHORT_COMMANDS = {
                        "next", "previous", "pause", "play", "stop", "resume",
                        "next song", "next track", "previous song", "previous track",
                        "volume up", "volume down", "mute", "unmute", "skip", "back",
                    }
                    if transcript.strip().lower() in SHORT_COMMANDS:
                        self._emit(transcript)
                        continue

                    if ELI_DISABLE_WAKE_WORD:
                        self._emit(transcript)
                        continue

                    wake, inline_cmd = self._detect_wake(transcript)
                    if not wake:
                        continue

                    now = time.time()
                    if (now - self._last_wake_ts) < WAKE_DEBOUNCE_S:
                        continue
                    self._last_wake_ts = now

                    print(f"🔊 [AUDIO] Wake word detected: '{wake}'")

                    prev_vol = _get_current_volume()
                    _duck(prev_vol)

                    try:
                        if inline_cmd:
                            self._emit(inline_cmd)
                        else:
                            follow = self._followup_command(source)
                            if follow:
                                self._emit(follow)
                            else:
                                print(f"⚠️  [AUDIO] Ignoring: Only wake word '{wake}' detected, no command after")
                    finally:
                        _restore_later(prev_vol)

                except sr.WaitTimeoutError:
                    continue
                except Exception as e:
                    print(f"[AUDIO] Loop error: {e}")
                    time.sleep(0.2)


# ----------------------------
# Backward-compatible exports
# ----------------------------
_AUDIO_STT = None

def get_audio_stt():
    global _AUDIO_STT
    if _AUDIO_STT is None:
        _AUDIO_STT = ELIAudioSTT()
    return _AUDIO_STT

def start_audio_listening(callback=None):
    get_audio_stt().start_listening(callback)
    return True

def stop_audio_listening():
    get_audio_stt().stop_listening()
    return True

def listen_for_command(timeout=5):
    return get_audio_stt().listen_once(timeout)