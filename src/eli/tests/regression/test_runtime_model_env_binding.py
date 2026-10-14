import sys, os, pytest
from pathlib import Path
import eli as _eli_pkg
_ELI_DIR = Path(_eli_pkg.__file__).resolve().parent  # <-- THIS is the real project root (src/eli)
_PROJECT_ROOT = _ELI_DIR.parent                      # src
sys.path.insert(0, os.path.abspath('eli'))

def test_run_eli_exports_memory_db():
    with open('run_eli.sh') as f:
        content = f.read()
    assert 'ELI_MEMORY_DB' in content, "run_eli.sh not exporting ELI_MEMORY_DB"

def test_run_eli_exports_eli_root():
    with open('run_eli.sh') as f:
        content = f.read()
    assert 'ELI_ROOT' in content, "run_eli.sh not exporting ELI_ROOT"

def test_generate_script_prompt_is_rigorous():
    with open((_ELI_DIR / 'tools' / 'executor_enhanced.py').as_posix()) as f:
        content = f.read()
    assert 'production-quality' in content, "GENERATE_SCRIPT prompt not upgraded"
    assert 'SI units' in content or 'mathematical notation' in content, \
        "GENERATE_SCRIPT prompt missing physics/math requirements"