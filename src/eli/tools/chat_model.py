"""
Chat model interface for ELI – supports GGUF direct inference and Ollama fallback.
"""

import json
import os
import requests
from typing import Optional, Generator, Dict, Any

from eli.brain import config as eli_config

OLLAMA_HOST = eli_config.ollama_base()
DEFAULT_CHAT_MODEL = eli_config.ollama_model()

def chat_response_stream(prompt: str, model: Optional[str] = None, **kwargs) -> Generator[str, None, None]:
    """
    Stream chat response – try GGUF first, fallback to Ollama.
    Yields token strings as they arrive.
    """
    # ---------- GGUF path ----------
    try:
        from eli.brain.gguf_inference import generate
        # Check if GGUF model is configured and loadable
        generator = generate(
            prompt=prompt,
            system=None,
            temperature=kwargs.get('temperature', 0.7),
            max_tokens=kwargs.get('num_predict', 512),
            stop=kwargs.get('stop', []),
            stream=True
        )
        for chunk in generator:
            if "response" in chunk:
                yield chunk["response"]
        return  # success – stop here
    except ImportError:
        # gguf_inference not available – skip
        pass
    except Exception as e:
        print(f"[Chat] GGUF stream failed: {e}, falling back to Ollama")

    # ---------- Ollama fallback ----------
    model = model or DEFAULT_CHAT_MODEL
    if not model:
        yield ("[No model set: put a .gguf file in the models folder (or set ELI_GGUF_MODEL_PATH), "
               "or set ELI_MODEL to an Ollama model you have pulled]")
        return
    url = f"{OLLAMA_HOST}/api/chat"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        **kwargs
    }
    timeout = kwargs.get("timeout", (10, 3600))
    try:
        with requests.post(url, json=payload, stream=True, timeout=timeout) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if line:
                    try:
                        data = json.loads(line)
                        if "message" in data and "content" in data["message"]:
                            yield data["message"]["content"]
                    except Exception:
                        continue
    except Exception as e:
        yield f"[Chat error: {e}]"

def chat_completion(prompt: str, model: Optional[str] = None, **kwargs) -> Dict[str, Any]:
    """
    Non‑streaming chat completion – returns full response dict.
    """
    full = ""
    for chunk in chat_response_stream(prompt, model, **kwargs):
        full += chunk
    return {
        "ok": True,
        "model": model or DEFAULT_CHAT_MODEL,
        "content": full,
        "response": full
    }
