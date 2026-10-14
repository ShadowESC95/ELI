#!/usr/bin/env python3
"""
OS Controller for ELI – GNOME/Wayland first, then generic Wayland, then X11.
Provides screenshot, volume, keyboard, mouse, clipboard.
"""

import os
import subprocess
import shutil
import time
from typing import Optional, Dict, Any

# ----------------------------------------------------------------------
# Environment detection
# ----------------------------------------------------------------------
SESSION_TYPE = os.environ.get('XDG_SESSION_TYPE', 'x11').lower()
DESKTOP = os.environ.get('XDG_CURRENT_DESKTOP', '').lower()
IS_WAYLAND = SESSION_TYPE == 'wayland'
IS_X11 = SESSION_TYPE == 'x11'
IS_GNOME = 'gnome' in DESKTOP

def _check_tool(tool: str) -> bool:
    """Return True if tool is installed and executable."""
    return shutil.which(tool) is not None

# ----------------------------------------------------------------------
# Screenshot – GNOME Screenshot first, then grim, then scrot
# ----------------------------------------------------------------------
def take_screenshot(region: str = "full") -> Dict[str, Any]:
    """
    Take a screenshot.
    region: "full" (entire screen) or "area" (select region)
    Returns dict with ok, path, error.
    """
    # Try GNOME Screenshot (works on GNOME Wayland)
    if IS_GNOME and _check_tool("gnome-screenshot"):
        try:
            if region == "full":
                cmd = ["gnome-screenshot"]
            else:
                cmd = ["gnome-screenshot", "-a"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return {"ok": True, "content": "Screenshot taken.", "response": "Screenshot taken."}
        except Exception:
            pass

    # Try generic Wayland tools (grim + slurp)
    if IS_WAYLAND:
        if region == "full":
            if _check_tool("grim"):
                filename = f"Screenshot_{os.popen('date +%Y%m%d_%H%M%S').read().strip()}.png"
                path = os.path.expanduser(f"~/Pictures/{filename}")
                result = subprocess.run(["grim", path], capture_output=True, text=True)
                if result.returncode == 0:
                    return {"ok": True, "path": path, "content": f"Screenshot saved: {path}", "response": f"Screenshot saved: {path}"}
                else:
                    return {"ok": False, "error": f"grim failed: {result.stderr}", "content": "Screenshot failed", "response": "Screenshot failed"}
            else:
                return {"ok": False, "error": "grim not installed (sudo apt install grim)", "content": "Screenshot failed", "response": "Screenshot failed"}
        else:  # area
            if _check_tool("slurp") and _check_tool("grim"):
                select = subprocess.run(["slurp"], capture_output=True, text=True)
                if select.returncode != 0 or not select.stdout.strip():
                    return {"ok": False, "error": "No area selected", "content": "Screenshot cancelled", "response": "Screenshot cancelled"}
                geometry = select.stdout.strip()
                filename = f"Screenshot_area_{os.popen('date +%Y%m%d_%H%M%S').read().strip()}.png"
                path = os.path.expanduser(f"~/Pictures/{filename}")
                result = subprocess.run(["grim", "-g", geometry, path], capture_output=True, text=True)
                if result.returncode == 0:
                    return {"ok": True, "path": path, "content": f"Screenshot saved: {path}", "response": f"Screenshot saved: {path}"}
                else:
                    return {"ok": False, "error": f"grim failed: {result.stderr}", "content": "Screenshot failed", "response": "Screenshot failed"}
            else:
                return {"ok": False, "error": "slurp or grim not installed (sudo apt install slurp grim)", "content": "Screenshot failed", "response": "Screenshot failed"}

    # X11 fallback (scrot)
    if _check_tool("scrot"):
        if region == "full":
            filename = f"Screenshot_%Y%m%d_%H%M%S.png"
            path = os.path.expanduser(f"~/Pictures/{filename}")
            result = subprocess.run(["scrot", path], capture_output=True, text=True)
            if result.returncode == 0:
                return {"ok": True, "path": path, "content": f"Screenshot saved: {path}", "response": f"Screenshot saved: {path}"}
            else:
                return {"ok": False, "error": f"scrot failed: {result.stderr}", "content": "Screenshot failed", "response": "Screenshot failed"}
        else:
            filename = f"Screenshot_area_%Y%m%d_%H%M%S.png"
            path = os.path.expanduser(f"~/Pictures/{filename}")
            result = subprocess.run(["scrot", "-s", path], capture_output=True, text=True)
            if result.returncode == 0:
                return {"ok": True, "path": path, "content": f"Screenshot saved: {path}", "response": f"Screenshot saved: {path}"}
            else:
                return {"ok": False, "error": f"scrot failed: {result.stderr}", "content": "Screenshot failed", "response": "Screenshot failed"}
    else:
        return {"ok": False, "error": "No screenshot tool found (install gnome-screenshot, grim, or scrot)", "content": "Screenshot failed", "response": "Screenshot failed"}

# ----------------------------------------------------------------------
# Volume control – wpctl (Wayland) then pactl (X11)
# ----------------------------------------------------------------------
def get_volume() -> Optional[int]:
    """Get current volume percentage (0-100)."""
    if IS_WAYLAND and _check_tool("wpctl"):
        result = subprocess.run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"], capture_output=True, text=True)
        if result.returncode == 0:
            parts = result.stdout.strip().split()
            for part in parts:
                try:
                    vol_float = float(part)
                    return int(vol_float * 100)
                except:
                    continue
    if _check_tool("pactl"):
        result = subprocess.run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"], capture_output=True, text=True)
        if result.returncode == 0:
            import re
            m = re.search(r'(\d+)%', result.stdout)
            if m:
                return int(m.group(1))
    return None

def set_volume(level: Optional[int] = None, direction: Optional[str] = None, delta: int = 5) -> Dict[str, Any]:
    """
    Set or adjust volume.
    - level: absolute percentage (0-100)
    - direction: "up" or "down"
    - delta: step percentage for up/down
    """
    if IS_WAYLAND and _check_tool("wpctl"):
        try:
            if level is not None:
                float_level = max(0, min(100, level)) / 100.0
                subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{float_level}"], check=True, capture_output=True)
                return {"ok": True, "content": f"Volume set to {level}%", "response": f"Volume set to {level}%"}
            elif direction == "up":
                subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{delta}%+"], check=True, capture_output=True)
                return {"ok": True, "content": f"Volume raised by {delta}%", "response": f"Volume raised by {delta}%"}
            elif direction == "down":
                subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{delta}%-"], check=True, capture_output=True)
                return {"ok": True, "content": f"Volume lowered by {delta}%", "response": f"Volume lowered by {delta}%"}
            elif direction == "mute":
                subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "1"], check=True, capture_output=True)
                return {"ok": True, "content": "Muted", "response": "Muted"}
            elif direction == "unmute":
                subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"], check=True, capture_output=True)
                return {"ok": True, "content": "Unmuted", "response": "Unmuted"}
        except Exception as e:
            return {"ok": False, "error": str(e), "content": "Volume control failed", "response": "Volume control failed"}

    # Fallback to pactl
    if _check_tool("pactl"):
        try:
            if level is not None:
                subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%"], check=True, capture_output=True)
                return {"ok": True, "content": f"Volume set to {level}%", "response": f"Volume set to {level}%"}
            elif direction == "up":
                subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"+{delta}%"], check=True, capture_output=True)
                return {"ok": True, "content": f"Volume raised by {delta}%", "response": f"Volume raised by {delta}%"}
            elif direction == "down":
                subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"-{delta}%"], check=True, capture_output=True)
                return {"ok": True, "content": f"Volume lowered by {delta}%", "response": f"Volume lowered by {delta}%"}
            elif direction == "mute":
                subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1"], check=True, capture_output=True)
                return {"ok": True, "content": "Muted", "response": "Muted"}
            elif direction == "unmute":
                subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"], check=True, capture_output=True)
                return {"ok": True, "content": "Unmuted", "response": "Unmuted"}
        except Exception as e:
            return {"ok": False, "error": str(e), "content": "Volume control failed", "response": "Volume control failed"}

    return {"ok": False, "error": "No volume control tool found (install wireplumber/wpctl or pulseaudio-utils)", "content": "Volume control failed", "response": "Volume control failed"}

# ----------------------------------------------------------------------
# Keyboard simulation – ydotool (Wayland) then xdotool (X11)
# ----------------------------------------------------------------------
def press_key(key: str) -> Dict[str, Any]:
    """Simulate a key press."""
    key_map = {
        "enter": "Return", "return": "Return", "tab": "Tab", "space": "space",
        "backspace": "BackSpace", "delete": "Delete", "escape": "Escape",
        "up": "Up", "down": "Down", "left": "Left", "right": "Right",
        "home": "Home", "end": "End", "pageup": "Page_Up", "pagedown": "Page_Down",
        "ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "super": "Super",
    }
    keyname = key_map.get(key.lower(), key)

    if IS_WAYLAND and _check_tool("ydotool"):
        try:
            subprocess.run(["ydotool", "key", f"{keyname}:1", f"{keyname}:0"], check=True, capture_output=True)
            return {"ok": True, "content": f"Pressed {key}", "response": f"Pressed {key}"}
        except Exception as e:
            pass
    if _check_tool("xdotool"):
        try:
            subprocess.run(["xdotool", "key", keyname], check=True, capture_output=True)
            return {"ok": True, "content": f"Pressed {key}", "response": f"Pressed {key}"}
        except Exception as e:
            pass
    return {"ok": False, "error": "No keyboard simulation tool found (install ydotool or xdotool)", "content": f"Failed to press {key}", "response": f"Failed to press {key}"}

def type_text(text: str) -> Dict[str, Any]:
    """Type a string."""
    if IS_WAYLAND and _check_tool("ydotool"):
        try:
            subprocess.run(["ydotool", "type", text], check=True, capture_output=True)
            return {"ok": True, "content": f"Typed: {text}", "response": f"Typed: {text}"}
        except Exception as e:
            pass
    if _check_tool("xdotool"):
        try:
            subprocess.run(["xdotool", "type", text], check=True, capture_output=True)
            return {"ok": True, "content": f"Typed: {text}", "response": f"Typed: {text}"}
        except Exception as e:
            pass
    return {"ok": False, "error": "No keyboard simulation tool found", "content": f"Failed to type", "response": f"Failed to type"}

# ----------------------------------------------------------------------
# CLIPBOARD – finally fixed: no timeouts, foreground mode for wl-copy
# ----------------------------------------------------------------------
def set_clipboard(text: str) -> Dict[str, Any]:
    """Set clipboard content. Works on Wayland (wl-copy) and X11 (xclip)."""
    # Wayland – use -f to keep in foreground, no timeout
    if _check_tool("wl-copy"):
        try:
            # No timeout – let it finish naturally
            proc = subprocess.run(
                ["wl-copy", "-f"],  # -f = foreground, prevents forking
                input=text,
                text=True,
                capture_output=True
            )
            if proc.returncode == 0:
                return {"ok": True, "content": "Clipboard set", "response": "Clipboard set"}
            else:
                print(f"[CLIPBOARD] wl-copy failed: {proc.stderr}")
        except Exception as e:
            print(f"[CLIPBOARD] wl-copy exception: {e}")

    # X11 fallback
    if _check_tool("xclip"):
        try:
            # No timeout
            proc = subprocess.run(
                ["xclip", "-selection", "clipboard"],
                input=text,
                text=True,
                capture_output=True
            )
            if proc.returncode == 0:
                return {"ok": True, "content": "Clipboard set", "response": "Clipboard set"}
            else:
                print(f"[CLIPBOARD] xclip failed: {proc.stderr}")
        except Exception as e:
            print(f"[CLIPBOARD] xclip exception: {e}")

    return {"ok": False, "error": "No clipboard tool works",
            "content": "Failed to set clipboard", "response": "Failed to set clipboard"}

def get_clipboard() -> Optional[str]:
    """Get clipboard content. Returns None if unavailable."""
    if _check_tool("wl-paste"):
        try:
            proc = subprocess.run(
                ["wl-paste"],  # no timeout
                capture_output=True,
                text=True
            )
            if proc.returncode == 0:
                return proc.stdout.strip()
            else:
                print(f"[CLIPBOARD] wl-paste failed: {proc.stderr}")
        except Exception as e:
            print(f"[CLIPBOARD] wl-paste exception: {e}")

    if _check_tool("xclip"):
        try:
            proc = subprocess.run(
                ["xclip", "-o", "-selection", "clipboard"],
                capture_output=True,
                text=True
            )
            if proc.returncode == 0:
                return proc.stdout.strip()
        except Exception:
            pass
    return None
