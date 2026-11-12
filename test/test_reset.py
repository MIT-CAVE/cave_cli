import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cave_cli.commands.reset import reset


@pytest.fixture
def fake_app_paths(tmp_path: Path):
    app_dir = tmp_path / "sample_app"
    app_dir.mkdir()
    return str(app_dir), "sample_app"


class TestResetCommand:
    @patch("cave_cli.commands.reset.run_cave")
    @patch("cave_cli.commands.reset.run_and_log")
    @patch("cave_cli.commands.reset.remove_volume")
    @patch("cave_cli.commands.reset.stop_task_server")
    @patch("cave_cli.commands.reset.remove_containers")
    def test_reset_cleans_task_server_resources(
        self,
        mock_remove_containers,
        mock_stop_task,
        mock_remove_vol,
        mock_run_and_log,
        mock_run_cave,
        fake_app_paths,
    ):
        app_dir, app_name = fake_app_paths
        args = argparse.Namespace(yes=True, docker_args="")
        reset(args, app_dir=app_dir, app_name=app_name)

        mock_remove_containers.assert_called_once_with(
            app_name, skip_header=True
        )
        mock_stop_task.assert_called_once_with(app_name)
        assert mock_remove_vol.call_count == 6
        mock_remove_vol.assert_any_call(app_name)
        mock_remove_vol.assert_any_call(app_name, "redis_volume")
        mock_remove_vol.assert_any_call(app_name, "task_pg_volume")
        mock_remove_vol.assert_any_call(app_name, "task_redis_volume")
        mock_remove_vol.assert_any_call(app_name, "test_pg_volume")
        mock_remove_vol.assert_any_call(app_name, "test_redis_volume")
        mock_run_and_log.assert_any_call(
            ["docker", "image", "rm", "-f", f"cave-app-task:{app_name}"]
        )
        mock_run_and_log.assert_any_call(
            ["docker", "image", "rm", "-f", f"cave-app-test:{app_name}"]
        )
        mock_run_cave.assert_called_once()
