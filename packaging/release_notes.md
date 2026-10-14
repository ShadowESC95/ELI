The first release of ELI (Entropic Logical Interpreter): a local AI assistant for Linux with a desktop window, memory, voice and system control.

## Get started

Download these two files into the same folder:

- `ELI-0.1.0-x86_64.AppImage`: the app
- `qwen2.5-1.5b-instruct-q4_k_m.gguf`: a small language model for it to run (Qwen2.5 1.5B Instruct, Apache 2.0, from [Qwen](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF))

Then make the app executable and open it:

```bash
chmod +x ELI-0.1.0-x86_64.AppImage
./ELI-0.1.0-x86_64.AppImage
```

Everything else is inside the AppImage: Python and all its libraries, llama.cpp, the window and the Whisper speech model, so speech recognition works offline. Nothing leaves your machine.

ELI works with any instruct model in GGUF format. It uses a `.gguf` file beside the AppImage, or the newest one in `~/.local/share/eli/models`, or the one `ELI_GGUF_MODEL_PATH` names.

| Command | |
|---|---|
| `./ELI-0.1.0-x86_64.AppImage` | the desktop window |
| `./ELI-0.1.0-x86_64.AppImage --cli check` | check the setup |
| `./ELI-0.1.0-x86_64.AppImage --daemon` | the background learning loop |
| `./ELI-0.1.0-x86_64.AppImage --api` | the local API on 127.0.0.1:8081 |

ELI keeps its memory, notes and documents in `~/.local/share/eli` and its settings in `~/.config/eli`.

This build runs the model on the processor. For an NVIDIA card, install from source with a CUDA build of llama-cpp-python (see the README) and set `ELI_N_GPU_LAYERS=-1`.

## Also here

- `eli_ai-0.1.0-py3-none-any.whl` and `eli_ai-0.1.0.tar.gz`: ELI as a Python package (`pip install eli_ai-0.1.0-py3-none-any.whl`)
- `SHA256SUMS.txt`: checksums of every file

## Needs

- Linux on x86_64 with glibc 2.35 or newer (Ubuntu 22.04, Debian 12, Fedora 36 or later)
- About 2 GB of memory for the model
- `espeak-ng` for spoken replies; PulseAudio or PipeWire for sound
- If your system will not open AppImages, run it with `--appimage-extract-and-run`

Apache 2.0.
