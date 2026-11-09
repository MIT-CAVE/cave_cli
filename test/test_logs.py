import argparse
import os
import queue
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cave_cli.commands.logs import logs
from cave_cli.utils.docker import stream_container_logs
from cave_cli.utils.task_queue import (
    get_run_log_path,
    get_task_log_path,
    register_task,
)


@pytest.fixture
def fake_app(tmp_path: Path):
    app_dir = tmp_path / "sample_app"
    app_dir.mkdir()
    return str(app_dir), "sample_app"


class TestLogsCommand:
    @patch("cave_cli.commands.logs.get_app")
    def test_logs_path_flag(self, mock_get_app, fake_app, capsys):
        mock_get_app.return_value = fake_app
        args = argparse.Namespace(
            path=True,
            task=None,
            errors=False,
            follow=False,
            clear=False,
            lines=None,
        )
        logs(args)
        out, _ = capsys.readouterr()
        expected_path = get_run_log_path(fake_app[0])
        assert expected_path in out

    @patch("cave_cli.commands.logs.get_app")
    def test_logs_display_all(self, mock_get_app, fake_app, capsys):
        mock_get_app.return_value = fake_app
        log_path = get_run_log_path(fake_app[0])
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("line 1\nline 2\nline 3\n")

        args = argparse.Namespace(
            path=False,
            task=None,
            errors=False,
            follow=False,
            clear=False,
            lines=None,
        )
        logs(args)
        out, _ = capsys.readouterr()
        assert "line 1\nline 2\nline 3\n" == out

    @patch("cave_cli.commands.logs.get_app")
    def test_logs_lines_tail(self, mock_get_app, fake_app, capsys):
        mock_get_app.return_value = fake_app
        log_path = get_run_log_path(fake_app[0])
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("line 1\nline 2\nline 3\nline 4\n")

        args = argparse.Namespace(
            path=False,
            task=None,
            errors=False,
            follow=False,
            clear=False,
            lines=2,
        )
        logs(args)
        out, _ = capsys.readouterr()
        assert "line 3\nline 4\n" == out

    @patch("cave_cli.commands.logs.get_app")
    def test_logs_filter_errors(self, mock_get_app, fake_app, capsys):
        mock_get_app.return_value = fake_app
        log_path = get_run_log_path(fake_app[0])
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("INFO: healthy\nERROR: bad error\nDEBUG: detail\n")

        args = argparse.Namespace(
            path=False,
            task=None,
            errors=True,
            follow=False,
            clear=False,
            lines=None,
        )
        logs(args)
        out, _ = capsys.readouterr()
        assert "ERROR: bad error\n" == out
        assert "INFO: healthy" not in out

    @patch("cave_cli.commands.logs.get_app")
    def test_logs_clear(self, mock_get_app, fake_app):
        mock_get_app.return_value = fake_app
        log_path = get_run_log_path(fake_app[0])
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("some logs\n")

        args = argparse.Namespace(
            path=False,
            task=None,
            errors=False,
            follow=False,
            clear=True,
            lines=None,
        )
        logs(args)
        with open(log_path, "r", encoding="utf-8") as f:
            assert f.read() == ""

    @patch("cave_cli.commands.logs.get_app")
    def test_logs_task_specific(self, mock_get_app, fake_app, capsys):
        mock_get_app.return_value = fake_app
        t = register_task(fake_app[0], fake_app[1], "prettify", [])
        t_log = get_task_log_path(fake_app[0], t["id"])
        with open(t_log, "w", encoding="utf-8") as f:
            f.write("Task 1 output line\n")

        args = argparse.Namespace(
            path=False,
            task=t["id"],
            errors=False,
            follow=False,
            clear=False,
            lines=None,
        )
        logs(args)
        out, _ = capsys.readouterr()
        assert "Task 1 output line\n" in out

    @patch("cave_cli.commands.logs.get_app")
    def test_logs_task_latest(self, mock_get_app, fake_app, capsys):
        mock_get_app.return_value = fake_app
        register_task(fake_app[0], fake_app[1], "cmd1", [])
        t2 = register_task(fake_app[0], fake_app[1], "cmd2", [])
        t2_log = get_task_log_path(fake_app[0], t2["id"])
        with open(t2_log, "w", encoding="utf-8") as f:
            f.write("Latest task output\n")

        # task=0 indicates latest task
        args = argparse.Namespace(
            path=False,
            task=0,
            errors=False,
            follow=False,
            clear=False,
            lines=None,
        )
        logs(args)
        out, _ = capsys.readouterr()
        assert "Latest task output\n" in out


class TestLogStreamingBuffer:
    @patch("subprocess.Popen")
    def test_stream_container_logs_buffer_rotation(
        self, mock_popen, tmp_path: Path
    ):
        mock_proc = MagicMock()
        simulated_lines = [f"log line {i}\n" for i in range(1, 11)]
        mock_proc.stdout = iter(simulated_lines)
        mock_proc.terminate = MagicMock()
        mock_proc.wait = MagicMock()
        mock_popen.return_value = mock_proc

        log_file = tmp_path / "run.log"
        log_q = queue.Queue()
        stop_evt = threading.Event()

        stream_container_logs(
            container_name="test_django",
            log_queue=log_q,
            stop_event=stop_evt,
            log_file_path=str(log_file),
            max_log_lines=4,
        )

        assert log_file.exists()
        saved = log_file.read_text(encoding="utf-8").strip().splitlines()
        # Should have rotated and preserved only the last 4 lines: 7, 8, 9, 10
        assert len(saved) == 4
        assert saved == [
            "log line 7",
            "log line 8",
            "log line 9",
            "log line 10",
        ]

    def test_follow_file_live_streaming(self, tmp_path: Path):
        import time
        from cave_cli.commands.logs import _follow_file

        log_file = tmp_path / "follow_test.log"
        log_file.write_text("initial 1\ninitial 2\n", encoding="utf-8")

        streamed = []
        stop_evt = threading.Event()

        def mock_stdout_write(s: str) -> int:
            streamed.append(s)
            return len(s)

        with patch("sys.stdout.write", side_effect=mock_stdout_write):
            # Start following from end of file
            follow_thread = threading.Thread(
                target=_follow_file,
                kwargs={
                    "path": str(log_file),
                    "start_pos": log_file.stat().st_size,
                },
                daemon=True,
            )
            follow_thread.start()
            time.sleep(0.1)

            # Append new lines to file
            with open(log_file, "a", encoding="utf-8") as f:
                f.write("live line 1\n")
                f.flush()

            time.sleep(0.2)
            assert "live line 1\n" in streamed

            # Append another line
            with open(log_file, "a", encoding="utf-8") as f:
                f.write("live line 2\n")
                f.flush()

            time.sleep(0.2)
            assert "live line 2\n" in streamed

    def test_follow_file_handles_file_rotation(self, tmp_path: Path):
        import time
        from cave_cli.commands.logs import _follow_file

        log_file = tmp_path / "rotation_test.log"
        log_file.write_text("before rotation\n", encoding="utf-8")

        streamed = []

        def mock_stdout_write(s: str) -> int:
            streamed.append(s)
            return len(s)

        with patch("sys.stdout.write", side_effect=mock_stdout_write):
            follow_thread = threading.Thread(
                target=_follow_file,
                kwargs={
                    "path": str(log_file),
                    "start_pos": log_file.stat().st_size,
                },
                daemon=True,
            )
            follow_thread.start()
            time.sleep(0.1)

            # Rotate file by atomic replace (new inode)
            new_file = tmp_path / "rotation_test.log.tmp"
            new_file.write_text(
                "after rotation 1\nafter rotation 2\n", encoding="utf-8"
            )
            os.replace(new_file, log_file)

            time.sleep(0.3)
            # Must detect inode change and stream from new file
            assert any("after rotation 1" in s for s in streamed)
            assert any("after rotation 2" in s for s in streamed)
