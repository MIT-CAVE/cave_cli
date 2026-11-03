import os
from pathlib import Path
from unittest.mock import patch

import pytest

from cave_cli.utils.complete import (
    find_app_dir_safe,
    get_completion_script,
    get_completions,
    get_test_files,
    install_completion,
)


class TestCompleteUtils:
    def test_find_app_dir_safe_non_app(self, tmp_path: Path):
        assert find_app_dir_safe(str(tmp_path)) is None

    def test_get_test_files_empty(self, tmp_path: Path):
        assert get_test_files(str(tmp_path)) == []

    def test_get_test_files_populated(self, tmp_path: Path):
        tests_dir = tmp_path / "cave_api" / "tests"
        tests_dir.mkdir(parents=True)
        (tests_dir / "__init__.py").write_text("", encoding="utf-8")
        (tests_dir / ".hidden.py").write_text("", encoding="utf-8")
        (tests_dir / "notes.txt").write_text("", encoding="utf-8")
        (tests_dir / "test_init.py").write_text("", encoding="utf-8")
        (tests_dir / "test_pipeline.py").write_text("", encoding="utf-8")

        sub_dir = tests_dir / "unit"
        sub_dir.mkdir()
        (sub_dir / "test_sub.py").write_text("", encoding="utf-8")

        files = get_test_files(str(tmp_path))
        assert files == [
            "test_init.py",
            "test_pipeline.py",
            os.path.join("unit", "test_sub.py"),
        ]

    def test_get_completions_top_level(self):
        candidates = get_completions(["cave"], 1)
        assert "test" in candidates
        assert "run" in candidates
        assert "completion" in candidates
        assert "--help" in candidates

    def test_get_completions_test(self, tmp_path: Path):
        tests_dir = tmp_path / "cave_api" / "tests"
        tests_dir.mkdir(parents=True)
        (tests_dir / "test_custom.py").write_text("", encoding="utf-8")

        with patch(
            "cave_cli.utils.complete.get_test_files",
            return_value=["test_custom.py"],
        ):
            candidates = get_completions(["cave", "test", ""], 2)
            assert "test_custom.py" in candidates
            assert "cancel" in candidates
            assert "kill-server" in candidates
            assert "--keep-alive" in candidates
            assert "--reset" in candidates

    def test_get_completions_theme(self):
        candidates = get_completions(["cave", "theme", ""], 2)
        assert "dark" in candidates
        assert "light" in candidates
        assert "solarized" in candidates
        assert "monokai" in candidates

    def test_get_completions_kill(self):
        with patch(
            "cave_cli.utils.docker.get_running_apps", return_value=["app_one"]
        ):
            with patch(
                "cave_cli.utils.docker.get_running_test_servers",
                return_value=["test_two"],
            ):
                candidates = get_completions(["cave", "kill", ""], 2)
                assert "app_one" in candidates
                assert "test_two" in candidates
                assert "--test" in candidates

    def test_get_completion_script(self):
        script = get_completion_script()
        assert "_cave_completions" in script
        assert "complete -o default -F _cave_completions cave" in script

    def test_install_completion(self, tmp_path: Path):
        fake_rc = tmp_path / ".bashrc"
        fake_rc.write_text("# existing config\n", encoding="utf-8")

        with patch.object(Path, "home", return_value=tmp_path):
            with patch.dict(os.environ, {"SHELL": "/bin/bash"}):
                result = install_completion()
                assert result == str(fake_rc)
                content = fake_rc.read_text(encoding="utf-8")
                assert 'eval "$(cave completion)"' in content

                # Calling again should not duplicate
                result2 = install_completion()
                assert result2 == str(fake_rc)
                assert content.count('eval "$(cave completion)"') == 1


class TestCLICompletion:
    def test_cave_completion_command(self, capsys):
        from cave_cli.cli import main

        with patch("sys.argv", ["cave", "completion"]):
            main()
        captured = capsys.readouterr()
        assert "_cave_completions" in captured.out

    def test_cave_complete_internal(self, capsys):
        from cave_cli.cli import main

        with patch("sys.argv", ["cave", "_complete", "--cword", "1", "cave"]):
            main()
        captured = capsys.readouterr()
        assert "test" in captured.out
        assert "completion" in captured.out
