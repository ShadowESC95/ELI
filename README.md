# ELI

The start of the ELI project: the first version of ELI (Entropic Logical Interpreter), a local AI assistant for Linux.

It has a desktop window with chat, memory, habits, self-improvement and a small code workspace. It runs a local GGUF model through llama.cpp, keeps what you tell it in a local SQLite database, and can act on the PC: open apps, files and websites, control media and volume, take screenshots, and write notes and documents.

Everything runs on your machine: the model, speech recognition (Whisper, through faster-whisper) and memory. The first time you use the microphone, the Whisper model is downloaded once from Hugging Face.

## What you need

- Linux (X11 or Wayland)
- Python 3.10 or newer
- A GGUF model file (any instruct model)
- For voice and system control: `espeak-ng`, `pulseaudio-utils` or `wireplumber`, `portaudio19-dev`, `playerctl`, `xclip` or `wl-clipboard`

## Setup

```bash
git clone https://github.com/ShadowESC95/ELI.git
cd ELI
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

`llama-cpp-python` compiles from source, which needs `build-essential` and `cmake`. A ready-made processor-only build installs faster:

```bash
pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
```

For an NVIDIA card, build it with CUDA instead: `CMAKE_ARGS="-DGGML_CUDA=on" pip install --force-reinstall llama-cpp-python`.

On Ubuntu or Debian, `src/eli/scripts/bootstrap_install.sh` does all of the above, including the system packages, and adds ELI to the app menu. It also installs the background loop as a user service if you run it with `ELI_INSTALL_DAEMON=1`.

## Model

Put a `.gguf` file in `~/.local/share/eli/models` (ELI uses the newest one there), or point to one:

```bash
export ELI_GGUF_MODEL_PATH=/path/to/model.gguf
```

Prompts are built with the chat template stored in the model file, so any instruct model works.

A few side tools (the clipboard and two-machine agents, long documents) use [Ollama](https://ollama.com) instead: set `ELI_MODEL` to a model from `ollama list`. `src/eli/scripts/build_persona_model.sh <model>` builds an `eli-persona` Ollama model with ELI's personality on top of any model.

## Run

| What | Command |
|---|---|
| Desktop window | `./run_eli.sh` or `eli-gui` |
| Check the setup | `eli-cli check` |
| Background learning loop | `eli-daemon` |
| Local API on 127.0.0.1:8081 | `python -m eli.api.server` |
| Tests | `./run_tests_clean.sh` |

The tests never touch your desktop: volume, media, app and screenshot commands are turned into no-ops while they run.

## Settings

Set these in the environment (or in `~/.config/eli/config.json` where noted in the code).

| Setting | Default | |
|---|---|---|
| `ELI_GGUF_MODEL_PATH` | newest `.gguf` in the models folder | the model file |
| `ELI_MODELS_DIR` | `~/.local/share/eli/models` | where to look for models |
| `ELI_N_GPU_LAYERS` | `0` | layers on the graphics card; `-1` puts them all there |
| `ELI_GGUF_N_CTX` | `16384` | context length |
| `ELI_GGUF_CACHE_TYPE_K`, `ELI_GGUF_CACHE_TYPE_V` | model default | e.g. `q8_0` for a smaller cache |
| `ELI_MODEL` | none | Ollama model for the side tools |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | where Ollama is |
| `ELI_USER_NAME` | none | what ELI calls you |
| `ELI_DATA_DIR` | `~/.local/share/eli` | memory, notes, documents, models |
| `ELI_WHISPER`, `ELI_WHISPER_DEVICE` | `base`, `cpu` | speech recognition model size, and `cuda` for an NVIDIA card |
| `ELI_TTS_ENGINE` | `espeak` | or `piper` with `ELI_PIPER_MODEL=/path/to/voice.onnx` |
| `ELI_API_HOST`, `ELI_API_PORT` | `127.0.0.1`, `8081` | the API server; it can run actions, so keep it local |
| `ELI_PROJECTS_DIR`, `ELI_SCRIPTS_DIR` | in the data folder | the code workspace's folders |

`./wipe_memory.sh` empties ELI's memory (it asks first).

## Licence

Apache 2.0, see [LICENSE](LICENSE).
