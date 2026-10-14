"""ELI as one program (the entry point of the packaged app).

    ELI                  the desktop window
    ELI --cli check      check the setup (also: init)
    ELI --daemon         the background learning loop
    ELI --api            the local API on 127.0.0.1:8081
    ELI --selftest       check that everything in the package works, then exit
    ELI -m <module>      run one of ELI's modules, as `python -m` does (ELI uses this itself)

ELI uses the model it ships with unless there is a .gguf model in ~/.local/share/eli-ai/models,
in the same folder as the AppImage, or at ELI_GGUF_MODEL_PATH.

Settings come from ~/.config/eli-ai/settings (KEY=VALUE lines, e.g. ELI_N_GPU_LAYERS=-1) or from
variables named ELI_AI_ instead of ELI_ (ELI_AI_N_GPU_LAYERS=-1). Other ELI_ variables belong to
other ELI versions and are ignored.
"""

import os
import sys
from pathlib import Path

BUNDLE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1] / "src"))


OWN_PREFIX = "ELI_AI_"  # ELI_AI_MODEL=... sets ELI_MODEL for this app only


def own_settings() -> None:
    """Keep only this app's own settings. Every ELI version reads ELI_... variables, so ones exported
    for another version (in a shell profile, say) are dropped; this app's come from its settings file
    (~/.config/eli-ai/settings, KEY=VALUE lines) and from ELI_AI_... variables, which win."""
    own = {"ELI_" + k[len(OWN_PREFIX):]: v for k, v in os.environ.items()
           if k.startswith(OWN_PREFIX) and len(k) > len(OWN_PREFIX)}
    for k in [k for k in os.environ if k.startswith("ELI_")]:
        del os.environ[k]
    settings = {}
    path = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "eli-ai" / "settings"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    for line in lines:
        line = line.strip()
        if line.startswith("export "):
            line = line[7:].strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            if k.strip().startswith("ELI_"):
                settings[k.strip()] = os.path.expandvars(os.path.expanduser(v.strip().strip('"').strip("'")))
    settings.update(own)
    os.environ.update(settings)


def _prepare() -> None:
    own_settings()
    # Programs ELI starts (espeak, paplay, xdg-open, playerctl, ...) must load this system's
    # libraries, not the ones packed inside the app.
    original = os.environ.pop("LD_LIBRARY_PATH_ORIG", None)
    if original:
        os.environ["LD_LIBRARY_PATH"] = original
    else:
        os.environ.pop("LD_LIBRARY_PATH", None)
    # The Qt inside the app has its own styles only; a desktop's style name (adwaita, breeze...) cannot load
    os.environ.pop("QT_STYLE_OVERRIDE", None)

    whisper = BUNDLE / "whisper-base"
    if whisper.is_dir():
        os.environ.setdefault("ELI_WHISPER", str(whisper))
    shipped = sorted((BUNDLE / "models").glob("*.gguf")) if (BUNDLE / "models").is_dir() else []
    if shipped:
        os.environ.setdefault("ELI_DEFAULT_MODEL", str(shipped[0]))

    from eli.brain.paths import ensure_dirs
    ensure_dirs()


def _code_dirs() -> list:
    import eli
    return [str(Path(eli.__file__).resolve().parent), str(BUNDLE.resolve())]


def selftest() -> int:
    """Check every part, as a user would meet it: a message sent through the window and the window
    closed, with every write into ELI's own (read-only when packaged) code folder reported.
    ELI_SELFTEST_WAV: a recording whose words must come back."""
    import threading
    import time

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    failed, errors, code_writes = [], [], []
    code_dirs = _code_dirs()

    def in_code(path) -> bool:
        try:
            p = os.path.realpath(os.fsdecode(path))
        except (TypeError, ValueError):
            return False
        return "__pycache__" not in p and any(p == d or p.startswith(d + os.sep) for d in code_dirs)

    write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC

    def audit(event, args):
        if event == "open" and args and isinstance(args[0], (str, bytes, os.PathLike)):
            mode, flags = (args[1] if len(args) > 1 else None), (args[2] if len(args) > 2 else 0)
            writing = (isinstance(mode, str) and any(c in mode for c in "wax+")) or bool((flags or 0) & write_flags)
            if writing and in_code(args[0]):
                code_writes.append(f"open {os.fsdecode(args[0])}")
        elif event in ("os.mkdir", "os.rename", "os.remove", "shutil.copyfile") and args and in_code(args[0]):
            code_writes.append(f"{event} {os.fsdecode(args[0])}")
        elif event == "sqlite3.connect" and args and str(args[0]) not in (":memory:", "") and in_code(args[0]):
            code_writes.append(f"sqlite {args[0]}")

    # onnxruntime keeps its telemetry device ID and upload queue here; it must never appear
    telemetry_queue = Path.home() / ".cache" / "Microsoft" / "DeveloperTools" / ".onnxruntime"
    queue_existed = telemetry_queue.exists()

    sys.addaudithook(audit)
    sys.excepthook = lambda t, e, tb: errors.append(f"{t.__name__}: {e}")
    threading.excepthook = lambda a: errors.append(f"{a.exc_type.__name__}: {a.exc_value}")

    def check(name, run):
        try:
            detail = run()
            print(f"ok    {name}" + (f": {detail}" if detail else ""), flush=True)
        except BaseException as e:
            failed.append(name)
            print(f"FAIL  {name}: {e!r}", flush=True)

    def model():
        from eli.brain import gguf_inference
        path = gguf_inference.get_model_path()
        if not path:
            raise RuntimeError("no model found, not even the one ELI ships with")
        reply = gguf_inference.chat_completion("What is the capital of France? Answer in one word.",
                                               system="You are a helpful assistant.", max_tokens=12, temperature=0.0)
        if "paris" not in reply.lower():
            raise RuntimeError(f"{path.name} answered {reply!r}")
        return f"{path.name}: {reply!r}"

    def persona():
        from eli.brain.persona import get_persona, persona_file
        text = get_persona()
        if "ELI" not in text or len(text) < 500:
            raise RuntimeError(f"persona missing or short ({len(text)} chars) at {persona_file()}")
        return f"{len(text)} chars"

    def window_turn():
        from PySide6.QtWidgets import QApplication
        from eli.brain.paths import get_paths
        app = QApplication.instance() or QApplication([])
        from eli.gui import eli_pro_audio_gui_MKI as gui
        conversations = Path(get_paths().conversations_dir)
        before = set(conversations.glob("*.json")) if conversations.is_dir() else set()
        w = gui.ELIEntropicGUI()
        w.show()
        settle = time.time() + 5  # the start-up messages appear over the first seconds
        while time.time() < settle:
            app.processEvents()
            time.sleep(0.05)
        shown_before = len(w.conversation_display.toPlainText())
        w.input_field.setText("What is the capital of France? Answer in one word.")
        w.process_input_stream()
        deadline = time.time() + 600
        while time.time() < deadline:
            app.processEvents()
            worker = getattr(w, "_stream_worker", None) or getattr(w, "_eli_worker", None)
            if worker is not None and worker.isFinished():
                break
            time.sleep(0.05)
        else:
            raise RuntimeError("no reply within 10 minutes")
        for _ in range(40):
            app.processEvents()
            time.sleep(0.02)
        shown = w.conversation_display.toPlainText()[shown_before:]
        w.close()
        app.processEvents()
        if "paris" not in shown.lower():
            raise RuntimeError(f"the window showed: {shown[-400:]!r}")
        reply = [line for line in shown.splitlines() if "paris" in line.lower()]
        saved = (set(conversations.glob("*.json")) if conversations.is_dir() else set()) - before
        if not saved:
            raise RuntimeError(f"closing the window saved no conversation in {conversations}")
        return f"{w.windowTitle()}; reply {reply[-1]!r}; conversation saved to {sorted(saved)[-1]}"

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

    check("model (llama.cpp)", model)
    check("persona", persona)
    check("window: a message sent and the window closed", window_turn)
    check("speech recognition (local Whisper)", speech_recognition)
    check("microphone capture", microphone)
    check("speech output", speech_output)
    check("API", api)
    if telemetry_queue.exists() and not queue_existed:
        failed.append("telemetry")
        print(f"FAIL  telemetry: onnxruntime created its upload queue in {telemetry_queue}", flush=True)
    else:
        print(f"ok    no telemetry (ORT_DISABLE_TELEMETRY={os.environ.get('ORT_DISABLE_TELEMETRY')})", flush=True)
    if errors:
        failed.append("errors raised inside the app")
        print("FAIL  errors raised inside the app (window events, threads):", flush=True)
        for e in errors[:10]:
            print(f"        {e}", flush=True)
    if code_writes:
        failed.append("writes into ELI's own folder")
        print("FAIL  writes into ELI's own folder (read-only when packaged):", flush=True)
        for w in sorted(set(code_writes))[:20]:
            print(f"        {w}", flush=True)
    print("selftest OK" if not failed else f"selftest FAILED: {', '.join(failed)}", flush=True)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(1 if failed else 0)  # background threads (memory, workers) must not hold the exit


def main() -> int:
    _prepare()
    args = sys.argv[1:]
    mode = args[0] if args else ""
    if mode == "-m" and len(args) > 1:
        import runpy
        sys.argv = [args[1]] + args[2:]
        runpy.run_module(args[1], run_name="__main__", alter_sys=True)
        return 0
    if mode.endswith(".py") and os.path.isfile(mode):
        import runpy
        sys.argv = args
        runpy.run_path(mode, run_name="__main__")
        return 0
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
