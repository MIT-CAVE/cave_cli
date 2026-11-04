import argparse
from pathlib import Path
from unittest.mock import patch

import pytest

from cave_cli.commands.prettify import prettify


@pytest.fixture
def fake_app(tmp_path: Path):
    app_dir = tmp_path / "sample_app"
    app_dir.mkdir()
    return str(app_dir), "sample_app"


class TestPrettifyCommand:
    @patch("cave_cli.commands.prettify.get_app")
    @patch("cave_cli.commands.prettify.schedule_task", return_value=0)
    def test_prettify_default_launch(
        self, mock_schedule, mock_get_app, fake_app
    ):
        mock_get_app.return_value = fake_app
        args = argparse.Namespace(
            detached=False,
            docker_args="",
            remaining=[],
        )
        prettify(args)
        mock_schedule.assert_called_once()
        kwargs = mock_schedule.call_args[1]
        assert kwargs["app_name"] == "sample_app"
        assert kwargs["detached"] is False
        assert kwargs["display_command"] == "prettify"

    @patch("cave_cli.commands.prettify.get_app")
    @patch("cave_cli.commands.prettify.schedule_task", return_value=0)
    def test_prettify_detached_flag(
        self, mock_schedule, mock_get_app, fake_app
    ):
        mock_get_app.return_value = fake_app
        args = argparse.Namespace(
            detached=True,
            docker_args="--cpus 2",
            remaining=["some_file.py"],
        )
        prettify(args)
        mock_schedule.assert_called_once()
        kwargs = mock_schedule.call_args[1]
        assert kwargs["detached"] is True
        assert kwargs["docker_args"] == ["--cpus", "2"]
        assert "some_file.py" in kwargs["command"]

    @patch("cave_cli.commands.prettify.get_app")
    @patch("cave_cli.commands.prettify.schedule_task", return_value=42)
    def test_prettify_nonzero_exit_code(
        self, mock_schedule, mock_get_app, fake_app
    ):
        mock_get_app.return_value = fake_app
        args = argparse.Namespace(
            detached=False,
            docker_args="",
            remaining=[],
        )
        with pytest.raises(SystemExit) as exc:
            prettify(args)
        assert exc.value.code == 42
