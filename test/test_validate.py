import pytest
from cave_cli.utils.validate import validate_app_name


class TestValidateAppName:
    def test_valid_simple(self):
        assert validate_app_name("myapp") is None

    def test_valid_with_hyphen(self):
        assert validate_app_name("my-app") is None

    def test_valid_with_underscore(self):
        assert validate_app_name("my_app") is None

    def test_valid_with_numbers(self):
        assert validate_app_name("app123") is None

    def test_too_short(self):
        assert validate_app_name("a") is not None

    def test_uppercase_rejected(self):
        assert validate_app_name("MyApp") is not None

    def test_starts_with_hyphen(self):
        assert validate_app_name("-myapp") is not None

    def test_starts_with_underscore(self):
        assert validate_app_name("_myapp") is not None

    def test_ends_with_hyphen(self):
        assert validate_app_name("myapp-") is not None

    def test_ends_with_underscore(self):
        assert validate_app_name("myapp_") is not None

    def test_hyphen_followed_by_underscore(self):
        assert validate_app_name("my-_app") is not None

    def test_underscore_followed_by_hyphen(self):
        assert validate_app_name("my_-app") is not None

    def test_spaces_rejected(self):
        assert validate_app_name("my app") is not None

    def test_too_long(self):
        assert validate_app_name("a" * 256) is not None

    def test_max_valid_length(self):
        assert validate_app_name("a" * 255) is None


class TestValidateAppDir:
    def test_not_a_candidate(self, tmp_path):
        from cave_cli.utils.validate import validate_app_dir
        # Completely empty dir
        res = validate_app_dir(str(tmp_path))
        assert res == ["Not a CAVE app directory"]

    def test_candidate_missing_folders_files(self, tmp_path):
        from cave_cli.utils.validate import validate_app_dir
        # Contains manage.py, so it is a candidate
        (tmp_path / "manage.py").write_text("")
        
        res = validate_app_dir(str(tmp_path))
        assert any("The folder 'cave_core' is missing" in err for err in res)
        assert any("The folder 'cave_api' is missing" in err for err in res)
        assert any("The file 'Dockerfile' is missing" in err for err in res)
        assert any("Neither 'requirements.txt' nor 'pyproject.toml' exists." in err for err in res)

    def test_find_app_dir_reports_starting_dir_errors(self, tmp_path, monkeypatch):
        import sys
        from cave_cli.utils.validate import find_app_dir
        
        # We start in a directory that has manage.py (so it's a candidate) but is missing other things.
        start_dir = tmp_path / "my_app"
        start_dir.mkdir()
        (start_dir / "manage.py").write_text("")
        
        # We'll mock sys.exit and logger to verify that when it reaches the root,
        # it prints the errors of the starting directory start_dir.
        logged_errors = []
        class MockLogger:
            def error(self, msg):
                logged_errors.append(msg)
        
        import cave_cli.utils.validate
        monkeypatch.setattr(cave_cli.utils.validate, "logger", MockLogger())
        
        exit_called = False
        def mock_exit(code):
            nonlocal exit_called
            exit_called = True
            raise SystemExit(code)
            
        monkeypatch.setattr(sys, "exit", mock_exit)
        
        with pytest.raises(SystemExit):
            find_app_dir(str(start_dir))
            
        assert exit_called
        # Check that it printed errors about start_dir (e.g. missing cave_core)
        any_missing_core = any("The folder 'cave_core' is missing" in err for err in logged_errors)
        assert any_missing_core
