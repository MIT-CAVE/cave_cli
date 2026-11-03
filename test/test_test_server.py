import argparse
import os
import subprocess
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cave_cli.utils.test_server import (
    get_last_test_activity,
    get_test_activity_path,
    get_test_db_name,
    get_test_django_name,
    get_test_image,
    get_test_network,
    get_test_redis_name,
    get_test_watcher_pid_path,
    is_process_alive,
    is_test_server_running,
    touch_test_activity,
)


class TestNamingAndPaths:
    def test_container_and_network_names(self):
        app_name = "sample_app"
        assert get_test_django_name(app_name) == "sample_app_test_django"
        assert get_test_db_name(app_name) == "sample_app_test_db_host"
        assert get_test_redis_name(app_name) == "sample_app_test_redis_host"
        assert get_test_network(app_name) == "cave-net-test:sample_app"
        assert get_test_image(app_name) == "cave-app-test:sample_app"

    def test_activity_and_pid_paths(self, tmp_path: Path):
        app_dir = tmp_path / "sample_app"
        app_dir.mkdir()
        activity_path = get_test_activity_path(str(app_dir), "sample_app")
        pid_path = get_test_watcher_pid_path(str(app_dir), "sample_app")

        assert "sample_app" in activity_path
        assert activity_path.endswith("_activity.json")
        assert "sample_app" in pid_path
        assert pid_path.endswith("_watcher.pid")


class TestActivityTracking:
    def test_touch_and_get_last_activity(self, tmp_path: Path):
        app_dir = tmp_path / "sample_app"
        app_dir.mkdir()

        # Before touch
        assert get_last_test_activity(str(app_dir), "sample_app") == 0.0

        before = time.time()
        touch_test_activity(str(app_dir), "sample_app")
        after = time.time()

        last = get_last_test_activity(str(app_dir), "sample_app")
        assert before <= last <= after


class TestServerStatusCheck:
    @patch("cave_cli.utils.test_server.is_container_running")
    def test_is_test_server_running_true(self, mock_is_running):
        mock_is_running.return_value = True
        assert is_test_server_running("my_app") is True

    @patch("cave_cli.utils.test_server.is_container_running")
    def test_is_test_server_running_partial(self, mock_is_running):
        mock_is_running.side_effect = lambda name: "django" not in name
        assert is_test_server_running("my_app") is False

    @patch("cave_cli.utils.test_server.is_container_running")
    def test_is_test_server_running_empty(self, mock_is_running):
        mock_is_running.return_value = False
        assert is_test_server_running("my_app") is False

    @patch("cave_cli.utils.test_server.run")
    def test_is_container_running_inspect(self, mock_run):
        from cave_cli.utils.test_server import is_container_running

        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="true\n"
        )
        assert is_container_running("any_name") is True

        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="false\n"
        )
        assert is_container_running("any_name") is False

        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout=""
        )
        assert is_container_running("any_name") is False


class TestProcessCheck:
    def test_is_process_alive_current(self):
        assert is_process_alive(os.getpid()) is True

    def test_is_process_alive_invalid(self):
        assert is_process_alive(-1) is False
        assert is_process_alive(0) is False


class TestCLIParsing:
    @patch("cave_cli.commands.doctor.check_all")
    @patch("cave_cli.commands.test.test")
    def test_cli_test_defaults(self, mock_test, mock_check_all):
        from cave_cli.cli import main

        with patch("sys.argv", ["cave", "test"]):
            main()
        mock_test.assert_called_once()
        args = mock_test.call_args[0][0]
        assert args.keep_alive == 10
        assert args.reset is False
        assert args.cancel is False
        assert args.kill_server is False

    @patch("cave_cli.commands.doctor.check_all")
    @patch("cave_cli.commands.test.test")
    def test_cli_test_flags(self, mock_test, mock_check_all):
        from cave_cli.cli import main

        with patch(
            "sys.argv", ["cave", "test", "--keep-alive", "5", "--reset"]
        ):
            main()
        args = mock_test.call_args[0][0]
        assert args.keep_alive == 5
        assert args.reset is True

    @patch("cave_cli.commands.doctor.check_all")
    @patch("cave_cli.commands.test.test")
    def test_cli_test_cancel_flag(self, mock_test, mock_check_all):
        from cave_cli.cli import main

        with patch("sys.argv", ["cave", "test", "-c"]):
            main()
        args = mock_test.call_args[0][0]
        assert args.cancel is True

    @patch("cave_cli.commands.doctor.check_all")
    @patch("cave_cli.commands.test.test")
    def test_cli_test_cancel_subcommand(self, mock_test, mock_check_all):
        from cave_cli.cli import main

        with patch("sys.argv", ["cave", "test", "cancel"]):
            main()
        args = mock_test.call_args[0][0]
        assert args.cancel is True

    @patch("cave_cli.commands.doctor.check_all")
    @patch("cave_cli.commands.test.test")
    def test_cli_test_kill_server_flag(self, mock_test, mock_check_all):
        from cave_cli.cli import main

        with patch("sys.argv", ["cave", "test", "-k"]):
            main()
        args = mock_test.call_args[0][0]
        assert args.kill_server is True

    @patch("cave_cli.commands.doctor.check_all")
    @patch("cave_cli.commands.test.test")
    def test_cli_test_kill_server_subcommand(self, mock_test, mock_check_all):
        from cave_cli.cli import main

        with patch("sys.argv", ["cave", "test", "kill-server"]):
            main()
        args = mock_test.call_args[0][0]
        assert args.kill_server is True

    @patch("cave_cli.commands.doctor.check_all")
    @patch("cave_cli.commands.kill.kill")
    def test_cli_kill_test_flag(self, mock_kill, mock_check_all):
        from cave_cli.cli import main

        with patch("sys.argv", ["cave", "kill", "--test"]):
            main()
        mock_kill.assert_called_once()
        args = mock_kill.call_args[0][0]
        assert args.test is True
