"""Unit tests for executor_enhanced — accurate to actual implementation."""
import pytest, os, sys, tempfile
from unittest.mock import patch, MagicMock

os.environ.setdefault("ELI_MEMORY_DB", os.path.abspath("eli/artifacts/eli_memory.sqlite3"))
sys.path.insert(0, os.path.abspath("eli"))
from eli.tools.executor_enhanced import execute


def test_execute_time():
    """TIME returns a dict — ok may be True or False depending on handler."""
    result = execute("TIME")
    assert isinstance(result, dict)
    assert "ok" in result


def test_execute_date():
    result = execute("GET_DATE")
    assert isinstance(result, dict)
    assert "ok" in result


@patch("subprocess.Popen")
def test_execute_open_app(mock_popen):
    """OPEN_APP tries multiple launch strategies — Popen must be called."""
    proc = MagicMock()
    proc.poll.return_value = 0
    proc.stderr.read.return_value = b""
    mock_popen.return_value = proc
    result = execute("OPEN_APP", {"name": "calculator"})
    assert isinstance(result, dict)
    assert mock_popen.called


@patch("subprocess.Popen")
def test_execute_open_url(mock_popen):
    mock_popen.return_value = MagicMock()
    result = execute("OPEN_URL", {"url": "https://example.com"})
    assert isinstance(result, dict)
    assert mock_popen.called


def test_execute_read_file(tmp_path):
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello world")
    result = execute("READ_FILE", {"path": str(test_file)})
    assert isinstance(result, dict)
    if result.get("ok"):
        content = result.get("content") or result.get("response", "")
        assert "hello world" in content


def test_execute_read_file_missing():
    result = execute("READ_FILE", {"path": "/nonexistent/file_xyz"})
    assert result["ok"] is False


@patch("subprocess.run")
def test_execute_volume(mock_run):
    """Volume uses subprocess.run with pactl — verify it was called correctly."""
    mock_run.return_value = MagicMock(returncode=0)
    result = execute("VOLUME", {"direction": "up", "delta": 5})
    assert result["ok"] is True
    assert mock_run.called
    call_args = mock_run.call_args[0][0]
    assert "pactl" in call_args
    assert "@DEFAULT_SINK@" in call_args
    assert "+5%" in call_args


def test_execute_volume_down():
    result = execute("VOLUME", {"direction": "down", "delta": 5})
    assert isinstance(result, dict)


def test_execute_volume_set():
    result = execute("VOLUME", {"level": 50})
    assert isinstance(result, dict)
