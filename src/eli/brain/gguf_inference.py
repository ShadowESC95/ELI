"""
GGUF inference for ELI. Prompts are built with the chat template stored in the
GGUF file, so any instruct model works (Qwen, Llama, Mistral, Phi, Gemma, ...).

FULL FIXED VERSION (no hardcoded paths, no forced parameter lowering):
- Adds optional KV-cache quantization via env:
    ELI_GGUF_CACHE_TYPE_K (e.g. q4_0, q8_0)
    ELI_GGUF_CACHE_TYPE_V (e.g. q4_0, q8_0)
  This is the main way to keep large n_ctx on big models without llama_context allocation failure.

- Adds optional runtime knobs (env) without changing your defaults:
    ELI_GGUF_THREADS
    ELI_GGUF_USE_MMAP
    ELI_GGUF_USE_MLOCK
    ELI_GGUF_VERBOSE

- Adds compatibility fallback: if llama-cpp-python doesn't accept the extra kwargs,
  it retries without them (keeping your model + n_ctx unchanged).
"""

from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Optional, Dict, Any, Generator, Union

from llama_cpp import Llama, LlamaGrammar


def _env_int(name: str, default: Optional[int] = None) -> Optional[int]:
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    try:
        return int(v)
    except Exception:
        print(f"[GGUF] Warning: {name}={v!r} is not an int; ignoring")
        return default


def _env_bool(name: str, default: Optional[bool] = None) -> Optional[bool]:
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    v = v.strip().lower()
    if v in ("1", "true", "yes", "y", "on"):
        return True
    if v in ("0", "false", "no", "n", "off"):
        return False
    print(f"[GGUF] Warning: {name}={v!r} is not a bool; ignoring")
    return default


def get_model_path() -> Optional[Path]:
    # Strongest override: explicit file path
    env_path = os.environ.get("ELI_GGUF_MODEL_PATH")
    if env_path:
        p = Path(env_path).expanduser()
        if p.exists():
            return p
        print(f"[GGUF] Warning: ELI_GGUF_MODEL_PATH={p} does not exist")

    # Next: (models dir, filename) pair
    # This allows redistributable installs to ship models separately while keeping config clean.
    model_name = os.environ.get("ELI_GGUF_MODEL")
    models_dir = os.environ.get("ELI_MODELS_DIR")
    if model_name and models_dir:
        cand = (Path(models_dir).expanduser().resolve() / model_name)
        if cand.exists():
            return cand

    # Next: PATHS.model (uses ELI_MODELS_DIR / portable dirs / platformdirs)
    try:
        from .paths import PATHS
        cand = PATHS.model
        if cand and Path(cand).exists():
            return Path(cand)
    except Exception:
        pass

    # Next: config key 'gguf_model_path'
    from . import config
    path = config.get("gguf_model_path")
    if path:
        p = Path(path).expanduser()
        if p.exists():
            return p

    return None


_llm: Optional[Llama] = None


def load_model() -> Optional[Llama]:
    global _llm
    if _llm is not None:
        return _llm

    model_path = get_model_path()
    if not model_path:
        print("[GGUF] No model path configured – using Ollama fallback.")
        return None

    from . import config

    # Priority: environment variable > config default
    n_ctx = int(os.environ.get("ELI_GGUF_N_CTX", config.get_gguf_n_ctx()))

    # These are already wired in your config (and may read env like ELI_N_GPU_LAYERS)
    n_gpu_layers = config.get_gguf_n_gpu_layers()
    n_batch = config.get_gguf_n_batch()

    # Extra knobs (optional, do not change your model/settings unless you set env vars)
    n_threads = _env_int("ELI_GGUF_THREADS", os.cpu_count() or 4) or (os.cpu_count() or 4)
    use_mmap = _env_bool("ELI_GGUF_USE_MMAP", None)
    use_mlock = _env_bool("ELI_GGUF_USE_MLOCK", None)
    verbose = bool(_env_bool("ELI_GGUF_VERBOSE", False))

    # KV-cache quantization (optional, keeps n_ctx, reduces memory footprint)
    cache_k = os.environ.get("ELI_GGUF_CACHE_TYPE_K")
    cache_v = os.environ.get("ELI_GGUF_CACHE_TYPE_V")

    print(f"[GGUF] Loading model from {model_path}...")
    print(f"[GGUF] Params: ctx={n_ctx}, gpu_layers={n_gpu_layers}, batch={n_batch}, threads={n_threads}")
    if cache_k or cache_v:
        print(f"[GGUF] KV cache quant: K={cache_k or '(default)'} V={cache_v or '(default)'}")
    if use_mmap is not None or use_mlock is not None:
        print(f"[GGUF] mmap/mlock: use_mmap={use_mmap} use_mlock={use_mlock}")

    # Build kwargs, then try to construct Llama
    kwargs: Dict[str, Any] = dict(
        model_path=str(model_path),
        n_ctx=n_ctx,
        n_threads=n_threads,
        n_gpu_layers=n_gpu_layers,
        n_batch=n_batch,
        verbose=verbose,
    )

    # Only include if set; older bindings may not accept them.
    if use_mmap is not None:
        kwargs["use_mmap"] = bool(use_mmap)
    if use_mlock is not None:
        kwargs["use_mlock"] = bool(use_mlock)

    # KV-cache quantization: llama-cpp-python takes ggml type ids as type_k / type_v
    # (it ignores unknown names such as cache_type_k without an error)
    import llama_cpp
    for name, key in ((cache_k, "type_k"), (cache_v, "type_v")):
        if name:
            ggml_type = getattr(llama_cpp, f"GGML_TYPE_{name.strip().upper()}", None)
            if ggml_type is None:
                print(f"[GGUF] Warning: unknown KV cache type {name!r}; using the default")
            else:
                kwargs[key] = ggml_type
    if "type_v" in kwargs:
        kwargs["flash_attn"] = True  # a quantized V cache needs flash attention

    try:
        _llm = Llama(**kwargs)
        print("[GGUF] Model loaded successfully.")
        return _llm

    except TypeError as e:
        # Compatibility: installed llama-cpp-python may not support cache_type_* or mmap/mlock args
        print(f"[GGUF] Llama() arg mismatch: {e} (retrying without optional kwargs)")
        kwargs.pop("type_k", None)
        kwargs.pop("type_v", None)
        kwargs.pop("flash_attn", None)
        kwargs.pop("use_mmap", None)
        kwargs.pop("use_mlock", None)
        try:
            _llm = Llama(**kwargs)
            print("[GGUF] Model loaded successfully (compat retry).")
            return _llm
        except Exception as e2:
            print(f"[GGUF] Failed to load model after compat retry: {e2}")
            return None

    except Exception as e:
        print(f"[GGUF] Failed to load model: {e}")
        return None


def _messages(system: Optional[str], user: str) -> list:
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": user})
    return msgs


def _chat(llm: Llama, system: Optional[str], user: str, **kwargs):
    """Run the model's own chat template. Some templates have no system role;
    the system text then goes in front of the user's message."""
    try:
        return llm.create_chat_completion(messages=_messages(system, user), **kwargs)
    except Exception as e:
        if not system:
            raise
        print(f"[GGUF] Chat template refused a system message ({e}); folding it into the user turn")
        return llm.create_chat_completion(messages=_messages(None, f"{system}\n\n{user}"), **kwargs)


def generate(
    prompt: str,
    system: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    top_p: Optional[float] = None,
    top_k: Optional[int] = None,
    repeat_penalty: Optional[float] = None,
    stop: Optional[list] = None,
    stream: bool = False,
    grammar: Optional[LlamaGrammar] = None,
) -> Union[Generator[Dict[str, Any], None, None], Dict[str, Any]]:
    from . import config

    if system is None:
        system = config.get_persona()

    if temperature is None:
        temperature = config.get_temperature()
    if max_tokens is None:
        max_tokens = config.get_num_predict()
    if top_p is None:
        top_p = config.get_top_p()
    if top_k is None:
        top_k = config.get_top_k()
    if repeat_penalty is None:
        repeat_penalty = config.get_repeat_penalty()

    llm = load_model()
    if llm is None:
        raise RuntimeError("GGUF model not available")

    params = dict(
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        top_k=top_k,
        repeat_penalty=repeat_penalty,
        stop=stop or None,
        grammar=grammar,
    )

    if stream:
        for chunk in _chat(llm, system, prompt, stream=True, **params):
            text = (chunk["choices"][0].get("delta") or {}).get("content")
            if text:
                yield {"response": text}
    else:
        response = _chat(llm, system, prompt, stream=False, **params)
        yield {"response": response["choices"][0]["message"].get("content") or ""}


_json_grammar = LlamaGrammar.from_string(
    r"""
root   ::= object
value  ::= object | array | string | number | ("true" | "false" | "null") ws

object ::=
  "{" ws (
            string ":" ws value
    ("," ws string ":" ws value)*
  )? "}" ws

array  ::=
  "[" ws (
            value
    ("," ws value)*
  )? "]" ws

string ::=
  "\"" (
    [^"\\] |
    "\\" (["\\/bfnrt] | "u" [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F])
  )* "\"" ws

number ::= ("-"? ([0-9] | [1-9] [0-9]*)) ("." [0-9]+)? ([eE] [-+]? [0-9]+)? ws
ws ::= [ \t\n]*
"""
)


def generate_json(
    prompt: str,
    system: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    top_p: Optional[float] = None,
    top_k: Optional[int] = None,
    repeat_penalty: Optional[float] = None,
    **kwargs,
) -> dict:
    if system is None:
        from . import config
        system = config.get_persona() + " Output ONLY valid JSON."

    llm = load_model()
    if llm is None:
        raise RuntimeError("GGUF model not available")

    from . import config
    if temperature is None:
        temperature = config.get_temperature()
    if max_tokens is None:
        max_tokens = config.get_num_predict()
    if top_p is None:
        top_p = config.get_top_p()
    if top_k is None:
        top_k = config.get_top_k()
    if repeat_penalty is None:
        repeat_penalty = config.get_repeat_penalty()

    try:
        response = _chat(
            llm, system, prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            top_k=top_k,
            repeat_penalty=repeat_penalty,
            grammar=_json_grammar,
            **kwargs,
        )
        content = response["choices"][0]["message"].get("content") or ""
        return json.loads(content)
    except Exception as e:
        print(f"[GGUF] JSON generation failed: {e}")
        raise RuntimeError(f"Failed to generate JSON: {e}") from e


def chat_completion(prompt: str, system: Optional[str] = None, **kwargs) -> str:
    generator = generate(prompt=prompt, system=system, stream=False, **kwargs)
    for chunk in generator:
        response = chunk["response"]
        # Clean up stray special tokens
        response = response.replace("[INST]", "").replace("[/INST]", "").replace("<s>", "").replace("</s>", "")
        # Clean up other prefixes
        response = response.replace("Assistant:", "ELI:").replace("assistant:", "ELI:").replace("AI:", "ELI:")
        return response.strip()
    return ""


# ---- Safe backward-compat wrappers for legacy cognitive_engine callers ----
# Marker: _ELI_SAFE_COMPAT_WRAPPERS_V1

_chat_completion_impl = chat_completion
_generate_impl = generate
_generate_json_impl = generate_json


def _coerce_chat_args(*args, **kwargs):
    # Supports:
    #   chat_completion(system_prompt, user_prompt, ...)
    #   chat_completion(prompt="...", system="...", ...)
    #   chat_completion("user text", system="...")
    system_prompt = kwargs.pop("system_prompt", None)
    user_prompt = kwargs.pop("user_prompt", None)

    if "system" in kwargs and system_prompt is None:
        system_prompt = kwargs.pop("system")
    if "prompt" in kwargs and user_prompt is None:
        user_prompt = kwargs.pop("prompt")

    if len(args) == 2 and system_prompt is None and user_prompt is None:
        system_prompt, user_prompt = args
    elif len(args) == 1 and user_prompt is None:
        user_prompt = args[0]
    elif len(args) > 2:
        if system_prompt is None:
            system_prompt = args[0]
        if user_prompt is None:
            user_prompt = args[1]

    if system_prompt is None:
        system_prompt = ""
    if user_prompt is None:
        user_prompt = ""

    return str(system_prompt), str(user_prompt), kwargs


def chat_completion(*args, **kwargs) -> str:
    system_prompt, user_prompt, rest = _coerce_chat_args(*args, **kwargs)

    # Map legacy names to your current implementation
    if "num_predict" in rest and "max_tokens" not in rest:
        rest["max_tokens"] = rest.pop("num_predict")

    # Ignore model_path in this implementation (current file resolves path internally)
    rest.pop("model_path", None)

    return _chat_completion_impl(prompt=user_prompt, system=system_prompt, **rest)


def generate(*args, **kwargs):
    return _generate_impl(*args, **kwargs)


def generate_json(*args, **kwargs):
    return _generate_json_impl(*args, **kwargs)
