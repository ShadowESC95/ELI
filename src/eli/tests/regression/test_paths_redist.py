def test_paths_are_generic_and_create_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("ELI_PROJECT_ROOT", str(tmp_path))
    from importlib import reload
    import eli.brain.paths as paths

    reload(paths)
    paths.ensure_dirs()

    assert paths.ARTIFACTS_DIR.exists()
    assert paths.CONVERSATIONS_DIR.exists()
    assert str(paths.PROJECT_ROOT).startswith(str(tmp_path))
