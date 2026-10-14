ELI (Entropic Logical Interpreter), the first version: a local AI assistant for Linux with a desktop window, memory, voice and system control.

## Get started

Download `ELI-0.1.1-x86_64.AppImage`, make it executable and open it:

```bash
chmod +x ELI-0.1.1-x86_64.AppImage
./ELI-0.1.1-x86_64.AppImage
```

That one file is everything ELI needs: Python and all its libraries, llama.cpp, the window, a language model (Qwen2.5 1.5B Instruct, Apache 2.0, from [Qwen](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF)) and the Whisper speech model. Nothing leaves your machine.

To use another model, put any instruct model in GGUF format in `~/.local/share/eli-ai/models` or beside the AppImage. ELI uses that one instead of the one it ships with.

| Command | |
|---|---|
| `./ELI-0.1.1-x86_64.AppImage` | the desktop window |
| `./ELI-0.1.1-x86_64.AppImage --cli check` | check the setup |
| `./ELI-0.1.1-x86_64.AppImage --daemon` | the background learning loop |
| `./ELI-0.1.1-x86_64.AppImage --api` | the local API on 127.0.0.1:8081 |

## Its own folders and settings

ELI keeps everything in its own folders, apart from any other ELI version: memory, notes and documents in `~/.local/share/eli-ai`, settings in `~/.config/eli-ai`.

Settings go in `~/.config/eli-ai/settings` as `KEY=VALUE` lines (the README lists them), for example `ELI_N_GPU_LAYERS=-1`. A variable named with `ELI_AI_` in place of `ELI_` works too: `ELI_AI_N_GPU_LAYERS=-1 ./ELI-0.1.1-x86_64.AppImage`. Plain `ELI_` variables belong to other ELI versions and are ignored.

This build runs the model on the processor. For an NVIDIA card, install from source with a CUDA build of llama-cpp-python (see the README) and set `ELI_N_GPU_LAYERS=-1`.

## Fixed since 0.1.0

- 0.1.0 needed the model as a second download; on its own it could not chat. The model is inside now.
- Closing the window crashed: ELI tried to save the conversation inside the AppImage, which is read-only. Everything ELI writes now goes to its own data folder.
- 0.1.0 used the same folders as later ELI versions (`~/.local/share/eli`, `~/.config/eli`) and some shared files in the home folder. It has its own now.
- The speech model's onnxruntime queued usage telemetry for Microsoft. That is switched off.

## Also here

- `eli_ai-0.1.1-py3-none-any.whl` and `eli_ai-0.1.1.tar.gz`: ELI as a Python package
- `SHA256SUMS.txt`: checksums of every file

## Needs

- Linux on x86_64 with glibc 2.35 or newer (Ubuntu 22.04, Debian 12, Fedora 36 or later)
- About 2 GB of memory for the model
- `espeak-ng` for spoken replies; PulseAudio or PipeWire for sound
- If your system will not open AppImages, run it with `--appimage-extract-and-run`

Apache 2.0.
