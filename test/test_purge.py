import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cave_cli.commands.purge import purge


@pytest.fixture
def fake_app_dir(tmp_path: Path):
    app_dir = tmp_path / "sample_app"
    app_dir.mkdir()
    return str(app_dir)


class TestPurgeCommand:
    @patch("cave_cli.commands.purge.validate_app_dir", return_value=[])
    @patch("cave_cli.commands.purge.run_and_log")
    @patch("cave_cli.commands.purge.remove_image")
    @patch("cave_cli.commands.purge.remove_volume")
    @patch("cave_cli.commands.purge.stop_task_server")
    @patch("cave_cli.commands.purge.remove_containers")
    def test_purge_cleans_all_resources(
        self,
        mock_remove_containers,
        mock_stop_task,
        mock_remove_vol,
        mock_remove_img,
        mock_run_and_log,
        mock_validate,
        fake_app_dir,
    ):
        args = argparse.Namespace(path=fake_app_dir, yes=True)
        purge(args)

        mock_remove_containers.assert_called_once_with(
            "sample_app", skip_header=True
        )
        mock_stop_task.assert_called_once_with("sample_app")
        assert mock_remove_vol.call_count == 6
        mock_remove_vol.assert_any_call("sample_app")
        mock_remove_vol.assert_any_call("sample_app", "redis_volume")
        mock_remove_vol.assert_any_call("sample_app", "task_pg_volume")
        mock_remove_vol.assert_any_call("sample_app", "task_redis_volume")
        mock_remove_vol.assert_any_call("sample_app", "test_pg_volume")
        mock_remove_vol.assert_any_call("sample_app", "test_redis_volume")
        mock_remove_img.assert_called_once_with("sample_app")
        mock_run_and_log.assert_any_call(
            ["docker", "image", "rm", "-f", "cave-app-task:sample_app"]
        )
        mock_run_and_log.assert_any_call(
            ["docker", "image", "rm", "-f", "cave-app-test:sample_app"]
        )
        assert not Path(fake_app_dir).exists()
