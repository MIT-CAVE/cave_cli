import argparse
import os
import queue
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cave_cli.commands.logs import logs
from cave_cli.utils.docker import stream_container_logs
from cave_cli.utils.log_parser import LogParser
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


class TestLogParser:
    def test_strip_outer_prefixes(self):
        parser = LogParser()
        assert parser.strip_outer_prefixes("INFO: INFO: hello") == "hello"
        assert (
            parser.strip_outer_prefixes("INFO:   File 'test.py'")
            == "  File 'test.py'"
        )
        assert (
            parser.strip_outer_prefixes("INFO: error: ['panes', 'data']")
            == "error: ['panes', 'data']"
        )

    def test_parse_user_snippet(self):
        snippet = """INFO: INFO:     172.18.0.1:43294 - "GET /cave/auth/login/ HTTP/1.1" 200 OK
INFO: WS RECEIVE  mutate_session
INFO: Console Log: `myCommand` has been triggered!
INFO: error: ['panes', 'data', 'examplePropsPane', 'props', 'audioExample', 'variant']
INFO: \tInvalid value(s) selected: ['audio']. Accepted Values are ['picture', 'video']
INFO: The `test` button has been pressed by the user!
INFO: Traceback (most recent call last):
INFO:   File "/app/cave_core/utils/wrapping.py", line 103, in wrap
INFO:     fn(request)
INFO:     ~~^^^^^^^^^
INFO:   File "/app/cave_api/examples/kitchen_sink.py", line 2452, in execute_command
INFO:     raise Exception("Test Exception!")
INFO: Exception: Test Exception!
INFO: WS RECEIVE  session_management"""

        parser = LogParser()
        parsed = [parser.parse_line(line) for line in snippet.splitlines()]

        # 1. Access log -> DEBUG (noise)
        assert parsed[0].level == "DEBUG"
        assert parsed[0].is_noise is True

        # 2. WS RECEIVE -> DEBUG (noise)
        assert parsed[1].level == "DEBUG"
        assert parsed[1].is_noise is True

        # 3. Console log -> INFO
        assert parsed[2].level == "INFO"
        assert parsed[2].is_noise is False
        assert (
            "Console Log: `myCommand` has been triggered!" in parsed[2].message
        )

        # 4 & 5. Soft validation error -> ERROR
        assert parsed[3].level == "ERROR"
        assert parsed[3].is_error is True
        assert parsed[4].level == "ERROR"
        assert parsed[4].is_error is True

        # 6. User button press -> INFO
        assert parsed[5].level == "INFO"

        # 7-13. Traceback block -> all ERROR
        for entry in parsed[6:13]:
            assert (
                entry.level == "ERROR"
            ), f"Line '{entry.message}' should be ERROR"
            assert entry.is_error is True

        # 14. WS RECEIVE after traceback -> DEBUG (noise)
        assert parsed[13].level == "DEBUG"
        assert parsed[13].is_noise is True

    def test_ws_receive_formats(self):
        parser = LogParser()
        lines = [
            "INFO: WS RECEIVE  mutate_session",
            "INFO: WS RECEIVE command=mutate_session, api_command=myCommand",
            "INFO: WS RECEIVE command='mutate_session', api_command='myCommand'",
        ]
        for line in lines:
            parsed = parser.parse_line(line)
            assert parsed.level == "DEBUG"
            assert parsed.is_noise is True


class TestLogsCommand:
    @patch("cave_cli.commands.logs.get_app")
    def test_logs_path_flag(self, mock_get_app, fake_app, capsys):
        mock_get_app.return_value = fake_app
        args = argparse.Namespace(
            path=True,
            task=None,
            errors=False,
            warnings=False,
            all=False,
            raw=False,
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
            warnings=False,
            all=False,
            raw=True,
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
            warnings=False,
            all=False,
            raw=True,
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
            f.write(
                "INFO: healthy\n"
                "INFO: error: ['panes', 'data']\n"
                "INFO: \tInvalid value(s)\n"
                "DEBUG: detail\n"
            )

        args = argparse.Namespace(
            path=False,
            task=None,
            errors=True,
            warnings=False,
            all=False,
            raw=False,
            follow=False,
            clear=False,
            lines=None,
            no_color=True,
        )
        logs(args)
        out, _ = capsys.readouterr()
        assert "ERROR: error: ['panes', 'data']\n" in out
        assert "ERROR: \tInvalid value(s)\n" in out
        assert "healthy" not in out
        assert "detail" not in out

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
            warnings=False,
            all=False,
            raw=False,
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
            warnings=False,
            all=False,
            raw=True,
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

        args = argparse.Namespace(
            path=False,
            task=0,
            errors=False,
            warnings=False,
            all=False,
            raw=True,
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
            "INFO: log line 7",
            "INFO: log line 8",
            "INFO: log line 9",
            "INFO: log line 10",
        ]

    def test_follow_file_live_streaming(self, tmp_path: Path):
        import time
        from cave_cli.commands.logs import _follow_file

        log_file = tmp_path / "follow_test.log"
        log_file.write_text("initial 1\ninitial 2\n", encoding="utf-8")

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
                    "raw_mode": True,
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
            assert any("live line 1" in s for s in streamed)

            # Append another line
            with open(log_file, "a", encoding="utf-8") as f:
                f.write("live line 2\n")
                f.flush()

            time.sleep(0.2)
            assert any("live line 2" in s for s in streamed)

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
                    "raw_mode": True,
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
