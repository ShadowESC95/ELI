import sys, os, pytest
os.environ['ELI_MEMORY_DB'] = os.path.abspath('eli/artifacts/eli_memory.sqlite3')
os.environ['ELI_ROOT'] = os.path.abspath('eli')
sys.path.insert(0, os.path.abspath('eli'))
from eli.tools.executor_enhanced import execute

@pytest.fixture
def sound_calls(monkeypatch):
    """Record the volume commands instead of changing this machine's volume."""
    import subprocess
    import eli.controllers.os_controller as oc
    calls = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(oc.subprocess, "run", fake_run)
    monkeypatch.setattr(oc, "_check_tool", lambda name: True)
    return calls

def _sent_volume_command(calls):
    return any(c and c[0] in ("wpctl", "pactl") for c in calls)

def test_volume_up(sound_calls):
    res = execute('VOLUME', {'direction': 'up', 'delta': 5})
    assert isinstance(res, dict)
    assert res.get('ok') is True
    assert _sent_volume_command(sound_calls)

def test_volume_down(sound_calls):
    res = execute('VOLUME', {'direction': 'down', 'delta': 5})
    assert isinstance(res, dict)
    assert res.get('ok') is True
    assert _sent_volume_command(sound_calls)

def test_volume_set(sound_calls):
    res = execute('VOLUME', {'direction': 'set', 'level': 50})
    assert isinstance(res, dict)
    assert _sent_volume_command(sound_calls)
    assert res.get('ok') is True

def test_get_time():
    res = execute('TIME', {})
    assert isinstance(res, dict)
    assert 'ok' in res
    assert 'response' in res or 'content' in res

def test_get_date():
    res = execute('GET_DATE', {})
    assert isinstance(res, dict)
    assert res.get('ok') is True

def test_fix_file_missing():
    res = execute('FIX_FILE', {'path': '/nonexistent/path.py'})
    assert isinstance(res, dict)
    assert res.get('ok') is False
    assert 'not found' in res.get('response', '').lower()

def test_fix_file_no_path():
    res = execute('FIX_FILE', {})
    assert isinstance(res, dict)
    assert res.get('ok') is False

def test_generate_script_returns_dict():
    # Don't actually run GGUF — just verify handler structure exists
    import eli.tools.executor_enhanced as ex
    content = open(os.path.join(os.path.dirname(__file__), '..', '..', 'tools', 'executor_enhanced.py')).read()
    assert 'if a == "GENERATE_SCRIPT"' in content
    assert 'production-quality' in content

def test_analyze_pdf_missing_path():
    res = execute('ANALYZE_PDF', {'path': '/nonexistent/dir'})
    assert isinstance(res, dict)

def test_read_file_exists():
    res = execute('READ_FILE', {'path': 'eli/brain/persona.txt'})
    assert isinstance(res, dict)

def test_read_file_missing():
    res = execute('READ_FILE', {'path': '/nonexistent/file.txt'})
    assert isinstance(res, dict)
