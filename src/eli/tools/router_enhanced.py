# eli/tools/router_enhanced.py
# Deterministic intent router (upgraded)
# Goals:
# - Stable / redistributable / no machine-specific paths
# - Strong URL/path detection
# - Backward compatibility for legacy tests (e.g. STOP_MEDIA)
# - Canonicalized aliases + STT cleanup
# - Route metadata for debugging / future planner integration
# - Deterministic first, "AGI-ready" structure second

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

# ============================================================
# STATIC CONFIG
# ============================================================

COMMON_DIRS = {
    "home": "~",
    "desktop": "~/Desktop",
    "downloads": "~/Downloads",
    "documents": "~/Documents",
    "music": "~/Music",
    "pictures": "~/Pictures",
    "videos": "~/Videos",
}

DESKTOP_APP_PRIORITY = {
    "spotify", "steam", "discord", "slack", "code", "vscode", "codium",
    "thunderbird", "paraview", "powerview", "rhythmbox", "vlc", "mpv",
    "totem", "gimp", "inkscape", "blender", "krita", "libreoffice",
    "onlyoffice", "wps", "zoom", "skype", "teams", "telegram", "signal",
    "element", "minecraft", "lutris", "heroic", "retroarch", "obs",
    "obs-studio", "audacity", "shotcut", "kdenlive", "openshot",
    "handbrake", "makemkv", "calibre", "evince", "okular", "qbittorrent",
    "transmission", "deluge", "filezilla", "thunar", "nautilus",
    "dolphin", "pcmanfm", "kitty", "alacritty", "konsole", "gnome-terminal",
    "xfce4-terminal", "terminator", "guake", "yakuake", "dropbox",
    "nextcloud", "owncloud", "syncthing", "kodi", "plex", "jellyfin",
    "emby", "stremio", "anki", "obsidian", "joplin", "typora", "marktext",
    "zotero", "mendeley", "pycharm", "intellij", "webstorm", "phpstorm",
    "android-studio", "eclipse", "netbeans", "sublime", "sublime-text",
    "atom", "emacs", "vim", "nvim", "neovim", "gitk", "gitg", "gitkraken",
    "github-desktop", "postman", "insomnia", "docker", "kubectl", "lens",
    "virtualbox", "vmware", "vagrant", "ansible", "terraform", "packer",
    "qgis", "grass", "rstudio", "jupyter", "jupyter-lab", "spyder",
    "matlab", "octave", "gnuplot", "fritzing", "kicad", "eagle", "freecad",
    "openscad", "solvespace", "celestia", "stellarium", "geogebra",
    "code-oss",
    "firefox", "chrome", "chromium",
    "terminal",
}

WEBSITE_ALIASES = {
    "youtube": "https://youtube.com",
    "google": "https://google.com",
    "facebook": "https://facebook.com",
    "twitter": "https://twitter.com",
    "x": "https://x.com",
    "instagram": "https://instagram.com",
    "linkedin": "https://linkedin.com",
    "reddit": "https://reddit.com",
    "github": "https://github.com",
    "stackoverflow": "https://stackoverflow.com",
    "wikipedia": "https://wikipedia.org",
    "amazon": "https://amazon.com",
    "ebay": "https://ebay.com",
    "netflix": "https://netflix.com",
    "hulu": "https://hulu.com",
    "twitch": "https://twitch.tv",
    "gmail": "https://mail.google.com",
    "outlook": "https://outlook.live.com",
    "yahoo": "https://mail.yahoo.com",
    "maps": "https://maps.google.com",
    "news": "https://news.google.com",
    "weather": "https://weather.com",
}

APP_ALIASES = {
    "codes": "code",
    "code-oss": "code",
    "vs code": "code",
    "visual studio code": "code",
    "term": "gnome-terminal",
    "terminal app": "gnome-terminal",
    "chrome browser": "chrome",
    "firefox browser": "firefox",
    # Spelling corrections
    "calender": "gnome-calendar",
    "calander": "gnome-calendar",
    "calendar": "gnome-calendar",
    "calandar": "gnome-calendar",
    "settings": "gnome-control-center",
    "setting": "gnome-control-center",
    "calculator": "gnome-calculator",
    "calc": "gnome-calculator",
    "files": "nautilus",
    "file manager": "nautilus",
    "text editor": "gedit",
    "editor": "gedit",
    "system monitor": "gnome-system-monitor",
    "monitor": "gnome-system-monitor",
    "music player": "rhythmbox",
    "image viewer": "eog",
    "photos": "eog",
    "disks": "gnome-disks",
    "disk usage": "baobab",
    "screenshot": "gnome-screenshot",
}

MEDIA_APPS = ["spotify", "vlc", "chrome", "firefox", "mpv", "rhythmbox", "audacious", "youtube", "netflix"]


# ============================================================
# LOW-LEVEL HELPERS
# ============================================================

def _mk(
    action: str,
    args: Optional[Dict[str, Any]] = None,
    confidence: float = 0.7,
    *,
    matched_by: Optional[str] = None,
    entities: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Canonical route object. Includes metadata for observability/debugging.
    Older code can ignore the extra keys.
    """
    out = {
        "action": action,
        "args": args or {},
        "confidence": float(max(0.0, min(1.0, confidence))),
    }
    meta = {}
    if matched_by:
        meta["matched_by"] = matched_by
    if entities:
        meta["entities"] = entities
    if meta:
        out["meta"] = meta
    return out


def _normalize_text(text: str) -> Tuple[str, str]:
    """
    Returns (raw_clean, low_clean)
    Removes weird whitespace/control chars that can break regexes.
    """
    raw = (text or "")
    raw = raw.replace("\u200b", " ").replace("\ufeff", " ")
    raw = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", raw)  # strip control chars
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw, raw.lower()


def _clean_app_name(s: str) -> str:
    s = s.strip()
    s = re.sub(r'^(?:the|my|a|an)\s+', '', s, flags=re.I)
    s = re.sub(r'^(?:application|app)\s+', '', s, flags=re.I)
    s = re.sub(r'\s+located.*$', '', s, flags=re.I).strip()
    s = APP_ALIASES.get(s.lower(), s)
    return s


def _is_likely_url(s: str) -> bool:
    """
    Detects URLs and bare domains (google.com, www.x.y, foo.io/bar).
    Avoids false positives for local files when possible.
    """
    s = s.strip().lower()
    if not s:
        return False

    if s.startswith(("http://", "https://", "www.")):
        return True

    # domain.tld[/...]
    # conservative but broad enough for practical routing
    if re.match(r"^(?:[a-z0-9-]+\.)+[a-z]{2,24}(?:[:/].*)?$", s):
        return True

    return False


def _normalize_url(s: str) -> str:
    s = s.strip()
    if s.lower().startswith(("http://", "https://")):
        return s
    if s.lower().startswith("www."):
        return f"https://{s}"
    if _is_likely_url(s):
        return f"https://{s}"
    return s


def _is_likely_path(s: str) -> bool:
    s = s.strip()
    if not s:
        return False

    # URL check first to avoid "google.com" becoming a file
    if _is_likely_url(s):
        return False

    if s.startswith(("./", "../", "~", "/")):
        return True

    if "/" in s or "\\" in s:
        return True

    if s.lower() in COMMON_DIRS:
        return True

    # file.ext style
    if "." in s:
        ext = s.rsplit(".", 1)[-1]
        if ext.isalpha() and 1 <= len(ext) <= 8:
            return True

    keywords = {
        "directory", "folder", "file", "path", "location",
        "desktop", "documents", "downloads", "music", "pictures", "videos"
    }
    toks = set(re.findall(r"[a-zA-Z]+", s.lower()))
    if toks & keywords:
        return True

    return False


def _expand_common_dir(s: str) -> str:
    key = s.strip()

    # If already a full/home path, just expand ~ and return
    if key.startswith(("~", "/", "./")):
        return str(Path(key).expanduser())

    low = re.sub(r'^(?:the|my|a|an)\s+', '', key.lower()).strip()

    for dirname, path in COMMON_DIRS.items():
        if re.search(rf"\b{re.escape(dirname)}\b", low):
            rest = re.sub(rf"\b{re.escape(dirname)}\b", "", low).strip()
            # Clean leftover slashes/dots
            rest = rest.strip("/. ")
            if rest:
                return str(Path(path).expanduser() / rest)
            return str(Path(path).expanduser())

    return COMMON_DIRS.get(low, str(Path(key).expanduser()))


def _extract_path_from_text(raw: str) -> Optional[str]:
    patterns = [
        r'([~/][\w.\- /]+(?:\.\w+)?)',
        r'(\./[\w.\- /]+(?:\.\w+)?)',
        r'(\.\./[\w.\- /]+(?:\.\w+)?)',
        r'([\w.\-]+/\S+)',
        r'([A-Za-z0-9_.-]+\.(?:py|txt|md|json|yaml|yml|csv|pdf|log|ini|cfg|toml|sh))',
    ]
    for p in patterns:
        m = re.search(p, raw)
        if m:
            return m.group(1).strip()
    return None


def _extract_int(raw: str, default: int, min_value: int, max_value: int) -> int:
    m = re.search(r'(\d+)', raw)
    if not m:
        return default
    n = int(m.group(1))
    return max(min_value, min(max_value, n))


def _canonical_media_command(low: str) -> Optional[str]:
    # Specific ordering matters
    if "unmute" in low:
        return "unmute"
    if "mute" in low:
        return "mute"
    if "pause" in low or re.search(r"\bstop\b", low):
        return "pause"  # generic media stop often means pause
    if "resume" in low or re.search(r"\bplay\b", low):
        return "play"
    if "next" in low or "skip" in low:
        return "next"
    if "previous" in low or "prev" in low or re.search(r"\bback\b", low):
        return "previous"
    if "shuffle" in low:
        return "shuffle"
    if "repeat" in low:
        return "repeat"
    return None


def _is_time_recall_query(raw: str, low: str) -> bool:
    patterns = [
        r"\bwhat did (?:we|i|you) (?:discuss|talk|say|mention)\b",
        r"\bwhat was (?:the )?last (?:thing|topic|subject|conversation)\b",
        r"\b(?:an?\s+hour\s+ago|earlier today|this morning|yesterday)\b",
        r"\bwhat did i (?:say|ask|tell you)\b",
    ]
    return any(re.search(p, low) for p in patterns)


def _looks_like_conversation_summary(low: str) -> bool:
    return any(re.search(p, low) for p in [
        r"^summari[sz]e\s+(?:the\s+)?(?:conversation|chat|discussion|what we talked about)",
        r"^summari[sz]e\s+(?:the\s+)?last\s+\d+\s+(?:messages|conversations|turns)",
    ])


# ============================================================
# ROUTER
# ============================================================

def route(text: str) -> Dict[str, Any]:
    raw, low = _normalize_text(text)

    if not raw:
        return _mk("CHAT", {"message": ""}, 0.2, matched_by="empty_input")

        # ============================================================
    # LEGACY-COMPAT MEDIA INTENTS (must be before generic MEDIA_CONTROL)
    # Keeps test compatibility and deterministic semantics.
    # ============================================================
    if re.search(r"\bstop\s+(?:the\s+)?(?:media|music|spotify)\b", low):
        return {"action": "STOP_MEDIA", "args": {}, "confidence": 0.96}

    if re.search(r"\bpause\s+(?:the\s+)?(?:media|music|spotify)\b", low):
        return {"action": "PAUSE_MEDIA", "args": {}, "confidence": 0.96}

    if re.search(r"\b(play|resume|start)\s+(?:the\s+)?(?:media|music|spotify)\b", low):
        return {"action": "PLAY_MEDIA", "args": {}, "confidence": 0.96}

    if re.search(r"\b(next|skip)\s+(?:the\s+)?(?:song|track|media)\b", low):
        return {"action": "NEXT_MEDIA", "args": {}, "confidence": 0.96}

    if re.search(r"\b(previous|prev|back)\s+(?:the\s+)?(?:song|track|media)\b", low):
        return {"action": "PREVIOUS_MEDIA", "args": {}, "confidence": 0.96}

    # ------------------------------------------------------------
    # 0) HARD COMPATIBILITY / REGRESSION CONTRACTS
    # ------------------------------------------------------------
    # Important: tests may expect STOP_MEDIA exactly for "stop media"
    if low.strip() == "stop media":
        return _mk("STOP_MEDIA", {}, 0.99, matched_by="compat.stop_media_exact")

    # Bare domain / URL
    if _is_likely_url(raw):
        return _mk(
            "OPEN_URL",
            {"url": _normalize_url(raw)},
            0.99,
            matched_by="url.bare",
            entities={"url": _normalize_url(raw)},
        )

    # ------------------------------------------------------------
    # 1) SELF / SYSTEM INTELLIGENCE INTENTS
    # ------------------------------------------------------------
    if any(p in low for p in ["analyze yourself", "analyse yourself", "self analysis", "check yourself", "diagnostic"]):
        return _mk("SELF_ANALYZE", {}, 0.95, matched_by="self.analyze")

    if any(p in low for p in ["morning report", "daily report", "intelligence report", "status report"]):
        return _mk("MORNING_REPORT", {}, 0.95, matched_by="self.morning_report")

    if "improve" in low and ("yourself" in low or "self" in low or "code" in low):
        return _mk("SELF_IMPROVE", {}, 0.9, matched_by="self.improve")

    if "suggest" in low and ("improvement" in low or "optimization" in low or "optimisation" in low):
        return _mk("SELF_ANALYZE", {"suggest": True}, 0.9, matched_by="self.suggest_improvements")

    # ------------------------------------------------------------
    # 2) CODE / IDE / DEV WORKFLOWS
    # ------------------------------------------------------------
    if any(p in low for p in [
        "create project", "build project", "generate project", "make project",
        "new project", "start project"
    ]):
        return _mk("GENERATE_PROJECT", {"description": raw}, 0.95, matched_by="dev.generate_project")

    code_triggers = [
        "create a script", "write a script", "generate a script",
        "create a python", "write a python", "make a python",
        "create a function", "write a function", "generate a function",
        "write code", "generate code", "write me code",
        "create code", "build a script", "make a script",
        "create me a script", "write me a script"
    ]
    if any(p in low for p in code_triggers):
        return _mk("GENERATE_SCRIPT", {"description": raw}, 0.95, matched_by="dev.generate_script")

    if re.search(r"(show|open|view|display)\s+.{0,20}?(diff|changes?|what.{0,10}fixed)", low):
        return _mk("SHOW_DIFF", {}, 0.9, matched_by="dev.show_diff")

    # fixed regex (no hidden control char nonsense)
    if re.search(r"(open|show|view)\s+.{0,20}?(?:in\s+)?(?:code|editor|ide)\b", low):
        pm = re.search(r"([~/\w.\- /]+\.py)\b", raw)
        path = pm.group(1).strip() if pm else ""
        return _mk("OPEN_IN_IDE", {"path": path}, 0.88, matched_by="dev.open_in_ide", entities={"path": path} if path else None)

    if any(p in low for p in ["open ide", "open code editor", "show ide", "code editor"]):
        return _mk("OPEN_IDE", {}, 0.97, matched_by="dev.open_ide")

    # ------------------------------------------------------------
    # 3) MEMORY / CONTEXT / TEMPORAL RECALL
    # ------------------------------------------------------------
    if _is_time_recall_query(raw, low):
        # Let chat/planner handle temporal interpretation using memory backend
        return _mk("CHAT", {"message": raw}, 0.98, matched_by="memory.temporal_recall_as_chat")

    m = re.match(r"^(?:recall|memory recall)\s+(.+)$", raw, re.I)
    if m:
        return _mk("MEMORY_RECALL", {"query": m.group(1).strip()}, 1.0, matched_by="memory.recall_explicit")

    if re.search(r"(what (is|was) (my|our) favourite colour|what (is|was) (my|our) favorite color|tell me (my|our) favorite color)", raw, re.I):
        return _mk("MEMORY_RECALL", {"query": "favorite color"}, 0.95, matched_by="memory.favorite_color")

    if re.search(r"(what (is|was) (my|our) name|what should you call me)", raw, re.I):
        return _mk("MEMORY_RECALL", {"query": "name"}, 0.95, matched_by="memory.name_recall")

    if re.search(r"\b(?:access|query)\s+neural\s+archive\b", raw, re.I):
        return _mk("MEMORY_RECALL", {"query": "recent memories"}, 1.0, matched_by="memory.neural_archive_alias")

    if _looks_like_conversation_summary(low):
        m_num = re.search(r"last\s+(\d+)", low)
        limit = int(m_num.group(1)) if m_num else 10
        return _mk("MEMORY_RECALL", {"query": "recent", "limit": limit}, 0.95, matched_by="memory.conversation_summary")

    # Explicit remember/store (keep this later than some command parses)
    m = re.match(r"^(?:remember|store|save|note)\s+(?:that\s+)?(.+)$", raw, re.I)
    if m:
        text_to_store = m.group(1).strip()
        return _mk(
            "MEMORY_STORE",
            {"text": text_to_store, "tags": ["user_memory", "remembered"]},
            1.0,
            matched_by="memory.store_explicit",
            entities={"text": text_to_store},
        )

    if re.search(r"\b(store|remember|save)\s+(?:this\s+)?memory\b", low):
        return _mk("MEMORY_STORE", {"text": raw}, 0.8, matched_by="memory.store_generic")

    # ------------------------------------------------------------
    # 4) MEDIA CONTROL (specific → generic)
    # ------------------------------------------------------------
    # Specific next/prev track controls (legacy-friendly)
    if re.search(r"\b(next|skip)\s+(?:the\s+)?(?:song|track)\b", low):
        return _mk("NEXT_MEDIA", {}, 0.95, matched_by="media.next_track_specific")
    if re.search(r"\b(previous|back)\s+(?:the\s+)?(?:song|track)\b", low):
        return _mk("PREVIOUS_MEDIA", {}, 0.95, matched_by="media.prev_track_specific")

    # App-targeted media commands
    for app in MEDIA_APPS:
        if re.search(rf"\b{re.escape(app)}\b", low):
            cmd = _canonical_media_command(low)
            if cmd:
                # preserve STOP_MEDIA semantic if user literally says stop media/music/spotify later
                if cmd == "pause" and re.search(r"\bstop\b", low) and app in {"spotify"}:
                    return _mk("STOP_MEDIA", {}, 0.93, matched_by="media.legacy_stop_specific_app", entities={"target": app})
                return _mk(
                    "MEDIA_CONTROL",
                    {"command": cmd, "target": app, "type": "app"},
                    0.95,
                    matched_by="media.app_targeted",
                    entities={"target": app, "command": cmd},
                )

    # Browser/video media
    if any(k in low for k in ["netflix", "youtube", "browser", "tab", "video"]):
        cmd = _canonical_media_command(low)
        if cmd:
            if "forward" in low:
                cmd = "seek_forward"
            elif "rewind" in low:
                cmd = "seek_backward"
            return _mk(
                "MEDIA_CONTROL",
                {"command": cmd, "type": "browser"},
                0.9,
                matched_by="media.browser",
                entities={"command": cmd},
            )

    # Generic media control
    media_keywords = ["media", "music", "audio", "song", "track", "player", "spotify"]
    media_commands = ["pause", "play", "resume", "stop", "next", "previous", "prev", "skip"]
    if any(k in low for k in media_keywords) or any(k in low for k in media_commands):
        # legacy explicit actions first
        if re.search(r"\bstop\s+(?:the\s+)?(?:media|music|spotify)\b", low):
            return _mk("STOP_MEDIA", {}, 0.95, matched_by="media.stop_legacy")
        if re.search(r"\bpause\s+(?:the\s+)?(?:media|music|spotify)\b", low):
            return _mk("PAUSE_MEDIA", {}, 0.9, matched_by="media.pause_legacy")
        if re.search(r"\b(play|resume|start)\s+(?:the\s+)?(?:media|music|spotify)\b", low):
            return _mk("PLAY_MEDIA", {}, 0.9, matched_by="media.play_legacy")
        if re.search(r"\b(next|skip)\s+(?:the\s+)?(?:song|track|media)\b", low):
            return _mk("NEXT_MEDIA", {}, 0.9, matched_by="media.next_legacy")
        if re.search(r"\b(previous|back)\s+(?:the\s+)?(?:song|track|media)\b", low):
            return _mk("PREVIOUS_MEDIA", {}, 0.9, matched_by="media.prev_legacy")

        # Bare single-word commands → map to specific actions
        cmd = _canonical_media_command(low)
        if cmd:
            # Check if user literally said "stop" (not "pause")
            if re.search(r"\bstop\b", low) and cmd == "pause":
                return _mk("STOP_MEDIA", {}, 0.85, matched_by="media.bare_stop", entities={"command": "stop"})
            _bare_cmd_map = {
                "pause": ("PAUSE_MEDIA", 0.88),
                "play": ("PLAY_MEDIA", 0.88),
                "stop": ("STOP_MEDIA", 0.85),
                "next": ("NEXT_MEDIA", 0.88),
                "previous": ("PREVIOUS_MEDIA", 0.88),
            }
            mapped = _bare_cmd_map.get(cmd)
            if mapped:
                return _mk(mapped[0], {}, mapped[1], matched_by="media.bare_command", entities={"command": cmd})
            return _mk(
                "MEDIA_CONTROL",
                {"command": cmd, "type": "generic"},
                0.85,
                matched_by="media.generic",
                entities={"command": cmd},
            )

    # ------------------------------------------------------------
    # 5) TIME / DATE / CAPABILITIES
    # ------------------------------------------------------------
    if any(re.search(p, low) for p in [
        r'\bwhat time\b', r'\bcurrent time\b', r'\bclock\b', r'^time[?!.\s]*$', r'\btell me the time\b'
    ]):
        return _mk("TIME", {}, 1.0, matched_by="system.time")

    if any(re.search(p, low) for p in [
        r'\bwhat date\b', r'\bcurrent date\b', r'\btoday.*date\b', r'^date[?!.\s]*$', r"\bwhat(?:'s| is) today\b"
    ]):
        return _mk("DATE", {}, 1.0, matched_by="system.date")

    if low in ("list capabilities", "capabilities", "what can you do"):
        return _mk("LIST_CAPABILITIES", {}, 1.0, matched_by="system.capabilities")

    if re.search(r"\b(?:check|what is)\s+chronal\s+alignment\b", raw, re.I):
        return _mk("TIME", {}, 1.0, matched_by="alias.chronal_alignment")

    # ------------------------------------------------------------
    # 5b) ALARM / TIMER
    # ------------------------------------------------------------
    m = re.search(r"\b(?:set|start|create)\s+(?:a\s+)?(?:timer|countdown)\s+(?:for\s+)?(\d+)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?)\b", low)
    if m:
        val = int(m.group(1))
        unit = m.group(2).lower()
        if unit.startswith("min"):
            val *= 60
        elif unit.startswith("hour") or unit.startswith("hr"):
            val *= 3600
        return _mk("SET_TIMER", {"duration": val}, 0.98, matched_by="timer.set_duration", entities={"seconds": val})

    m = re.search(r"\b(?:set|create)\s+(?:a\s+)?(?:alarm|reminder)\s+(?:for\s+)?(\d{1,2}[:.]\d{2})\b", low)
    if m:
        alarm_time = m.group(1).replace(".", ":")
        return _mk("SET_ALARM", {"time": alarm_time}, 0.98, matched_by="timer.set_alarm", entities={"time": alarm_time})

    m = re.search(r"\b(?:set|create)\s+(?:a\s+)?(?:alarm|timer|reminder)\b", low)
    if m:
        # Try to find a time anywhere in the string
        time_m = re.search(r"(\d{1,2}[:.]\d{2})", raw)
        dur_m = re.search(r"(\d+)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?)", low)
        if time_m:
            alarm_time = time_m.group(1).replace(".", ":")
            return _mk("SET_ALARM", {"time": alarm_time}, 0.95, matched_by="timer.set_alarm_loose", entities={"time": alarm_time})
        elif dur_m:
            val = int(dur_m.group(1))
            unit = dur_m.group(2).lower()
            if unit.startswith("min"):
                val *= 60
            elif unit.startswith("hour") or unit.startswith("hr"):
                val *= 3600
            return _mk("SET_TIMER", {"duration": val}, 0.95, matched_by="timer.set_duration_loose", entities={"seconds": val})
        return _mk("CHAT", {"message": raw}, 0.6, matched_by="timer.no_time_found")

    # ------------------------------------------------------------
    # 6) FILE SYSTEM / PATH / DIRECTORY
    # ------------------------------------------------------------
    m = re.match(r"^(?:list|show)\s+(?:files|contents|directory)\s+(?:in\s+)?(.+)$", raw, re.I)
    if m:
        path = m.group(1).strip()
        return _mk("LIST_DIR", {"path": path}, 0.95, matched_by="fs.list_dir_explicit", entities={"path": path})

    if re.search(r"\b(list|show)\s+(?:the\s+)?(?:files?|contents?|directory)\s+(?:in\s+)?(?:the\s+)?(?:project|current)\b", raw, re.I):
        return _mk("LIST_DIR", {"path": "."}, 0.9, matched_by="fs.list_project")

    if re.match(r"^(?:list|show)\s+directory\s*$", raw, re.I):
        return _mk("LIST_DIR", {"path": "."}, 0.9, matched_by="fs.list_dir_default")

    if re.match(r"^(?:open|launch|start|show)\s+(?:home|home\s+(?:folder|directory)|file\s+manager|files?)\b", low):
        return _mk("OPEN_FILE_SYSTEM", {"path": "~"}, 0.98, matched_by="fs.open_home")

    if re.search(r"\b(?:access|open|launch)\s+storage\s+matrix\b", raw, re.I):
        return _mk("OPEN_FILE_SYSTEM", {"path": "~"}, 1.0, matched_by="alias.storage_matrix")

    # ------------------------------------------------------------
    # 7) URL / BROWSER
    # ------------------------------------------------------------
    if re.match(r"^(?:open|launch)\s+url\s+(.+)$", raw, re.I):
        url = re.match(r"^(?:open|launch)\s+url\s+(.+)$", raw, re.I).group(1).strip()
        return _mk("OPEN_URL", {"url": _normalize_url(url)}, 0.98, matched_by="web.open_url_explicit")

    m = re.match(r"^(?:open|launch)\s+(https?://\S+)\s*$", raw, re.I)
    if m:
        return _mk("OPEN_URL", {"url": m.group(1)}, 0.98, matched_by="web.open_url_with_scheme")

    if re.search(r"\b(?:open|launch|access|start)\s+network\s+browser\b", low):
        return _mk("OPEN_BROWSER", {}, 0.98, matched_by="web.browser_alias_network")

    if re.match(r"^(?:open|launch|start)\s+(?:browser|browse|web|firefox|chrome|chromium|safari|edge)\b", low):
        return _mk("OPEN_BROWSER", {}, 0.98, matched_by="web.browser_explicit")

    if re.match(r"^(?:open|launch|start)\s+(?:the\s+)?(?:internet|web)\b", low):
        return _mk("OPEN_BROWSER", {}, 0.98, matched_by="web.browser_internet_alias")

    m = re.match(r"^(?:search\s+(?:for\s+)?)(.+)$", raw, re.I)
    if m:
        query = m.group(1).strip()
        if query:
            return _mk("OPEN_BROWSER", {"query": query}, 0.95, matched_by="web.search", entities={"query": query})

    # ------------------------------------------------------------
    # 8) SCREENSHOT / INPUT / VOLUME
    # ------------------------------------------------------------
    if re.search(r"\b(take|capture)\s+(a\s+)?(screenshot|screen\s*shot|screen\s*capture|screen)\b", raw, re.I):
        region = "area" if re.search(r"\b(area|region|selection|part)\b", raw, re.I) else "full"
        return _mk("SCREENSHOT", {"region": region}, 0.98, matched_by="io.screenshot", entities={"region": region})

    # Volume (order matters: unmute before mute)
    if re.search(r"\bmax(?:imum)?\s+volume\b|\bvolume\s+max\b|\bfull\s+volume\b", low):
        return _mk("VOLUME", {"direction": "set", "level": 100}, 0.99, matched_by="audio.volume_max")

    m = re.search(r"\b(?:(?:set|change)\s+volume\s+to|volume\s+set)\s+(\d+)%?", raw, re.I)
    if m:
        level = max(0, min(100, int(m.group(1))))
        return _mk("VOLUME", {"direction": "set", "level": level}, 0.98, matched_by="audio.volume_set", entities={"level": level})

    if re.search(r"\bunmute\b", low):
        return _mk("VOLUME", {"direction": "unmute"}, 0.98, matched_by="audio.unmute")

    if re.search(r"\bmute\b", low):
        return _mk("VOLUME", {"direction": "mute"}, 0.98, matched_by="audio.mute")

    if re.search(r"\b(raise|increase|volume\s+up)\b", low):
        return _mk("VOLUME", {"direction": "up", "delta": 10}, 0.95, matched_by="audio.volume_up")

    if re.search(r"\b(lower|decrease|volume\s+down)\b", low):
        return _mk("VOLUME", {"direction": "down", "delta": 10}, 0.95, matched_by="audio.volume_down")

    # Keyboard typing/press
    m = re.match(r"^type\s+(.+)$", raw, re.I)
    if m:
        typed = m.group(1).strip()
        if typed:
            return _mk("KEYBOARD", {"type": typed}, 0.95, matched_by="io.keyboard_type", entities={"text": typed})

    m = re.search(r"\b(press|hit)\s+(enter|return)\b", raw, re.I)
    if m:
        return _mk("KEYBOARD", {"key": "Return"}, 0.95, matched_by="io.keyboard_enter")

    m = re.search(r"\b(press|hit)\s+([a-zA-Z0-9_\-]+)\b", raw, re.I)
    if m:
        key = m.group(2)
        return _mk("KEYBOARD", {"key": key}, 0.9, matched_by="io.keyboard_key", entities={"key": key})

    # ------------------------------------------------------------
    # 9) CALENDAR shortcuts before generic read/show
    # ------------------------------------------------------------
    if re.match(r"^(?:show|list)\s+(?:my\s+)?calendar$", low, re.I):
        return _mk("LIST_EVENTS", {}, 0.97, matched_by="calendar.show_exact")

    # ------------------------------------------------------------
    # 10) FILE READ / FIX / SUMMARIZE / ANALYZE
    # ------------------------------------------------------------
    m = re.match(r"^(read|show)\s+(.+)$", raw, re.I)
    if m:
        path = m.group(2).strip()
        return _mk("READ_FILE", {"path": path}, 0.9, matched_by="file.read_show", entities={"path": path})

    m = re.search(r"(fix|debug|repair|correct|patch)\s+.{0,30}?([\w./~ -]+\.py)\b", raw, re.I)
    if m:
        path = m.group(2).strip()
        return _mk("FIX_FILE", {"path": path}, 0.92, matched_by="file.fix_python", entities={"path": path})

    m = re.search(r"(fix|debug|repair|correct|patch)\s+(?:the\s+)?(?:script|file|code)(?:\s+(?:in|at|located\s+at))?\s+(.+)$", raw, re.I)
    if m:
        path = (m.group(2) or "").strip()
        extracted = _extract_path_from_text(path) or path
        return _mk("FIX_FILE", {"path": extracted}, 0.9, matched_by="file.fix_generic", entities={"path": extracted})

    if re.match(r"^(?:fix|debug|repair|correct|patch)\b", low):
        guessed = _extract_path_from_text(raw)
        if guessed:
            return _mk("FIX_FILE", {"path": guessed}, 0.86, matched_by="file.fix_fallback", entities={"path": guessed})

    # summarize: conversation vs file/topic
    m = re.match(r"^(?:summari[sz]e|analyse|analyze)\s+(.+)$", raw, re.I)
    if m:
        target = m.group(1).strip()
        expanded = os.path.expanduser(target)
        if _is_likely_path(target) or os.path.exists(expanded):
            abs_path = os.path.abspath(expanded)
            # Route PDFs to PDF analyzer, everything else to SUMMARIZE_FILE (reads + chats)
            if abs_path.lower().endswith(".pdf"):
                return _mk("ANALYZE_PDF", {"path": abs_path}, 0.95, matched_by="analyze.summarize_pdf")
            return _mk("SUMMARIZE_FILE", {"path": abs_path}, 0.92, matched_by="analyze.summarize_file")
        return _mk("MEMORY_RECALL", {"query": target}, 0.8, matched_by="memory.summarize_topic")

    # PDF analysis
    if any(w in low for w in ["pdf", "pdfs"]) and any(w in low for w in ["analyze", "analyse", "summarize", "summarise", "read", "extract"]):
        path_match = None
        for pattern in [
            r'(?:in|from|at)\s+([~/\w.\-/ ]+)',
            r'([~/\w.\-/ ]+\.pdf)\b',
            r'(/[\w./\- ]+\.pdf)\b',
        ]:
            mm = re.search(pattern, raw, re.I)
            if mm:
                path_match = mm.group(1).strip()
                break
        if path_match:
            return _mk("ANALYZE_PDF", {"path": path_match}, 0.95, matched_by="analyze.pdf", entities={"path": path_match})
        return _mk("ANALYZE_PDF", {"path": "."}, 0.85, matched_by="analyze.pdf_default")

    # CSV analysis
    if any(w in low for w in ["csv", "spreadsheet"]) or (any(w in low for w in ["read", "show"]) and ".csv" in low):
        if any(w in low for w in ["analyze", "analyse", "summarize", "summarise", "read", "parse", "show"]):
            m = re.search(r'([~/\w.\-/ ]+\.csv)\b', raw, re.I)
            if m:
                return _mk("ANALYZE_CSV", {"path": m.group(1).strip()}, 0.95, matched_by="analyze.csv", entities={"path": m.group(1).strip()})

    # ------------------------------------------------------------
    # 10) DOCUMENT / NOTES / GENERATION
    # ------------------------------------------------------------
    note_m = re.match(r'^(?:write|save|create|make|add)\s+(?:a\s+)?notes?[:\s]+(?:saying\s+)?(.+)$', raw, re.I)
    if note_m:
        note_text = note_m.group(1).strip()
        return _mk("WRITE_NOTE", {"text": note_text}, 0.97, matched_by="notes.write", entities={"text": note_text})

    note_m2 = re.match(r'^(?:write|add)\s+note\s+(.+)$', raw, re.I)
    if note_m2:
        note_text = note_m2.group(1).strip()
        return _mk("WRITE_NOTE", {"text": note_text}, 0.95, matched_by="notes.add", entities={"text": note_text})

    if "generate" in low and "document" in low:
        topic = re.sub(r'\b(generate|create|write|document|about|on|a|the)\b', '', low).strip()
        return _mk("GENERATE_DOCUMENT", {"topic": topic or raw}, 0.95, matched_by="doc.generate_generic", entities={"topic": topic or raw})

    m = re.search(r"\b(create|write|generate|draft|make)\s+(?:a\s+)?(?:doc|document|report|notes?)\s+(?:about|on|for)\s+(.+)$", raw, re.I)
    if m:
        topic = m.group(2).strip()
        return _mk("DOC_GENERATE", {"topic": topic, "format": "md"}, 0.9, matched_by="doc.generate_structured", entities={"topic": topic})

    # Data fabricator alias
    if re.search(r"\b(?:fabricate|create|make)\s+data\s+(?:construct|fabricator)\b", raw, re.I):
        topic_match = re.search(r"fabricate data construct(?:\s+about\s+|\s+on\s+)?(.+)$", raw, re.I)
        if topic_match:
            topic = topic_match.group(1).strip()
            return _mk("DATA_FABRICATOR", {"topic": topic}, 0.98, matched_by="alias.data_fabricator", entities={"topic": topic})
        return _mk("DATA_FABRICATOR", {}, 0.98, matched_by="alias.data_fabricator")

    # ------------------------------------------------------------
    # 11) CLIPBOARD / WEATHER / CALENDAR
    # ------------------------------------------------------------
    if any(w in low for w in ["clipboard", "copy", "paste"]):
        if "copy" in low or "set clipboard" in low:
            content = re.sub(r'.*(copy|set clipboard to|clipboard)\s+', '', raw, flags=re.I).strip()
            return _mk("SET_CLIPBOARD", {"text": content}, 0.9, matched_by="clipboard.set", entities={"text": content})
        if "get" in low or "what" in low or "show" in low:
            return _mk("GET_CLIPBOARD", {}, 0.9, matched_by="clipboard.get")

    if any(w in low for w in ["weather", "forecast", "temperature"]):
        location_match = re.search(r'\b(?:in|at|for)\b\s+([\w\s,\-]+)', raw, re.I)
        location = location_match.group(1).strip() if location_match else None
        return _mk("GET_WEATHER", {"location": location}, 0.95, matched_by="info.weather", entities={"location": location} if location else None)

    if any(w in low for w in ["calendar", "calender", "calander", "event", "appointment", "meeting"]):
        if any(w in low for w in ["show", "list", "my", "what", "open", "display"]):
            return _mk("LIST_EVENTS", {}, 0.95, matched_by="calendar.list")
        if any(w in low for w in ["add", "create", "schedule"]):
            return _mk("ADD_EVENT", {"text": raw}, 0.95, matched_by="calendar.add", entities={"text": raw})

    # ------------------------------------------------------------
    # 12) SYSTEM SETTINGS / PANELS / ALIASES
    # ------------------------------------------------------------
    if re.search(r"\b(?:initiate|open|launch|access|start)\s+audio\s+(?:interface|settings)\b", raw, re.I):
        return _mk("OPEN_AUDIO_SETTINGS", {}, 1.0, matched_by="alias.audio_interface")

    if re.search(r"\b(?:access|open|launch|start)\s+communication\s+hub\b", raw, re.I):
        return _mk("OPEN_COMMUNICATION_HUB", {}, 1.0, matched_by="alias.communication_hub")

    if re.search(r"\bopen\s+power\b", raw, re.I):
        return _mk("OPEN_POWER_SETTINGS", {}, 0.95, matched_by="system.power")

    if re.match(r"^(?:open|launch|start|show)\s+(?:system\s+)?settings?\b", low):
        return _mk("OPEN_SYSTEM_SETTINGS", {}, 0.98, matched_by="system.settings")

    # ------------------------------------------------------------
    # 13) OPEN / LAUNCH (apps, aliases, websites, paths)
    # ------------------------------------------------------------
    m = re.match(r"^(?:open|launch|start)\s+(.+)$", raw, re.I)
    if m:
        arg = m.group(1).strip()
        cleaned = _clean_app_name(arg)
        cleaned_low = cleaned.lower()

        # URL/domain
        if _is_likely_url(cleaned):
            url = _normalize_url(cleaned)
            return _mk("OPEN_URL", {"url": url}, 0.98, matched_by="open.url_from_open_cmd", entities={"url": url})

        # Website alias
        if cleaned_low in WEBSITE_ALIASES:
            url = WEBSITE_ALIASES[cleaned_low]
            return _mk("OPEN_URL", {"url": url}, 0.98, matched_by="open.website_alias", entities={"url": url, "alias": cleaned_low})

        # App alias / app priority
        canonical_app = APP_ALIASES.get(cleaned_low, cleaned)
        if canonical_app.lower() in DESKTOP_APP_PRIORITY:
            return _mk("OPEN_APP", {"name": canonical_app}, 1.0, matched_by="open.app_priority", entities={"app": canonical_app})

        # Path
        if _is_likely_path(arg):
            expanded = _expand_common_dir(arg)
            return _mk("OPEN_FILE_SYSTEM", {"path": expanded}, 0.95, matched_by="open.path", entities={"path": expanded})

        # Fallback app launch
        return _mk("OPEN_APP", {"name": canonical_app}, 0.9, matched_by="open.app_fallback", entities={"app": canonical_app})

    # ------------------------------------------------------------
    # 14) SHELL EXEC (explicit only)
    # ------------------------------------------------------------
    shell_prefixes = ("execute ", "run cmd ", "bash ", "shell cmd ", "$ ", "terminal: ")
    for pfx in shell_prefixes:
        if low.startswith(pfx):
            cmd = raw[len(pfx):].strip().strip("`")
            if cmd:
                return _mk("SHELL_EXEC", {"cmd": cmd}, 0.95, matched_by="shell.prefix", entities={"cmd": cmd})

    m = re.match(r'^(grep\s+.+)$', raw, re.I)
    if m:
        return _mk("SHELL_EXEC", {"cmd": m.group(1)}, 0.95, matched_by="shell.grep", entities={"cmd": m.group(1)})

    if re.match(r'^(ls|cat|head|tail|find|diff|wc)\s+[~/\.]', raw, re.I):
        return _mk("SHELL_EXEC", {"cmd": raw}, 0.92, matched_by="shell.safeish_builtin", entities={"cmd": raw})

    m = re.match(r'^`([^`]+)`$', raw)
    if m:
        return _mk("SHELL_EXEC", {"cmd": m.group(1)}, 0.93, matched_by="shell.backticks", entities={"cmd": m.group(1)})

    # ------------------------------------------------------------
    # 14b) PROACTIVE DAEMON
    # ------------------------------------------------------------
    if re.search(r"\bproactive\s+(?:status|state|running)\b", low):
        return _mk("PROACTIVE_STATUS", {}, 0.95, matched_by="system.proactive_status")
    if re.search(r"\bproactive\s+(?:start|begin|enable)\b", low):
        return _mk("PROACTIVE_START", {}, 0.95, matched_by="system.proactive_start")
    if re.search(r"\bproactive\s+(?:stop|end|disable)\b", low):
        return _mk("PROACTIVE_STOP", {}, 0.95, matched_by="system.proactive_stop")

    # 14c) CLOSE / KILL APP
    m = re.match(r"^(?:close|quit|kill|exit)\s+(.+)$", raw, re.I)
    if m:
        name = m.group(1).strip()
        return _mk("CLOSE_APP", {"name": name}, 0.9, matched_by="system.close_app")

    # ------------------------------------------------------------
    # 15) DEFAULT CHAT
    # ------------------------------------------------------------
    return _mk("CHAT", {"message": raw}, 0.6, matched_by="fallback.chat")


# MKVIII compatibility shim
def route_intent(text: str) -> Dict[str, Any]:
    result = route(text)
    result.setdefault("args", {})
    result.setdefault("confidence", result.get("confidence", 0.7))
    return result
