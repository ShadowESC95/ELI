import sys, os, pytest
from pathlib import Path
import eli as _eli_pkg
_ELI_DIR = Path(_eli_pkg.__file__).resolve().parent  # <-- THIS is the real project root (src/eli)
_PROJECT_ROOT = _ELI_DIR.parent                      # src
sys.path.insert(0, os.path.abspath('eli'))

def _launcher():
    import importlib.util
    path = _PROJECT_ROOT.parent / "packaging" / "eli_app.py"
    spec = importlib.util.spec_from_file_location("eli_app_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_run_eli_starts_through_the_launcher():
    content = (_PROJECT_ROOT.parent / "run_eli.sh").read_text()
    assert "packaging/eli_app.py" in content, "run_eli.sh must start ELI through its launcher"


def test_launcher_keeps_only_this_apps_settings(tmp_path, monkeypatch):
    """ELI_ variables exported for another ELI version are dropped; ELI_AI_ ones and the
    settings file are this app's, and ELI_AI_ wins over the file."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    (tmp_path / "eli-ai").mkdir()
    (tmp_path / "eli-ai" / "settings").write_text(
        "# mine\nexport ELI_N_GPU_LAYERS=10\nELI_USER_NAME='Sam'\nOTHER=1\n")
    monkeypatch.setenv("ELI_FULL_CONTROL", "1")          # another version's
    monkeypatch.setenv("ELI_MEMORY_DB", "/elsewhere.db")  # another version's
    monkeypatch.setenv("ELI_AI_N_GPU_LAYERS", "-1")       # this app's, wins over the file
    _launcher().own_settings()
    assert "ELI_FULL_CONTROL" not in os.environ
    assert "ELI_MEMORY_DB" not in os.environ
    assert os.environ["ELI_N_GPU_LAYERS"] == "-1"
    assert os.environ["ELI_USER_NAME"] == "Sam"
    assert "OTHER" not in os.environ or os.environ.get("OTHER") != "1"

def test_generate_script_prompt_is_rigorous():
    with open((_ELI_DIR / 'tools' / 'executor_enhanced.py').as_posix()) as f:
        content = f.read()
    assert 'production-quality' in content, "GENERATE_SCRIPT prompt not upgraded"
    assert 'SI units' in content or 'mathematical notation' in content, \
        "GENERATE_SCRIPT prompt missing physics/math requirements"