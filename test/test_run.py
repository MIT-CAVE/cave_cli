import argparse
from unittest.mock import MagicMock, patch
import pytest

from cave_cli.commands.run import run, run_cave, _run_tui


@pytest.fixture
def fake_app(tmp_path):
    app_dir = tmp_path / "sample_app"
    app_dir.mkdir()
    env_file = app_dir / ".env"
    env_file.write_text("DATABASE_IMAGE=none\n", encoding="utf-8")
    return str(app_dir), "sample_app"


class TestRunCommand:
    @patch("cave_cli.commands.run.run_cave")
    @patch("cave_cli.utils.validate.get_app")
    def test_run_dispatch(self, mock_get_app, mock_run_cave, fake_app):
        mock_get_app.return_value = fake_app
        args = argparse.Namespace()
        run(args)
        mock_run_cave.assert_called_once_with(fake_app[0], fake_app[1], args)

    def test_attach_and_detached_conflict(self, fake_app):
        args = argparse.Namespace(
            attach=True,
            detached=True,
            interactive=False,
            show_all=False,
            entrypoint=None,
            docker_args="",
            ip_port=None,
        )
        with pytest.raises(SystemExit) as exc_info:
            run_cave(fake_app[0], fake_app[1], args)
        assert exc_info.value.code == 1

    @patch("cave_cli.utils.docker.get_running_apps", return_value=[])
    def test_attach_app_not_running(self, mock_get_running_apps, fake_app):
        args = argparse.Namespace(
            attach=True,
            detached=False,
            interactive=False,
            show_all=False,
            entrypoint=None,
            docker_args="",
            ip_port=None,
        )
        with pytest.raises(SystemExit) as exc_info:
            run_cave(fake_app[0], fake_app[1], args)
        assert exc_info.value.code == 1

    @patch("cave_cli.commands.run._run_tui")
    @patch("cave_cli.utils.docker.get_container_host_port", return_value="8000")
    @patch("cave_cli.utils.docker.get_all_containers", return_value=[])
    @patch(
        "cave_cli.utils.docker.get_running_apps", return_value=["sample_app"]
    )
    def test_attach_success(
        self,
        mock_get_running_apps,
        mock_get_all_containers,
        mock_get_container_host_port,
        mock_run_tui,
        fake_app,
    ):
        args = argparse.Namespace(
            attach=True,
            detached=False,
            interactive=False,
            show_all=False,
            entrypoint=None,
            docker_args="",
            ip_port=None,
            log_lines=None,
            log_history=None,
        )
        run_cave(fake_app[0], fake_app[1], args)
        mock_run_tui.assert_called_once()
        _, kwargs = mock_run_tui.call_args
        assert kwargs["already_running"] is True
        assert kwargs["app_name"] == "sample_app"
        assert kwargs["url"] == "http://localhost:8000"

    @patch("cave_cli.commands.run.run_detached_logged")
    @patch("cave_cli.commands.run.find_open_port", return_value=8000)
    @patch("cave_cli.commands.run.run_detached")
    @patch("cave_cli.commands.run.create_network")
    @patch("cave_cli.commands.run.build_image")
    @patch("cave_cli.commands.run.remove_containers")
    def test_run_detached_mode(
        self,
        mock_remove_containers,
        mock_build_image,
        mock_create_network,
        mock_run_detached,
        mock_find_open_port,
        mock_run_detached_logged,
        fake_app,
    ):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_run_detached_logged.return_value = mock_res

        args = argparse.Namespace(
            attach=False,
            detached=True,
            interactive=False,
            show_all=False,
            entrypoint=None,
            docker_args="",
            ip_port=None,
            log_lines=None,
            log_history=None,
        )
        run_cave(fake_app[0], fake_app[1], args, skip_header=True)

        # Container should have been started detached
        mock_run_detached_logged.assert_called_once()
        _, kwargs = mock_run_detached_logged.call_args
        assert kwargs["name"] == "sample_app_django"

        # remove_containers should only be called once at startup, not on exit
        assert mock_remove_containers.call_count == 1

    @patch("cave_cli.commands.run.remove_containers")
    @patch("cave_cli.commands.run.run_detached_logged")
    def test_run_tui_detach_skips_remove(
        self,
        mock_run_detached_logged,
        mock_remove_containers,
    ):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_run_detached_logged.return_value = mock_res

        mock_dashboard = MagicMock()
        mock_dashboard.is_detached = True

        with patch(
            "cave_cli.commands.run.RunDashboard", return_value=mock_dashboard
        ):
            with patch(
                "cave_cli.commands.run.threading.Thread"
            ) as mock_thread_cls:
                mock_thread = MagicMock()
                mock_thread_cls.return_value = mock_thread

                with patch(
                    "cave_cli.commands.run.threading.Event"
                ) as mock_event_cls:
                    mock_event = MagicMock()
                    mock_event.wait.return_value = None
                    mock_event_cls.return_value = mock_event

                    _run_tui(
                        app_name="sample_app",
                        django_container="sample_app_django",
                        image="cave-app:sample_app",
                        network="cave-net:sample_app",
                        ports=["8000:8000"],
                        volumes=[],
                        env_vars={},
                        extra_args=None,
                        command=["./utils/run_server.sh"],
                        url="http://localhost:8000",
                    )
        mock_remove_containers.assert_not_called()

    @patch("cave_cli.commands.run.remove_containers")
    @patch("cave_cli.commands.run.run_detached_logged")
    def test_run_tui_stop_removes_containers(
        self,
        mock_run_detached_logged,
        mock_remove_containers,
    ):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_run_detached_logged.return_value = mock_res

        mock_dashboard = MagicMock()
        mock_dashboard.is_detached = False

        with patch(
            "cave_cli.commands.run.RunDashboard", return_value=mock_dashboard
        ):
            with patch(
                "cave_cli.commands.run.threading.Thread"
            ) as mock_thread_cls:
                mock_thread = MagicMock()
                mock_thread_cls.return_value = mock_thread

                with patch(
                    "cave_cli.commands.run.threading.Event"
                ) as mock_event_cls:
                    mock_event = MagicMock()
                    mock_event.wait.return_value = None
                    mock_event_cls.return_value = mock_event

                    _run_tui(
                        app_name="sample_app",
                        django_container="sample_app_django",
                        image="cave-app:sample_app",
                        network="cave-net:sample_app",
                        ports=["8000:8000"],
                        volumes=[],
                        env_vars={},
                        extra_args=None,
                        command=["./utils/run_server.sh"],
                        url="http://localhost:8000",
                    )
        mock_remove_containers.assert_called_once_with("sample_app")

    @patch("cave_cli.utils.docker.subprocess.Popen")
    def test_stream_container_logs_stop_event_terminates(self, mock_popen):
        import queue
        import threading
        from cave_cli.utils.docker import stream_container_logs

        mock_proc = MagicMock()
        mock_proc.stdout = iter(["line 1\n"])
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc

        stop_event = threading.Event()
        stop_event.set()
        q = queue.Queue()

        stream_container_logs("test_container", q, stop_event)
        mock_proc.terminate.assert_called()
