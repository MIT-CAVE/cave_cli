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

    @patch("cave_cli.commands.run.remove_containers")
    @patch("cave_cli.commands.run.stream_container_logs")
    def test_run_tui_already_running_sets_ready_and_components(
        self,
        mock_stream,
        mock_remove,
    ):
        with patch("cave_cli.commands.run.RunDashboard") as mock_dash_cls:
            mock_dashboard = MagicMock()
            mock_dashboard.is_detached = True
            mock_dashboard.is_active_tui = True
            mock_dash_cls.return_value = mock_dashboard

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
                        ports=[],
                        volumes=[],
                        env_vars={},
                        extra_args=None,
                        command=[],
                        url="http://localhost:8000",
                        already_running=True,
                    )

            from cave_cli.utils.display import READY

            mock_dashboard.set_status.assert_called_with(READY)
            mock_dashboard.set_components.assert_called_once()
            mock_dashboard.add_lifecycle_event.assert_called_once()

    @patch("cave_cli.commands.run.start_and_verify_cache", return_value=True)
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
        mock_start_cache,
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

    @patch("cave_cli.commands.run.start_and_verify_cache", return_value=True)
    @patch("cave_cli.commands.run._stream_raw")
    @patch("cave_cli.commands.run._run_tui")
    @patch("cave_cli.utils.docker.get_running_apps", return_value=[])
    @patch("cave_cli.commands.run.run_detached_logged")
    @patch("cave_cli.commands.run.find_open_port", return_value=8000)
    @patch("cave_cli.commands.run.run_detached")
    @patch("cave_cli.commands.run.create_network")
    @patch("cave_cli.commands.run.build_image")
    @patch("cave_cli.commands.run.remove_containers")
    def test_run_no_tui_mode(
        self,
        mock_remove_containers,
        mock_build_image,
        mock_create_network,
        mock_run_detached,
        mock_find_open_port,
        mock_run_detached_logged,
        mock_get_running_apps,
        mock_run_tui,
        mock_stream_raw,
        mock_start_cache,
        fake_app,
    ):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_run_detached_logged.return_value = mock_res

        args = argparse.Namespace(
            attach=False,
            detached=False,
            interactive=False,
            show_all=False,
            no_tui=True,
            entrypoint=None,
            docker_args="",
            ip_port=None,
            log_lines=None,
            log_history=None,
        )
        run_cave(fake_app[0], fake_app[1], args, skip_header=True)

        # _stream_raw should be called, and _run_tui should NOT be called
        mock_stream_raw.assert_called_once()
        mock_run_tui.assert_not_called()
        # remove_containers should be called at startup and on exit
        assert mock_remove_containers.call_count == 2

    @patch("cave_cli.commands.run._run_tui")
    @patch("cave_cli.utils.docker.get_container_host_port", return_value="8000")
    @patch("cave_cli.utils.docker.get_all_containers", return_value=[])
    @patch(
        "cave_cli.utils.docker.get_running_apps", return_value=["sample_app"]
    )
    def test_run_auto_attaches_when_already_running(
        self,
        mock_get_running_apps,
        mock_get_all_containers,
        mock_get_container_host_port,
        mock_run_tui,
        fake_app,
    ):
        args = argparse.Namespace(
            attach=False,
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

    @patch("cave_cli.commands.run._stream_raw")
    @patch("cave_cli.commands.run._run_tui")
    @patch(
        "cave_cli.utils.docker.get_running_apps", return_value=["sample_app"]
    )
    @patch("cave_cli.utils.docker.get_all_containers", return_value=[])
    @patch("cave_cli.utils.docker.get_container_host_port", return_value="8000")
    def test_attach_no_tui_mode(
        self,
        mock_port,
        mock_containers,
        mock_apps,
        mock_run_tui,
        mock_stream_raw,
        fake_app,
    ):
        args = argparse.Namespace(
            attach=True,
            detached=False,
            interactive=False,
            show_all=False,
            no_tui=True,
            entrypoint=None,
            docker_args="",
            ip_port=None,
            log_lines=None,
            log_history=None,
        )
        run_cave(fake_app[0], fake_app[1], args)

        mock_stream_raw.assert_called_once()
        mock_run_tui.assert_not_called()

    @patch("cave_cli.commands.run._run_tui")
    @patch("cave_cli.commands.run.find_open_port", return_value=8000)
    @patch("cave_cli.commands.run.run_detached")
    @patch("cave_cli.commands.run.create_network")
    @patch("cave_cli.commands.run.build_image")
    @patch("cave_cli.commands.run.remove_containers")
    def test_batch_run_skips_db_check(
        self,
        mock_remove,
        mock_build,
        mock_net,
        mock_detached,
        mock_port,
        mock_tui,
        tmp_path,
    ):
        app_dir = tmp_path / "batch_app"
        app_dir.mkdir()
        env_file = app_dir / ".env"
        env_file.write_text("DATABASE_IMAGE=postgres:15\n", encoding="utf-8")

        args = argparse.Namespace(
            attach=False,
            detached=False,
            interactive=False,
            show_all=False,
            no_tui=False,
            raw=False,
            entrypoint="./utils/reset_db.sh",
            docker_args="",
            ip_port=None,
            yes=True,
            verbose=False,
            loglevel="INFO",
        )

        with patch("cave_cli.commands.run.RunDashboard"):
            with patch(
                "cave_cli.utils.docker.is_container_ready"
            ) as mock_ready:
                run_cave(str(app_dir), "batch_app", args, skip_header=True)
                # is_container_ready should NOT be called because is_server_run is False
                mock_ready.assert_not_called()

    @patch("cave_cli.commands.run.start_and_verify_cache", return_value=True)
    @patch("cave_cli.commands.run._stream_raw")
    @patch("cave_cli.commands.run._run_tui")
    @patch("cave_cli.commands.run.run_detached_logged")
    @patch("cave_cli.commands.run.find_open_port", return_value=8000)
    @patch("cave_cli.commands.run.create_network")
    @patch("cave_cli.commands.run.build_image")
    @patch("cave_cli.commands.run.remove_containers")
    def test_run_verbose_enables_raw_mode(
        self,
        mock_remove,
        mock_build,
        mock_net,
        mock_port,
        mock_run_detached_logged,
        mock_run_tui,
        mock_stream_raw,
        mock_start_cache,
        fake_app,
    ):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_run_detached_logged.return_value = mock_res

        args = argparse.Namespace(
            attach=False,
            detached=False,
            interactive=False,
            show_all=False,
            no_tui=False,
            raw=False,
            entrypoint=None,
            docker_args="",
            ip_port=None,
            log_lines=None,
            log_history=None,
            verbose=True,
            loglevel="INFO",
        )
        run_cave(fake_app[0], fake_app[1], args, skip_header=True)

        mock_stream_raw.assert_called_once()
        mock_run_tui.assert_not_called()


class TestDockerCacheAndHealth:
    @patch("cave_cli.utils.docker.run")
    def test_is_container_running(self, mock_run):
        from cave_cli.utils.docker import is_container_running

        import subprocess

        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="true\n"
        )
        assert is_container_running("my_container") is True

        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="false\n"
        )
        assert is_container_running("my_container") is False

        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout=""
        )
        assert is_container_running("my_container") is False

    @patch("cave_cli.utils.docker.run")
    def test_get_container_logs(self, mock_run):
        from cave_cli.utils.docker import get_container_logs

        import subprocess

        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="stdout line\n",
            stderr="stderr line\n",
        )
        logs = get_container_logs("my_container")
        assert "stdout line" in logs
        assert "stderr line" in logs

    @patch("cave_cli.utils.docker.run")
    def test_is_cache_ready_pong(self, mock_run):
        from cave_cli.utils.docker import is_cache_ready

        import subprocess

        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="PONG\n"
        )
        assert is_cache_ready("my_cache") is True

    @patch("cave_cli.utils.docker.run")
    def test_is_cache_ready_failure(self, mock_run):
        from cave_cli.utils.docker import is_cache_ready

        import subprocess

        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="Could not connect"
        )
        assert is_cache_ready("my_cache") is False

    @patch("cave_cli.utils.docker.is_container_running", return_value=True)
    @patch("cave_cli.utils.docker.is_cache_ready", return_value=True)
    @patch("cave_cli.utils.docker.run_detached")
    @patch("cave_cli.utils.docker.run")
    def test_start_and_verify_cache_success(
        self, mock_run, mock_run_detached, mock_ready, mock_running
    ):
        from cave_cli.utils.docker import start_and_verify_cache

        res = start_and_verify_cache(
            container_name="test_redis",
            image="valkey/valkey:7",
            network="test-net",
            volume_name="test_redis_volume",
        )
        assert res is True
        mock_run_detached.assert_called_once()

    @patch("cave_cli.utils.docker.get_container_logs")
    @patch("cave_cli.utils.docker.is_container_running", return_value=False)
    @patch("cave_cli.utils.docker.is_cache_ready", return_value=False)
    @patch("cave_cli.utils.docker.run_detached")
    @patch("cave_cli.utils.docker.run")
    def test_start_and_verify_cache_rdb_incompatibility(
        self,
        mock_run,
        mock_run_detached,
        mock_ready,
        mock_running,
        mock_logs,
    ):
        from cave_cli.utils.docker import start_and_verify_cache

        mock_logs.return_value = (
            "# Can't handle RDB format version 80\n"
            "# Fatal error loading the DB, check server logs. Exiting.\n"
        )
        res = start_and_verify_cache(
            container_name="test_redis",
            image="valkey/valkey:7",
            network="test-net",
            volume_name="test_redis_volume",
        )
        assert res is False
        # Volume should NOT have been removed
        for call_args in mock_run.call_args_list:
            cmd = call_args[0][0]
            assert not ("volume" in cmd and "rm" in cmd)

    @patch("cave_cli.utils.docker.is_container_running", return_value=False)
    @patch("cave_cli.utils.docker.run_and_log")
    def test_save_redis_not_running(self, mock_run_and_log, mock_running):
        from cave_cli.utils.docker import save_redis

        save_redis("my_app")
        mock_run_and_log.assert_not_called()

    @patch("cave_cli.utils.docker.is_container_running", return_value=True)
    @patch("cave_cli.utils.docker.run_and_log")
    def test_save_redis_running(self, mock_run_and_log, mock_running):
        from cave_cli.utils.docker import save_redis

        save_redis("my_app")
        mock_run_and_log.assert_called_once()

    @patch("cave_cli.commands.run.start_and_verify_cache", return_value=True)
    @patch("cave_cli.commands.run._stream_raw")
    @patch("cave_cli.commands.run._run_tui")
    @patch("cave_cli.commands.run.run_detached_logged")
    @patch("cave_cli.commands.run.find_open_port", return_value=8000)
    @patch("cave_cli.commands.run.create_network")
    @patch("cave_cli.commands.run.build_image")
    @patch("cave_cli.commands.run.remove_containers")
    def test_run_debug_loglevel_enables_raw_mode(
        self,
        mock_remove,
        mock_build,
        mock_net,
        mock_port,
        mock_run_detached_logged,
        mock_run_tui,
        mock_stream_raw,
        mock_start_cache,
        fake_app,
    ):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_run_detached_logged.return_value = mock_res

        args = argparse.Namespace(
            attach=False,
            detached=False,
            interactive=False,
            show_all=False,
            no_tui=False,
            raw=False,
            entrypoint=None,
            docker_args="",
            ip_port=None,
            log_lines=None,
            log_history=None,
            verbose=False,
            loglevel="DEBUG",
        )
        run_cave(fake_app[0], fake_app[1], args, skip_header=True)

        mock_stream_raw.assert_called_once()
        mock_run_tui.assert_not_called()


class TestDockerCacheAndHealth:
    @patch("cave_cli.utils.docker.run")
    def test_is_container_running(self, mock_run):
        from cave_cli.utils.docker import is_container_running

        import subprocess

        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="true\n"
        )
        assert is_container_running("my_container") is True

        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="false\n"
        )
        assert is_container_running("my_container") is False

        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout=""
        )
        assert is_container_running("my_container") is False

    @patch("cave_cli.utils.docker.run")
    def test_get_container_logs(self, mock_run):
        from cave_cli.utils.docker import get_container_logs

        import subprocess

        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="stdout line\n",
            stderr="stderr line\n",
        )
        logs = get_container_logs("my_container")
        assert "stdout line" in logs
        assert "stderr line" in logs

    @patch("cave_cli.utils.docker.run")
    def test_is_cache_ready_pong(self, mock_run):
        from cave_cli.utils.docker import is_cache_ready

        import subprocess

        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="PONG\n"
        )
        assert is_cache_ready("my_cache") is True

    @patch("cave_cli.utils.docker.run")
    def test_is_cache_ready_failure(self, mock_run):
        from cave_cli.utils.docker import is_cache_ready

        import subprocess

        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="Could not connect"
        )
        assert is_cache_ready("my_cache") is False

    @patch("cave_cli.utils.docker.is_container_running", return_value=True)
    @patch("cave_cli.utils.docker.is_cache_ready", return_value=True)
    @patch("cave_cli.utils.docker.run_detached")
    @patch("cave_cli.utils.docker.run")
    def test_start_and_verify_cache_success(
        self, mock_run, mock_run_detached, mock_ready, mock_running
    ):
        from cave_cli.utils.docker import start_and_verify_cache

        res = start_and_verify_cache(
            container_name="test_redis",
            image="valkey/valkey:7",
            network="test-net",
            volume_name="test_redis_volume",
        )
        assert res is True
        mock_run_detached.assert_called_once()

    @patch("cave_cli.utils.docker.get_container_logs")
    @patch("cave_cli.utils.docker.is_container_running", return_value=False)
    @patch("cave_cli.utils.docker.is_cache_ready", return_value=False)
    @patch("cave_cli.utils.docker.run_detached")
    @patch("cave_cli.utils.docker.run")
    def test_start_and_verify_cache_rdb_incompatibility(
        self,
        mock_run,
        mock_run_detached,
        mock_ready,
        mock_running,
        mock_logs,
    ):
        from cave_cli.utils.docker import start_and_verify_cache

        mock_logs.return_value = (
            "# Can't handle RDB format version 80\n"
            "# Fatal error loading the DB, check server logs. Exiting.\n"
        )
        res = start_and_verify_cache(
            container_name="test_redis",
            image="valkey/valkey:7",
            network="test-net",
            volume_name="test_redis_volume",
        )
        assert res is False
        # Volume should NOT have been removed
        for call_args in mock_run.call_args_list:
            cmd = call_args[0][0]
            assert not ("volume" in cmd and "rm" in cmd)

    @patch("cave_cli.utils.docker.is_container_running", return_value=False)
    @patch("cave_cli.utils.docker.run_and_log")
    def test_save_redis_not_running(self, mock_run_and_log, mock_running):
        from cave_cli.utils.docker import save_redis

        save_redis("my_app")
        mock_run_and_log.assert_not_called()

    @patch("cave_cli.utils.docker.is_container_running", return_value=True)
    @patch("cave_cli.utils.docker.run_and_log")
    def test_save_redis_running(self, mock_run_and_log, mock_running):
        from cave_cli.utils.docker import save_redis

        save_redis("my_app")
        mock_run_and_log.assert_called_once()
