"""Test config module with temporary files."""

import pytest
import tempfile
import json
from pathlib import Path
from eli.brain import config

@pytest.fixture(autouse=True)
def temp_config():
    """Redirect config to a temporary file."""
    with tempfile.NamedTemporaryFile(mode="w+", suffix=".json") as tmp:
        original_path = config.CONFIG_PATH
        config.CONFIG_PATH = Path(tmp.name)
        yield
        config.CONFIG_PATH = original_path

def test_set_get():
    config.set("test_key", "test_value")
    assert config.get("test_key") == "test_value"

def test_delete():
    config.set("test_key", "test_value")
    config.delete("test_key")
    assert config.get("test_key") is None

def test_list_keys():
    config.set("a", 1)
    config.set("b", 2)
    keys = config.list_keys()
    assert "a" in keys and "b" in keys

def test_get_temperature_default():
    assert config.get_temperature() == 0.55

def test_set_temperature():
    config.set_temperature(0.8)
    assert config.get_temperature() == 0.8
