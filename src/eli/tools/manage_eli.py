#!/usr/bin/env python3
"""eli-cli: check the setup, create ELI's folders and database, or start ELI.

Usage: eli-cli [check|init|gui|daemon]
"""

import importlib.util
import sys
from pathlib import Path


def check() -> None:
    from eli.brain import config
    from eli.brain.gguf_inference import get_model_path
    from eli.brain.paths import get_paths

    p = get_paths()
    print(f"Python      {sys.version.split()[0]} ({sys.executable})")
    print(f"Data        {p.data_dir}")
    print(f"Models      {p.models_dir}")
    model = get_model_path()
    print(f"GGUF model  {model or 'none (put a .gguf file in the models folder or set ELI_GGUF_MODEL_PATH)'}")
    print(f"Ollama      {config.ollama_base()} model={config.ollama_model() or 'none (ELI_MODEL)'}")
    for mod, what in (("PySide6", "window"), ("llama_cpp", "GGUF models"), ("speech_recognition", "voice input"),
                      ("pyttsx3", "speech output"), ("fastapi", "API server")):
        ok = importlib.util.find_spec(mod) is not None
        print(f"  {'ok     ' if ok else 'missing'} {mod} ({what})")


def init() -> None:
    from eli.brain.memory import get_memory
    from eli.brain.paths import ensure_dirs

    p = ensure_dirs()
    get_memory()
    print(f"Folders and memory database ready in {p.data_dir}")


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    cmd = (args[0] if args else "check").lower()
    if cmd == "check":
        check()
    elif cmd == "init":
        init()
    elif cmd == "gui":
        from eli.gui.app import main as gui_main
        gui_main()
    elif cmd == "daemon":
        from eli.brain.proactive_daemon import main as daemon_main
        daemon_main()
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
