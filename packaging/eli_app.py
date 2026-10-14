"""ELI as one program (the entry point of the packaged app).

    ELI                  the desktop window
    ELI --cli check      check the setup (also: init)
    ELI --daemon         the background learning loop
    ELI --api            the local API on 127.0.0.1:8081
    ELI --selftest       check that everything in the package loads, then exit

A .gguf model in ~/.local/share/eli/models, or in the same folder as the AppImage, is found
without any setting.
"""

import os
import sys
from pathlib import Path


def _prepare() -> None:
    # Programs ELI starts (espeak, paplay, xdg-open, playerctl, ...) must load this system's
    # libraries, not the ones packed inside the app.
    original = os.environ.pop("LD_LIBRARY_PATH_ORIG", None)
    if original:
        os.environ["LD_LIBRARY_PATH"] = original
    else:
        os.environ.pop("LD_LIBRARY_PATH", None)

    bundle = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1] / "src"))
    whisper = bundle / "whisper-base"
    if whisper.is_dir():
        os.environ.setdefault("ELI_WHISPER", str(whisper))

    # The app itself is read-only: ELI reads its own files from it and keeps yours in its data folder.
    from eli.brain.paths import ensure_dirs
    os.environ.setdefault("ELI_ROOT", str(bundle / "eli"))
    paths = ensure_dirs()
    os.environ.setdefault("ELI_ARTIFACTS_DIR", str(paths.artifacts_dir))
    os.environ.setdefault("ELI_MEMORY_DB", str(paths.data_dir / "eli_memory.sqlite3"))


def selftest() -> int:
    """Load every part of the package. ELI_SELFTEST_WAV: a recording whose words must come back.
    With a model available (models folder, beside the AppImage or ELI_GGUF_MODEL_PATH) it is
    asked one question."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    failed = []

    def check(name, run):
        try:
            detail = run()
            print(f"ok    {name}" + (f": {detail}" if detail else ""), flush=True)
        except BaseException as e:
            failed.append(name)
            print(f"FAIL  {name}: {e!r}", flush=True)

    def window():
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        from eli.gui import eli_pro_audio_gui_MKI as gui
        title = gui.ELIEntropicGUI().windowTitle()
        app.processEvents()
        return title

    def model():
        from eli.brain import gguf_inference
        path = gguf_inference.get_model_path()
        if not path:
            return "no model here (skipped)"
        reply = gguf_inference.chat_completion("What is the capital of France? Answer in one word.",
                                               system="You are a helpful assistant.", max_tokens=12, temperature=0.0)
        if "paris" not in reply.lower():
            raise RuntimeError(f"{path.name} answered {reply!r}")
        return f"{path.name}: {reply!r}"

    def speech_recognition():
        import speech_recognition as sr
        from eli.tools.audio_stt import transcribe
        wav = os.environ.get("ELI_SELFTEST_WAV")
        if wav:
            with sr.AudioFile(wav) as source:
                audio = sr.Recognizer().record(source)
            return repr(transcribe(audio))
        try:
            transcribe(sr.AudioData(b"\0\0" * 16000, 16000, 2))
        except sr.UnknownValueError:
            return "model loads (silence gives no words)"
        return "model loads"

    def microphone():
        import pyaudio
        return f"PortAudio {pyaudio.get_portaudio_version_text()}"

    def speech_output():
        import pyttsx3  # noqa: F401
        return ""

    def api():
        from eli.api import server
        return f"{len(server.app.routes)} routes"

    check("window", window)
    check("model (llama.cpp)", model)
    check("speech recognition (local Whisper)", speech_recognition)
    check("microphone capture", microphone)
    check("speech output", speech_output)
    check("API", api)
    print("selftest OK" if not failed else f"selftest FAILED: {', '.join(failed)}", flush=True)
    return 1 if failed else 0


def main() -> int:
    _prepare()
    args = sys.argv[1:]
    mode = args[0] if args else ""
    if mode == "--selftest":
        return selftest()
    if mode == "--cli":
        from eli.tools.manage_eli import main as cli
        return cli(args[1:])
    if mode == "--daemon":
        from eli.brain.proactive_daemon import main as daemon
        return daemon() or 0
    if mode == "--api":
        import uvicorn
        from eli.api.server import app
        uvicorn.run(app, host=os.environ.get("ELI_API_HOST", "127.0.0.1"), port=int(os.environ.get("ELI_API_PORT", "8081")))
        return 0
    if mode in ("-h", "--help"):
        print(__doc__)
        return 0
    from eli.gui.app import main as gui
    return gui() or 0


if __name__ == "__main__":
    sys.exit(main())
