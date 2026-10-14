# brain/response_sanitizer.py
from __future__ import annotations
import re
from typing import Any, Dict

ROLE_PREFIX_RE = re.compile(
    r"^\s*(user|assistant|system|eli)\s*:\s*",
    re.IGNORECASE
)

TRANSCRIPT_LINE_RE = re.compile(
    r"^\s*\[\d{1,2}:\d{2}(?::\d{2})?\]\s*(user|assistant|system|eli)\b.*$",
    re.IGNORECASE
)

BRACKET_ROLE_ONLY_RE = re.compile(
    r"^\s*\[\d{1,2}:\d{2}(?::\d{2})?\]\s*(user|assistant|system|eli)\s*$",
    re.IGNORECASE
)

def extract_text(resp: Any) -> str:
    """Normalize common model response shapes into text."""
    if isinstance(resp, str):
        return resp.strip()

    if isinstance(resp, dict):
        for k in ("content", "response", "text"):
            v = resp.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()

        msg = resp.get("message")
        if isinstance(msg, dict):
            v = msg.get("content")
            if isinstance(v, str) and v.strip():
                return v.strip()

        choices = resp.get("choices")
        if isinstance(choices, list) and choices:
            c0 = choices[0] or {}
            if isinstance(c0, dict):
                v = (c0.get("message") or {}).get("content")
                if isinstance(v, str) and v.strip():
                    return v.strip()
                v = c0.get("text")
                if isinstance(v, str) and v.strip():
                    return v.strip()

    return ""

def sanitize_assistant_text(text: str) -> str:
    """
    Remove leaked transcript/role lines and keep only assistant natural text.
    """
    if not text:
        return ""

    kept = []
    for raw_ln in text.splitlines():
        ln = raw_ln.strip()

        # Drop obvious transcript markers / role labels
        if ROLE_PREFIX_RE.match(ln):
            continue
        if TRANSCRIPT_LINE_RE.match(ln):
            continue
        if BRACKET_ROLE_ONLY_RE.match(ln):
            continue

        # Drop empty scaffold fragments
        if ln in {"ELI:", "Assistant:", "User:", "System:"}:
            continue

        kept.append(raw_ln.rstrip())

    out = "\n".join(x for x in kept if x.strip()).strip()

    # Final guard: reject pure metadata-ish leftovers
    if re.fullmatch(r"[\[\]\d:\sA-Za-z_-]+", out or ""):
        # e.g. "[21:09] User"
        if any(tok in out.lower() for tok in ("user", "assistant", "system", "eli")):
            return ""

    return out

def finalize_assistant_reply(raw_model_resp: Any) -> Dict[str, Any]:
    raw = extract_text(raw_model_resp)
    clean = sanitize_assistant_text(raw)

    if not clean:
        clean = "I hit a response-format error. Please retry your last message."

    return {
        "ok": True,
        "raw": raw,
        "content": clean,
        "response": clean,
    }
