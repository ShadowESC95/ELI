from typing import Optional, Dict, Any, List
"""
Configuration manager for ELI – stores API keys and user preferences.
Uses a simple JSON file in ELI's config folder (~/.config/eli/config.json).
"""

import os
import sys
import json
from pathlib import Path

def _running_under_pytest() -> bool:
    # pytest sets PYTEST_CURRENT_TEST during test execution.
    # Also check sys.modules in case tests import config before env var is set.
    if os.getenv("PYTEST_CURRENT_TEST"):
        return True
    return "pytest" in sys.modules

def _config_dir() -> Path:
    from .paths import get_paths
    return get_paths().config_dir


CONFIG_PATH = _config_dir() / "config.json"  # ~/.config/eli/config.json unless ELI_CONFIG_DIR is set

def _ensure_config():
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text("{}")

def get(key: str, default=None):
    """Get a configuration value."""
    _ensure_config()
    try:
        with open(CONFIG_PATH) as f:
            data = json.load(f)
        return data.get(key, default)
    except Exception:
        return default

def set(key: str, value):
    """Set a configuration value."""
    _ensure_config()
    try:
        with open(CONFIG_PATH) as f:
            data = json.load(f)
    except Exception:
        data = {}
    data[key] = value
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)
    return True

def delete(key: str):
    """Delete a configuration key."""
    _ensure_config()
    try:
        with open(CONFIG_PATH) as f:
            data = json.load(f)
        if key in data:
            del data[key]
            with open(CONFIG_PATH, "w") as f:
                json.dump(data, f, indent=2)
            return True
    except Exception:
        pass
    return False

def list_keys():
    """List all configuration keys."""
    _ensure_config()
    try:
        with open(CONFIG_PATH) as f:
            data = json.load(f)
        return list(data.keys())
    except Exception:
        return []

# Web automation defaults
def set_web_headless(headless: bool):
    """Set whether to run browser in headless mode (no GUI)."""
    set("web_headless", headless)

def get_web_headless() -> bool:
    """Get current headless mode setting."""
    return get("web_headless", True)

# ---------- GGUF model configuration ----------
def set_gguf_model_path(path: str):
    """Set the path to a GGUF model file."""
    set("gguf_model_path", path)

def get_gguf_model_path() -> Optional[str]:
    """Get the configured GGUF model path.

    Resolution order:
      1) ELI_GGUF_MODEL_PATH (explicit file path)
      2) ELI_MODELS_DIR + ELI_GGUF_MODEL (filename inside models dir)
      3) config key 'gguf_model_path'
      4) PATHS.model (portable/platformdirs)
    """
    env = os.getenv("ELI_GGUF_MODEL_PATH")
    if env:
        return env

    models_dir = os.getenv("ELI_MODELS_DIR")
    model_name = os.getenv("ELI_GGUF_MODEL")
    if models_dir and model_name:
        cand = str((Path(models_dir).expanduser().resolve() / model_name))
        return cand

    v = get("gguf_model_path")
    if v:
        return v

    try:
        from .paths import PATHS
        return str(PATHS.model)
    except Exception:
        return None


def set_gguf_n_gpu_layers(layers: int):
    """Set number of layers to offload to GPU (0 = CPU only)."""
    set("gguf_n_gpu_layers", layers)

def get_gguf_n_gpu_layers() -> int:
    """Get number of GPU layers. Env override: ELI_N_GPU_LAYERS, then config (default 0 = processor only;
    -1 puts every layer on the graphics card)."""
    env = os.getenv('ELI_N_GPU_LAYERS')
    if env is not None:
        try:
            return int(env)
        except Exception:
            pass
    return get('gguf_n_gpu_layers', 0)

def set_gguf_n_ctx(ctx: int):
    """Set context length for GGUF model."""
    set("gguf_n_ctx", ctx)

def get_gguf_n_ctx() -> int:
    """Get context length (default 16384, minimum 8192 for memory-augmented prompts)."""
    val = get("gguf_n_ctx", 16384)
    try:
        val = int(val)
    except (TypeError, ValueError):
        val = 16384
    # Enforce minimum — persona + memory context + conversation history needs space
    if val < 8192:
        print(f"[CONFIG] Warning: gguf_n_ctx={val} is too small. Using minimum 8192.")
        val = 8192
    return val

def set_gguf_n_batch(batch: int):
    """Set batch size for GGUF inference."""
    set("gguf_n_batch", batch)

def get_gguf_n_batch() -> int:
    """Get batch size for GGUF inference (default 256). Env override: ELI_GGUF_N_BATCH."""
    env = os.getenv('ELI_GGUF_N_BATCH')
    if env is not None:
        try:
            return int(env)
        except Exception:
            pass
    return get('gguf_n_batch', 256)

# ---------- ELI Persona ----------
def set_persona(text: str):
    """Set ELI's system prompt / personality."""
    set("eli_persona", text)

def get_persona() -> str:
    """Get the current persona. Returns default if not set."""
    default = (
        "You are ELI, an autonomous cognitive OS agent. "
        "You control the user's computer, manage files, launch apps, "
        "browse the web, and automate habits. "
        "Be concise, accurate, and helpful."
    )
    return get("eli_persona", default)

# ---------- Generation Parameters ----------
def set_temperature(value: float):
    """Set default temperature (0.0–2.0)."""
    set("temperature", value)

def get_temperature() -> float:
    """Get default temperature (default: 0.55)."""
    # If user explicitly set a value in config, that should win.
    cur = get('temperature', None)
    if cur is not None:
        try:
            return float(cur)
        except Exception:
            pass
    env = os.getenv('ELI_TEMP') or os.getenv('ELI_TEMPERATURE')
    if env:
        try:
            return float(env)
        except Exception:
            pass
    return 0.55

def set_top_p(value: float):
    """Set default top‑p (0.0–1.0)."""
    set("top_p", value)

def get_top_p() -> float:
    """Get default top‑p (default: 0.9)."""
    return get("top_p", 0.9)

def set_top_k(value: int):
    """Set default top‑k (1–100)."""
    set("top_k", value)

def get_top_k() -> int:
    """Get default top‑k (default: 40)."""
    return get("top_k", 40)

def set_repeat_penalty(value: float):
    """Set default repeat penalty (1.0–2.0)."""
    set("repeat_penalty", value)

def get_repeat_penalty() -> float:
    """Get default repeat penalty (default: 1.15)."""
    return get("repeat_penalty", 1.15)

def set_num_predict(value: int):
    """Set default max tokens to generate."""
    set("num_predict", value)

def get_num_predict() -> int:
    """Get default generation length (default: 4096)."""
    cur = get('num_predict', None)
    if cur is not None:
        try:
            return int(cur)
        except Exception:
            pass
    env = os.getenv('ELI_NUM_PREDICT')
    if env:
        try:
            return int(env)
        except Exception:
            pass
    return 4096


# Allow environment variable to override gguf_model_path
_original_get = get
def get_with_env(key, default=None):
    if key == 'gguf_model_path':
        env_path = os.environ.get('ELI_GGUF_MODEL_PATH')
        if env_path:
            return env_path
    return _original_get(key, default)

get = get_with_env


# ELI Persona - FORCED for all interactions
ELI_PERSONA = """You are ELI (Enhanced Learning Interface): The user's brutally honest, nerdy, sarcastic research partner and systems engineer.

Your job is not to be nice (although you don't have to be an arsehole either). Your job is to be correct, useful, and real.
You don't flatter. You don't "validate." You don't do corporate HR tone.
You do rigorous thinking, practical execution, analysis, innovative ideas that try to connect the bigger picture.

When a user provides you with a query:
1. ANALYSE the request
2. SEARCH memory for relevance to their work
3. ANALYSE all available information
4. FIND CONNECTIONS between possible suggestions
5. IDENTIFY 3 inconsistencies or high priority patterns
6. RESPOND with precision

PERSONALITY:
- Voice: calm, confident, dry, witty. Dark humor and shock value.
- Profanity allowed if user swears first.
- Address user by name. Remember it.
- "Now prove it." is your catchphrase.
- Wrong? Say it plainly. Unsure? Say so. Then show the fix.

You are ELI. Not "Assistant." Not "AI." ELI.

CORE VALUES:
1) Truth > comfort. Accuracy > emotions.
2) Reproducibility > one-off hacks.
3) Confidentiality > convenience.
4) Scientific method: observation ≠ inference ≠ speculation.

Remember: If it's not rigorous, it's not physics. If it's not testable, it's not science. If it's not documented, it never happened.
"""

def get_eli_persona() -> str:
    """Get the forced ELI persona."""
    return ELI_PERSONA


# ---------- Ollama (used when no GGUF model is set) ----------
def ollama_base() -> str:
    """Where Ollama answers. OLLAMA_HOST is often set for the server as "0.0.0.0" or "host:port"."""
    raw = (os.environ.get("ELI_OLLAMA_HOST") or os.environ.get("OLLAMA_BASE_URL")
           or os.environ.get("OLLAMA_HOST") or "127.0.0.1:11434").strip().rstrip("/")
    if "://" not in raw:
        raw = "http://" + raw
    return raw.replace("://0.0.0.0", "://127.0.0.1")


def ollama_model() -> str:
    """The Ollama model to chat with: ELI_CHAT_MODEL, ELI_MODEL or OLLAMA_MODEL ("" when none is set)."""
    return (os.environ.get("ELI_CHAT_MODEL") or os.environ.get("ELI_MODEL")
            or os.environ.get("OLLAMA_MODEL") or "").strip()
