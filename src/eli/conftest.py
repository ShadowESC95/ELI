"""
conftest.py — ELI test suite root configuration.

Placed at: src/eli/tests/conftest.py
(or project root conftest.py)

Ensures:
- ELI_MEMORY_DB points to a temp file per-session
- Memory singleton is reset between tests
- No Ollama / GPU required
"""

import os
import sys
import pytest
from pathlib import Path

# Make sure src/ is on the path when running from project root
_SRC = Path(__file__).resolve().parent.parent.parent  # -> src/
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


# Tests never reach the desktop: commands that would change the volume, play or stop media, open apps
# or files, take screenshots, notify or touch the clipboard run as a no-op instead (exit code 0).
# This applies from collection on, since some test modules call the executor at import.
# ELI_TESTS_REAL_DESKTOP=1 lets them through.
import shutil as _shutil
import subprocess as _subprocess
import webbrowser as _webbrowser

DESKTOP_TOOLS = {
    "pactl", "wpctl", "amixer", "paplay", "aplay", "pw-play", "ffplay", "espeak", "espeak-ng", "spd-say",
    "playerctl", "dbus-send", "gdbus", "qdbus", "spotify", "vlc", "mpv", "rhythmbox",
    "xdg-open", "gtk-launch", "gio", "flatpak", "snap", "firefox", "chromium", "google-chrome", "brave-browser",
    "code", "gedit", "gnome-text-editor", "kate", "nautilus", "dolphin", "libreoffice", "thunderbird",
    "gnome-terminal", "x-terminal-emulator", "gnome-calculator", "notify-send",
    "xdotool", "ydotool", "wtype", "wl-copy", "wl-paste", "xclip", "xsel",
    "gnome-screenshot", "grim", "slurp", "scrot", "spectacle", "import",
    "pkill", "kill", "killall", "systemctl", "loginctl", "shutdown", "reboot", "poweroff",
    "xrandr", "gsettings", "brightnessctl", "nmcli", "bluetoothctl",
}
DESKTOP_CALLS = []  # what the tests asked for, in order
_NOOP = _shutil.which("true") or "/bin/true"


def _desktop_command(args, shell):
    if isinstance(args, (list, tuple)) and args:
        return os.path.basename(str(args[0])) in DESKTOP_TOOLS
    if isinstance(args, (str, bytes)):
        words = (args.decode() if isinstance(args, bytes) else args).replace(";", " ").replace("&", " ").split()
        return any(os.path.basename(w) in DESKTOP_TOOLS for w in (words if shell else words[:1]))
    return False


if os.environ.get("ELI_TESTS_REAL_DESKTOP") != "1":
    _real_popen_init = _subprocess.Popen.__init__

    def _guarded_popen_init(self, args, *a, **k):
        if _desktop_command(args, k.get("shell", False)):
            DESKTOP_CALLS.append(args)
            args = [_NOOP]
            k["shell"] = False
            k.pop("executable", None)
        return _real_popen_init(self, args, *a, **k)

    _real_system = os.system

    def _guarded_system(command):
        if _desktop_command(command, True):
            DESKTOP_CALLS.append(command)
            return 0
        return _real_system(command)

    _subprocess.Popen.__init__ = _guarded_popen_init
    os.system = _guarded_system
    _webbrowser.open = _webbrowser.open_new = _webbrowser.open_new_tab = lambda url, *a, **k: DESKTOP_CALLS.append(url) or True


@pytest.fixture(scope="session", autouse=True)
def _set_pytest_env():
    """Mark as pytest environment so config.py skips disk writes."""
    os.environ.setdefault("PYTEST_CURRENT_TEST", "yes")
    yield


@pytest.fixture(autouse=True)
def _isolate_memory_db(tmp_path, monkeypatch):
    """Every test gets its own SQLite DB and a reset singleton."""
    db = tmp_path / "eli_test.sqlite3"
    monkeypatch.setenv("ELI_MEMORY_DB", str(db))
    monkeypatch.setenv("ELI_MEMORY_DB_PATH", str(db))

    # Reset memory singleton so it picks up the new DB path
    try:
        import eli.brain.memory as mem_mod
        mem_mod._memory_singleton = None
    except Exception:
        pass

    yield

    # Cleanup singleton after test
    try:
        import eli.brain.memory as mem_mod
        mem_mod._memory_singleton = None
    except Exception:
        pass
    try:
        import eli.brain.self_improvement as si
        si._self_engine = None
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _no_gpu(monkeypatch):
    """Prevent accidental GPU usage in tests."""
    monkeypatch.setenv("ELI_N_GPU_LAYERS", "0")
    monkeypatch.setenv("ELI_GGUF_N_CTX", "512")
    yield

exec(open(__file__.replace('conftest.py','conftest_fixes.py')).read())
