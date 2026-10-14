#!/usr/bin/env python3
"""
Helper script to configure ELI to use a local GGUF model.
Run: python3 setup_gguf_model.py /path/to/your/model.gguf [--gpu-layers N]
"""

import sys
import os
import argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eli.brain import config

def main():
    parser = argparse.ArgumentParser(description="Configure ELI to use a GGUF model.")
    parser.add_argument("model_path", help="Path to the GGUF model file")
    parser.add_argument("--gpu-layers", type=int, default=0, help="Number of layers to offload to GPU (0 = CPU only)")
    parser.add_argument("--ctx", type=int, default=4096, help="Context length (default: 4096)")
    args = parser.parse_args()

    path = Path(args.model_path).expanduser().resolve()
    if not path.exists():
        print(f"❌ Model file not found: {path}")
        sys.exit(1)

    config.set_gguf_model_path(str(path))
    config.set_gguf_n_gpu_layers(args.gpu_layers)
    config.set_gguf_n_ctx(args.ctx)

    print(f"✅ GGUF model configured: {path}")
    print(f"   GPU layers: {args.gpu_layers}")
    print(f"   Context length: {args.ctx}")
    print("   ELI will now use this model for intent parsing and chat (fallback to Ollama if loading fails).")

if __name__ == "__main__":
    main()
