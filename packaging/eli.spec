# PyInstaller recipe for the ELI app. From the repo root: pyinstaller packaging/eli.spec
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent

datas, binaries, hiddenimports = [], [], []
for package in ("llama_cpp", "faster_whisper", "ctranslate2", "onnxruntime", "av", "tokenizers",
                "speech_recognition", "pyttsx3", "uvicorn"):
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hiddenimports += h

# ELI itself, without its tests and the stand-alone listener/agent scripts that run on import
skip = ("eli.tests", "eli.conftest", "eli.conftest_fixes", "eli.tools.eli_listen",
        "eli.brain.eli_agent", "eli.brain.eli_clipboard_agent")
hiddenimports += collect_submodules("eli", filter=lambda name: not name.startswith(skip))
hiddenimports += ["pyaudio", "pypdf", "numpy", "requests", "platformdirs", "fastapi", "pydantic"]
datas += collect_data_files("eli", excludes=["tests/**", "artifacts/**", "voices/**", "models/**"])
datas += [(str(ROOT / "LICENSE"), ".")]
whisper = ROOT / "build" / "whisper-base"  # the speech model, so voice works offline
if whisper.is_dir():
    datas.append((str(whisper), "whisper-base"))
models = ROOT / "build" / "models"  # the language model ELI ships with, so the app works on its own
if models.is_dir() and any(models.glob("*.gguf")):
    datas.append((str(models), "models"))

a = Analysis(
    [str(ROOT / "packaging" / "eli_app.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "PyQt5", "PyQt6", "matplotlib", "IPython", "torch", "pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="ELI", console=True, strip=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="ELI")
