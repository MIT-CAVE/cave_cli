import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cave_cli.commands.task import (
    _get_next_active_task,
    attach_to_task,
    task,
)


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
    @patch("cave_cli.commands.task.list_tasks")
    def test_task_list_all_with_limit(
        self, mock_list_tasks, mock_get_app, fake_app
    ):
        mock_get_app.return_value = fake_app
        mock_list_tasks.return_value = [
            {"id": 1, "command": "test", "args": [], "status": "completed"}
        ]
        args = argparse.Namespace(
            list=False,
            list_all=True,
            limit=5,
            kill_id=None,
            kill_all=False,
            remaining=[],
        )
        task(args)
        mock_list_tasks.assert_called_once_with(fake_app[0], limit=5)

    @patch("cave_cli.commands.task.get_app")
    @patch("cave_cli.commands.task.clean_completed_tasks")
    def test_task_clean(self, mock_clean_completed, mock_get_app, fake_app):
        mock_get_app.return_value = fake_app
        mock_clean_completed.return_value = 2
        args = argparse.Namespace(
            action="clean",
            remaining=[],
        )
        task(args)
        mock_clean_completed.assert_called_once_with(fake_app[0], keep_last_n=0)

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

    @patch("cave_cli.commands.task.get_app")
    @patch("cave_cli.commands.task.attach_to_task", return_value=0)
    def test_task_attach_no_id_subcommand(
        self, mock_attach, mock_get_app, fake_app
    ):
        mock_get_app.return_value = fake_app
        args = argparse.Namespace(
            task_action="attach",
            task_id=None,
            attach_id=None,
            kill_id=None,
            kill_all=False,
            remaining=[],
        )
        task(args)
        mock_attach.assert_called_once_with(fake_app[0], fake_app[1], None)

    @patch("cave_cli.commands.task.get_app")
    @patch("cave_cli.commands.task.attach_to_task", return_value=0)
    def test_task_attach_no_id_flag(self, mock_attach, mock_get_app, fake_app):
        mock_get_app.return_value = fake_app
        args = argparse.Namespace(
            attach_id=-1,
            kill_id=None,
            kill_all=False,
            remaining=[],
        )
        task(args)
        mock_attach.assert_called_once_with(fake_app[0], fake_app[1], None)


class TestTaskAttachLogic:
    @patch("cave_cli.commands.task.list_tasks")
    def test_get_next_active_task_prefers_running(
        self, mock_list_tasks, fake_app
    ):
        mock_list_tasks.return_value = [
            {"id": 1, "status": "completed"},
            {"id": 2, "status": "queued"},
            {"id": 3, "status": "running"},
            {"id": 4, "status": "queued"},
        ]
        next_t = _get_next_active_task(fake_app[0])
        assert next_t is not None
        assert next_t["id"] == 3

    @patch("cave_cli.commands.task.list_tasks")
    def test_get_next_active_task_queued_order(self, mock_list_tasks, fake_app):
        mock_list_tasks.return_value = [
            {"id": 2, "status": "queued"},
            {"id": 3, "status": "queued"},
        ]
        next_t = _get_next_active_task(fake_app[0])
        assert next_t is not None
        assert next_t["id"] == 2

    @patch("cave_cli.commands.task.list_tasks")
    def test_get_next_active_task_after_id(self, mock_list_tasks, fake_app):
        mock_list_tasks.return_value = [
            {"id": 1, "status": "completed"},
            {"id": 2, "status": "queued"},
            {"id": 3, "status": "queued"},
        ]
        next_t = _get_next_active_task(fake_app[0], after_id=2)
        assert next_t is not None
        assert next_t["id"] == 3

    @patch("cave_cli.commands.task.list_tasks")
    def test_get_next_active_task_none_when_empty_or_done(
        self, mock_list_tasks, fake_app
    ):
        mock_list_tasks.return_value = [
            {"id": 1, "status": "completed"},
            {"id": 2, "status": "failed"},
        ]
        assert _get_next_active_task(fake_app[0]) is None

    @patch("cave_cli.commands.task.get_task", return_value=None)
    def test_attach_to_task_specified_id_not_found(
        self, mock_get_task, fake_app
    ):
        code = attach_to_task(fake_app[0], fake_app[1], task_id=99)
        assert code == 1

    @patch("cave_cli.commands.task._stream_task", return_value=(0, False))
    @patch("cave_cli.commands.task.get_task")
    def test_attach_to_task_specified_id_exits_without_following(
        self, mock_get_task, mock_stream_task, fake_app
    ):
        mock_get_task.return_value = {"id": 5, "status": "running"}
        code = attach_to_task(fake_app[0], fake_app[1], task_id=5)
        assert code == 0
        mock_stream_task.assert_called_once_with(
            app_dir=fake_app[0],
            app_name=fake_app[1],
            task_id=5,
            fd=None,
            follow_all=False,
        )

    @patch("cave_cli.commands.task.list_tasks", return_value=[])
    def test_attach_to_task_no_id_no_tasks(self, mock_list_tasks, fake_app):
        code = attach_to_task(fake_app[0], fake_app[1], task_id=None)
        assert code == 0

    @patch(
        "cave_cli.commands.task.list_tasks",
        return_value=[{"id": 1, "status": "completed"}],
    )
    def test_attach_to_task_no_id_no_active_tasks(
        self, mock_list_tasks, fake_app
    ):
        code = attach_to_task(fake_app[0], fake_app[1], task_id=None)
        assert code == 0

    @patch("cave_cli.commands.task._stream_task")
    @patch("cave_cli.commands.task.list_tasks")
    def test_attach_to_task_no_id_jumps_until_all_done(
        self, mock_list_tasks, mock_stream_task, fake_app
    ):
        # Initial: task 1 running, task 2 queued
        # After task 1 done: task 2 running
        # After task 2 done: no active tasks
        def fake_list_tasks(app_dir):
            if mock_stream_task.call_count == 0:
                return [
                    {"id": 1, "status": "running"},
                    {"id": 2, "status": "queued"},
                ]
            elif mock_stream_task.call_count == 1:
                return [
                    {"id": 1, "status": "completed"},
                    {"id": 2, "status": "running"},
                ]
            else:
                return [
                    {"id": 1, "status": "completed"},
                    {"id": 2, "status": "completed"},
                ]

        mock_list_tasks.side_effect = fake_list_tasks
        mock_stream_task.side_effect = [(0, False), (0, False)]

        code = attach_to_task(fake_app[0], fake_app[1], task_id=None)
        assert code == 0
        assert mock_stream_task.call_count == 2
        calls = mock_stream_task.call_args_list
        assert calls[0].kwargs["task_id"] == 1
        assert calls[0].kwargs["follow_all"] is True
        assert calls[1].kwargs["task_id"] == 2
        assert calls[1].kwargs["follow_all"] is True

    @patch("cave_cli.commands.task._stream_task")
    @patch("cave_cli.commands.task.list_tasks")
    def test_attach_to_task_no_id_stops_on_detach(
        self, mock_list_tasks, mock_stream_task, fake_app
    ):
        mock_list_tasks.return_value = [
            {"id": 1, "status": "running"},
            {"id": 2, "status": "queued"},
        ]
        # User presses ESC during task 1
        mock_stream_task.return_value = (0, True)

        code = attach_to_task(fake_app[0], fake_app[1], task_id=None)
        assert code == 0
        assert mock_stream_task.call_count == 1

    @patch("cave_cli.commands.task.cancel_task")
    @patch("cave_cli.commands.task._stream_task", side_effect=KeyboardInterrupt)
    @patch("cave_cli.commands.task.list_tasks")
    def test_attach_to_task_ctrl_c_cancels_current_task(
        self, mock_list_tasks, mock_stream_task, mock_cancel_task, fake_app
    ):
        mock_list_tasks.return_value = [{"id": 4, "status": "running"}]
        code = attach_to_task(fake_app[0], fake_app[1], task_id=None)
        assert code == 130
        mock_cancel_task.assert_called_once_with(fake_app[0], fake_app[1], 4)


class TestScheduleTaskLogic:
    @patch("cave_cli.commands.task.attach_to_task", return_value=0)
    @patch("cave_cli.commands.task.spawn_task_runner", return_value=12345)
    @patch("cave_cli.commands.task.update_task_pid")
    @patch("cave_cli.commands.task.register_task")
    def test_schedule_task_updates_runner_pid(
        self,
        mock_register,
        mock_update_pid,
        mock_spawn,
        mock_attach,
        fake_app,
    ):
        from cave_cli.commands.task import schedule_task

        mock_register.return_value = {"id": 7, "command": "prettify"}
        code = schedule_task(
            app_dir=fake_app[0],
            app_name=fake_app[1],
            command=["utils/prettify.py"],
            detached=False,
        )
        assert code == 0
        mock_spawn.assert_called_once_with(fake_app[0], fake_app[1], 7, None)
        mock_update_pid.assert_called_once_with(fake_app[0], 7, 12345)
        mock_attach.assert_called_once_with(fake_app[0], fake_app[1], 7)
