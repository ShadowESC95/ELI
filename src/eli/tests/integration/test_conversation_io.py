import sys, os, json, pytest
from pathlib import Path
import eli as _eli_pkg
_ELI_DIR = Path(_eli_pkg.__file__).resolve().parent  # src/eli
os.environ['ELI_MEMORY_DB'] = os.path.abspath('eli/artifacts/eli_memory.sqlite3')
sys.path.insert(0, os.path.abspath('eli'))

# These check the files a real ELI session leaves in src/eli/artifacts; a fresh copy has none yet.
_conv = _ELI_DIR / 'artifacts' / 'conversations'
if not (_conv.is_dir() and any(f.suffix == '.json' for f in _conv.iterdir())):
    pytest.skip("needs files from an earlier ELI session in src/eli/artifacts", allow_module_level=True)

def test_conversation_files_exist():
    conv_dir = str(_ELI_DIR / 'artifacts' / 'conversations')
    assert os.path.isdir(conv_dir), "Conversations dir missing"
    files = [f for f in os.listdir(conv_dir) if f.endswith('.json')]
    assert len(files) > 0, "No conversation files saved"

def test_conversation_files_valid_json():
    conv_dir = str(_ELI_DIR / 'artifacts' / 'conversations')
    files = sorted([f for f in os.listdir(conv_dir) if f.endswith('.json')])
    # Check last 3
    for fname in files[-3:]:
        path = os.path.join(conv_dir, fname)
        with open(path) as f:
            data = json.load(f)
        assert isinstance(data, (dict, list)), f"Invalid JSON in {fname}"

def test_artifacts_dir_structure():
    assert (_ELI_DIR / 'artifacts').is_dir(), "artifacts dir missing"
    assert (_ELI_DIR / 'artifacts' / 'eli_memory.sqlite3').is_file(), "DB missing"
    assert os.path.isdir('eli/artifacts/proactive'), "proactive dir missing"

def test_generated_scripts_exist():
    scripts = [f for f in os.listdir('eli/artifacts') if f.endswith('.py')]
    assert len(scripts) > 0, "No generated scripts in artifacts"

def test_proactive_files_exist():
    proactive_dir = str(_ELI_DIR / 'artifacts' / 'proactive')
    expected = ['latest_summary.txt', 'latest_context.txt', 'latest_decision.txt']
    for fname in expected:
        path = os.path.join(proactive_dir, fname)
        assert os.path.isfile(path), f"Missing proactive file: {fname}"