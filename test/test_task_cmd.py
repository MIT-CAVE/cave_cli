import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cave_cli.commands.task import task


@pytest.fixture
def fake_app(tmp_path: Path):
    app_dir = tmp_path / "sample_app"
    app_dir.mkdir()
    return str(app_dir), "sample_app"


class TestTaskCommand:
    @patch("cave_cli.commands.task.get_app")
    @patch("cave_cli.commands.task.list_tasks")
    def test_task_list_flag(self, mock_list_tasks, mock_get_app, fake_app):
        mock_get_app.return_value = fake_app
        mock_list_tasks.return_value = [
            {
                "id": 1,
                "command": "test",
                "args": ["all"],
                "pid": 1234,
                "status": "running",
                "started_at": 100.0,
                "ended_at": None,
            }
        ]
        args = argparse.Namespace(list=True, remaining=[])
        task(args)
        mock_list_tasks.assert_called_once_with(fake_app[0])

    @patch("cave_cli.commands.task.get_app")
    @patch("cave_cli.commands.task.list_tasks")
    def test_task_list_subcommand(
        self, mock_list_tasks, mock_get_app, fake_app
    ):
        mock_get_app.return_value = fake_app
        mock_list_tasks.return_value = []
        args = argparse.Namespace(list=False, remaining=["list"])
        task(args)
        mock_list_tasks.assert_called_once_with(fake_app[0])

    @patch("cave_cli.commands.task.get_app")
    @patch("cave_cli.commands.task.cancel_task")
    def test_task_kill_flag(self, mock_cancel_task, mock_get_app, fake_app):
        mock_get_app.return_value = fake_app
        mock_cancel_task.return_value = True
        args = argparse.Namespace(
            list=False, kill_id=2, kill_all=False, remaining=[]
        )
        task(args)
        mock_cancel_task.assert_called_once_with(fake_app[0], fake_app[1], 2)

    @patch("cave_cli.commands.task.get_app")
    @patch("cave_cli.commands.task.cancel_task")
    def test_task_kill_subcommand(
        self, mock_cancel_task, mock_get_app, fake_app
    ):
        mock_get_app.return_value = fake_app
        mock_cancel_task.return_value = True
        args = argparse.Namespace(
            list=False, kill_id=None, kill_all=False, remaining=["kill", "5"]
        )
        task(args)
        mock_cancel_task.assert_called_once_with(fake_app[0], fake_app[1], 5)

    @patch("cave_cli.commands.task.get_app")
    @patch("cave_cli.commands.task.cancel_all_tasks")
    def test_task_kill_all_flag(self, mock_cancel_all, mock_get_app, fake_app):
        mock_get_app.return_value = fake_app
        mock_cancel_all.return_value = 3
        args = argparse.Namespace(
            list=False, kill_id=None, kill_all=True, remaining=[]
        )
        task(args)
        mock_cancel_all.assert_called_once_with(fake_app[0], fake_app[1])

    @patch("cave_cli.commands.task.get_app")
    @patch("cave_cli.commands.task.cancel_all_tasks")
    def test_task_kill_all_subcommand(
        self, mock_cancel_all, mock_get_app, fake_app
    ):
        mock_get_app.return_value = fake_app
        mock_cancel_all.return_value = 1
        args = argparse.Namespace(
            list=False, kill_id=None, kill_all=False, remaining=["kill-all"]
        )
        task(args)
        mock_cancel_all.assert_called_once_with(fake_app[0], fake_app[1])

    @patch("cave_cli.commands.task.get_app")
    @patch("cave_cli.commands.task.reset_task_server")
    def test_task_reset(self, mock_reset, mock_get_app, fake_app):
        mock_get_app.return_value = fake_app
        args = argparse.Namespace(
            list=False,
            kill_id=None,
            kill_all=False,
            reset=True,
            docker_args="",
            remaining=[],
        )
        task(args)
        mock_reset.assert_called_once_with(fake_app[0], fake_app[1], [])

    @patch("cave_cli.commands.task.get_app")
    @patch("cave_cli.commands.task.is_task_server_running", return_value=True)
    @patch("cave_cli.commands.task.stop_task_server")
    def test_task_stop(
        self, mock_stop, mock_is_running, mock_get_app, fake_app
    ):
        mock_get_app.return_value = fake_app
        args = argparse.Namespace(
            list=False,
            kill_id=None,
            kill_all=False,
            stop=True,
            remaining=[],
        )
        task(args)
        mock_stop.assert_called_once_with(fake_app[1], app_dir=fake_app[0])

    @patch("cave_cli.commands.task.get_app")
    @patch("cave_cli.commands.task.list_tasks")
    def test_task_list_all(self, mock_list_tasks, mock_get_app, fake_app):
        mock_get_app.return_value = fake_app
        mock_list_tasks.return_value = [
            {"id": 1, "command": "test", "args": [], "status": "completed"}
        ]
        args = argparse.Namespace(
            list=False,
            list_all=True,
            kill_id=None,
            kill_all=False,
            remaining=[],
        )
        task(args)
        mock_list_tasks.assert_called_once_with(fake_app[0])

    @patch("cave_cli.commands.task.get_app")
    @patch("cave_cli.commands.task.schedule_task", return_value=0)
    def test_task_start_subcommand(self, mock_schedule, mock_get_app, fake_app):
        mock_get_app.return_value = fake_app
        args = argparse.Namespace(
            list=False,
            kill_id=None,
            kill_all=False,
            detached=False,
            docker_args="",
            remaining=["start", "utils/prettify.py", "--check"],
        )
        task(args)
        mock_schedule.assert_called_once_with(
            app_dir=fake_app[0],
            app_name=fake_app[1],
            command=["utils/prettify.py", "--check"],
            detached=False,
            docker_args=[],
        )

    @patch("cave_cli.commands.task.get_app")
    @patch("cave_cli.commands.task.schedule_task", return_value=0)
    def test_task_arbitrary_command(
        self, mock_schedule, mock_get_app, fake_app
    ):
        mock_get_app.return_value = fake_app
        args = argparse.Namespace(
            list=False,
            kill_id=None,
            kill_all=False,
            detached=True,
            docker_args="",
            remaining=["python", "manage.py", "makemigrations"],
        )
        task(args)
        mock_schedule.assert_called_once_with(
            app_dir=fake_app[0],
            app_name=fake_app[1],
            command=["python", "manage.py", "makemigrations"],
            detached=True,
            docker_args=[],
        )

    @patch("cave_cli.commands.task.get_app")
    @patch("cave_cli.commands.task.attach_to_task", return_value=0)
    def test_task_attach(self, mock_attach, mock_get_app, fake_app):
        mock_get_app.return_value = fake_app
        args = argparse.Namespace(
            list=False,
            kill_id=None,
            kill_all=False,
            attach_id=3,
            remaining=[],
        )
        task(args)
        mock_attach.assert_called_once_with(fake_app[0], fake_app[1], 3)
