import sys, os, pytest
sys.path.insert(0, os.path.abspath('eli'))

def test_model_env_set():
    model = os.environ.get('ELI_MODEL') or os.path.expanduser('~/.config/eli/config.json')
    assert model is not None

def test_memory_db_env():
    db = os.environ.get('ELI_MEMORY_DB', '')
    # When set, must point to project-scoped DB not home dir
    if db:
        assert '.config/eli/' not in db, f"Memory DB leaking to global path: {db}"

def test_eli_root_env():
    root = os.environ.get('ELI_ROOT', '')
    if root:
        assert os.path.isdir(root), f"ELI_ROOT does not exist: {root}"
