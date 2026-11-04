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
    run_command_in_server,
    run_test_in_server,
    touch_test_activity,
)


class TestNamingAndPaths:
    def test_container_and_network_names(self):
        app_name = "sample_app"
        assert get_test_django_name(app_name) == "sample_app_task_django"
        assert get_test_db_name(app_name) == "sample_app_task_db_host"
        assert get_test_redis_name(app_name) == "sample_app_task_redis_host"
        assert get_test_network(app_name) == "cave-net-task:sample_app"
        assert get_test_image(app_name) == "cave-app-task:sample_app"

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
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()

        with patch(
            "cave_cli.utils.task_server.get_cache_dir",
            return_value=str(cache_dir),
        ):
            # Before touch
            assert get_last_test_activity(str(app_dir), "sample_app") == 0.0

            before = time.time()
            touch_test_activity(str(app_dir), "sample_app")
            after = time.time()

            last = get_last_test_activity(str(app_dir), "sample_app")
            assert before <= last <= after


class TestServerStatusCheck:
    @patch("cave_cli.utils.task_server.is_container_running")
    def test_is_test_server_running_true(self, mock_is_running):
        mock_is_running.return_value = True
        assert is_test_server_running("my_app") is True

    @patch("cave_cli.utils.task_server.is_container_running")
    def test_is_test_server_running_partial(self, mock_is_running):
        mock_is_running.side_effect = lambda name: "django" not in name
        assert is_test_server_running("my_app") is False

    @patch("cave_cli.utils.task_server.is_container_running")
    def test_is_test_server_running_empty(self, mock_is_running):
        mock_is_running.return_value = False
        assert is_test_server_running("my_app") is False

    @patch("cave_cli.utils.task_server.run")
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


class TestRunInServer:
    @patch("cave_cli.utils.task_server.run")
    def test_run_command_in_server(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0
        )
        code = run_command_in_server(
            app_name="sample_app",
            command="./utils/prettify.sh",
            command_args=["arg1"],
            extra_env={"FOO": "bar"},
        )
        assert code == 0
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "sample_app_task_django" in cmd
        assert "./utils/prettify.sh" in cmd
        assert "arg1" in cmd
        assert "-e" in cmd
        assert "FOO=bar" in cmd

    @patch("cave_cli.utils.task_server.run_command_in_task_server")
    def test_run_test_in_server_delegation(self, mock_run_command):
        mock_run_command.return_value = 0
        code = run_test_in_server(
            app_name="sample_app",
            command_args=["test_one.py"],
            extra_env={"ALL_FLAG": "true"},
        )
        assert code == 0
        mock_run_command.assert_called_once_with(
            app_name="sample_app",
            command="./utils/run_test.sh",
            command_args=["test_one.py"],
            extra_env={"ALL_FLAG": "true"},
        )


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
        assert args.detached is False
        assert args.docker_args == ""
        assert args.remaining == []

    @patch("cave_cli.commands.doctor.check_all")
    @patch("cave_cli.commands.test.test")
    def test_cli_test_flags(self, mock_test, mock_check_all):
        from cave_cli.cli import main

        with patch(
            "sys.argv",
            ["cave", "test", "-d", "--docker-args", "--cpus 2", "test_foo.py"],
        ):
            main()
        args = mock_test.call_args[0][0]
        assert args.detached is True
        assert args.docker_args == "--cpus 2"
        assert args.remaining == ["test_foo.py"]

    @patch("cave_cli.commands.doctor.check_all")
    @patch("cave_cli.commands.kill.kill")
    def test_cli_kill_test_flag(self, mock_kill, mock_check_all):
        from cave_cli.cli import main

        with patch("sys.argv", ["cave", "kill", "--test"]):
            main()
        mock_kill.assert_called_once()
        args = mock_kill.call_args[0][0]
        assert (
            getattr(args, "task", False) is True
            or getattr(args, "test", False) is True
        )

    @patch("cave_cli.commands.doctor.check_all")
    @patch("cave_cli.commands.kill.kill")
    def test_cli_kill_task_flag(self, mock_kill, mock_check_all):
        from cave_cli.cli import main

        with patch("sys.argv", ["cave", "kill", "--task"]):
            main()
        mock_kill.assert_called_once()
        args = mock_kill.call_args[0][0]
        assert args.task is True

    @patch("cave_cli.commands.doctor.check_all")
    @patch("cave_cli.commands.task.task")
    def test_cli_task_list(self, mock_task, mock_check_all):
        from cave_cli.cli import main

        with patch("sys.argv", ["cave", "task", "--list"]):
            main()
        mock_task.assert_called_once()
        args = mock_task.call_args[0][0]
        assert args.list is True

    @patch("cave_cli.commands.doctor.check_all")
    @patch("cave_cli.commands.task.task")
    def test_cli_task_kill_flag(self, mock_task, mock_check_all):
        from cave_cli.cli import main

        with patch("sys.argv", ["cave", "task", "-k", "3"]):
            main()
        mock_task.assert_called_once()
        args = mock_task.call_args[0][0]
        assert args.kill_id == 3

    @patch("cave_cli.commands.doctor.check_all")
    @patch("cave_cli.commands.task.task")
    def test_cli_task_kill_all_flag(self, mock_task, mock_check_all):
        from cave_cli.cli import main

        with patch("sys.argv", ["cave", "task", "--kill-all"]):
            main()
        mock_task.assert_called_once()
        args = mock_task.call_args[0][0]
        assert args.kill_all is True

    @patch("cave_cli.commands.doctor.check_all")
    @patch("cave_cli.commands.task.task")
    def test_cli_task_reset_flag(self, mock_task, mock_check_all):
        from cave_cli.cli import main

        with patch("sys.argv", ["cave", "task", "--reset"]):
            main()
        mock_task.assert_called_once()
        args = mock_task.call_args[0][0]
        assert args.reset is True

    @patch("cave_cli.commands.doctor.check_all")
    @patch("cave_cli.commands.task.task")
    def test_cli_task_stop_flag(self, mock_task, mock_check_all):
        from cave_cli.cli import main

        with patch("sys.argv", ["cave", "task", "--stop"]):
            main()
        mock_task.assert_called_once()
        args = mock_task.call_args[0][0]
        assert args.stop is True

    @patch("cave_cli.commands.doctor.check_all")
    @patch("cave_cli.commands.task.task")
    def test_cli_task_list_all_flag(self, mock_task, mock_check_all):
        from cave_cli.cli import main

        with patch("sys.argv", ["cave", "task", "-la"]):
            main()
        mock_task.assert_called_once()
        args = mock_task.call_args[0][0]
        assert args.list_all is True

    @patch("cave_cli.commands.doctor.check_all")
    @patch("cave_cli.commands.task.task")
    def test_cli_task_attach_flag(self, mock_task, mock_check_all):
        from cave_cli.cli import main

        with patch("sys.argv", ["cave", "task", "-a", "5"]):
            main()
        mock_task.assert_called_once()
        args = mock_task.call_args[0][0]
        assert args.attach_id == 5

    @patch("cave_cli.commands.doctor.check_all")
    @patch("cave_cli.commands.task.task")
    def test_cli_task_detached_flag(self, mock_task, mock_check_all):
        from cave_cli.cli import main

        with patch("sys.argv", ["cave", "task", "-d", "start", "utils/foo.py"]):
            main()
        mock_task.assert_called_once()
        args = mock_task.call_args[0][0]
        assert args.detached is True
        assert args.task_cmd == ["utils/foo.py"]
        assert args.task_action == "start"

    @patch("cave_cli.commands.doctor.check_all")
    @patch("cave_cli.commands.prettify.prettify")
    def test_cli_prettify_defaults(self, mock_prettify, mock_check_all):
        from cave_cli.cli import main

        with patch("sys.argv", ["cave", "prettify"]):
            main()
        mock_prettify.assert_called_once()
        args = mock_prettify.call_args[0][0]
        assert args.detached is False
        assert args.docker_args == ""
        assert args.remaining == []

    @patch("cave_cli.commands.doctor.check_all")
    @patch("cave_cli.commands.prettify.prettify")
    def test_cli_prettify_flags(self, mock_prettify, mock_check_all):
        from cave_cli.cli import main

        with patch(
            "sys.argv",
            ["cave", "prettify", "-d", "--docker-args", "--cpus 2", "foo.py"],
        ):
            main()
        args = mock_prettify.call_args[0][0]
        assert args.detached is True
        assert args.docker_args == "--cpus 2"
        assert args.remaining == ["foo.py"]
