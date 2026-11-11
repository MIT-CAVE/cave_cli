from unittest.mock import MagicMock, patch
import pytest
from cave_cli.utils.display import (
    ALT_SCREEN_ENTER,
    ALT_SCREEN_EXIT,
    ALT_SCROLL_ENTER,
    ALT_SCROLL_EXIT,
    CLEAR_BELOW,
    MOUSE_ENTER,
    MOUSE_EXIT,
    MODE_ALL,
    MODE_LIFECYCLE,
    MODE_STANDARD,
    MODE_VERBOSE,
    DashboardRenderer,
    LifecycleEvent,
    LogFilter,
    LogLine,
    RunDashboard,
    StackComponent,
    READY,
    LOADING,
    RELOADING,
    RED,
    YELLOW,
    step_done,
    step_fail,
    step_start,
)


class TestLogFilter:
    def test_strip_level_prefix(self):
        filter_obj = LogFilter()
        assert (
            filter_obj.strip_level_prefix(
                "INFO:     Started server process [134449]"
            )
            == "Started server process [134449]"
        )
        assert (
            filter_obj.strip_level_prefix(
                "INFO: INFO:     Started server process [134449]"
            )
            == "Started server process [134449]"
        )
        assert (
            filter_obj.strip_level_prefix("WARNING: Connection lost")
            == "Connection lost"
        )
        assert (
            filter_obj.strip_level_prefix("connection open")
            == "connection open"
        )

    def test_ws_event(self):
        filter_obj = LogFilter()
        # Old Channels
        assert filter_obj.ws_event("WebSocket CONNECT /ws/") == "connect"
        assert filter_obj.ws_event("WebSocket DISCONNECT /ws/") == "disconnect"

        # Custom markers
        assert filter_obj.ws_event("SOCKET CONNECTION OPENED") == "connect"
        assert filter_obj.ws_event("SOCKET CONNECTION CLOSED") == "disconnect"

        # New Uvicorn vanilla markers should not be classified as events to avoid double counting
        assert filter_obj.ws_event("connection open") is None
        assert filter_obj.ws_event("connection closed") is None

        # Other logs
        assert filter_obj.ws_event("some other message") is None

    def test_classify_status(self):
        filter_obj = LogFilter()
        assert (
            filter_obj.classify_status("Application startup complete.") == READY
        )
        assert (
            filter_obj.classify_status("Started server process [134449]")
            == LOADING
        )
        assert (
            filter_obj.classify_status(
                "detected changes in 'app.py', reloading"
            )
            == RELOADING
        )
        assert (
            filter_obj.classify_status(
                "StatReload detected file change in 'app.py' - Reloading..."
            )
            == RELOADING
        )
        assert filter_obj.classify_status("Reloading...") == RELOADING
        assert filter_obj.classify_status("Just some logging") is None

    def test_is_noise(self):
        filter_obj = LogFilter()
        assert filter_obj.is_noise("connection open") is True
        assert filter_obj.is_noise("connection closed") is True
        assert filter_obj.is_noise("SOCKET CONNECTION OPENED") is True
        assert filter_obj.is_noise("WebSocket CONNECT /ws/") is True
        assert filter_obj.is_noise("Started server process ") is True
        assert (
            filter_obj.is_noise(
                "Will watch for changes in these directories: ['/app']"
            )
            is True
        )
        assert (
            filter_obj.is_noise(
                "Started reloader process [48] using StatReload"
            )
            is True
        )
        assert (
            filter_obj.is_noise(
                "WS RECEIVE command=mutate_session, api_command=myCommand"
            )
            is True
        )
        assert (
            filter_obj.is_noise(
                "WS RECEIVE command='mutate_session', api_command='myCommand'"
            )
            is True
        )
        assert filter_obj.is_noise("WS RECEIVE  mutate_session") is True
        assert filter_obj.is_noise("some actual log line") is False

    def test_strip_level_prefix_preserves_soft_validation(self):
        filter_obj = LogFilter()
        assert (
            filter_obj.strip_level_prefix("INFO: error: ['panes', 'data']")
            == "error: ['panes', 'data']"
        )
        assert (
            filter_obj.strip_level_prefix("INFO: warning: ['panes', 'data']")
            == "warning: ['panes', 'data']"
        )

    def test_is_validation_issue(self):
        filter_obj = LogFilter()
        assert (
            filter_obj.is_validation_issue(
                "INFO: error: ['panes']", "error: ['panes']"
            )
            is True
        )
        assert (
            filter_obj.is_validation_issue(
                "INFO: warning: ['panes']", "warning: ['panes']"
            )
            is True
        )
        assert (
            filter_obj.is_validation_issue(
                "INFO: \tUnknown Fields: ['a']", "\tUnknown Fields: ['a']"
            )
            is True
        )
        assert (
            filter_obj.is_validation_issue(
                "INFO: \tInvalid value(s) selected: ['a']",
                "\tInvalid value(s) selected: ['a']",
            )
            is True
        )
        assert (
            filter_obj.is_validation_issue(
                "INFO: Application startup complete.",
                "Application startup complete.",
            )
            is False
        )
        assert (
            filter_obj.is_validation_issue(
                "INFO: changed, reloading", "changed, reloading"
            )
            is False
        )


class TestRunDashboard:
    def test_reload_log_entry(self):
        dashboard = RunDashboard(
            app_name="test_app", url="http://localhost:8000"
        )
        assert len(dashboard._log_lines) == 1
        assert dashboard._log_lines[0].text == "App Loading"

        dashboard._process_line("INFO:     Application startup complete.")
        assert dashboard._log_lines[-1].text == "App Ready"

        dashboard._process_line(
            "WARNING:  StatReload detected file change in 'app.py' - Reloading..."
        )
        assert dashboard._log_lines[-1].text == "App Reloading"
        assert dashboard._log_lines[-1].raw == "INFO: App Reloading"

        dashboard._process_line("INFO:     Application startup complete.")
        assert dashboard._log_lines[-1].text == "App Ready"

    def test_dashboard_detach(self):
        dashboard = RunDashboard(
            app_name="test_app", url="http://localhost:8000"
        )
        assert dashboard.is_detached is False
        assert dashboard._stop_event.is_set() is False
        dashboard.detach()
        assert dashboard.is_detached is True
        assert dashboard._stop_event.is_set() is True

    @patch("cave_cli.utils.display.sys.stdin.fileno", return_value=0)
    @patch("cave_cli.utils.display.termios")
    @patch("cave_cli.utils.display.tty")
    @patch("cave_cli.utils.display.os.read")
    @patch("cave_cli.utils.display.select.select")
    def test_input_loop_unix_arrow_keys_do_not_detach(
        self, mock_select, mock_read, mock_tty, mock_termios, mock_fileno
    ):
        dashboard = RunDashboard(app_name="app", url="http://localhost:8000")
        dashboard._show_all = True
        mock_select.return_value = ([0], [], [])

        def read_up_then_stop(*args, **kwargs):
            dashboard._stop_event.set()
            return b"\x1b[A"

        mock_read.side_effect = read_up_then_stop

        with patch.object(dashboard, "scroll_up") as mock_scroll_up:
            with patch.object(dashboard, "detach") as mock_detach:
                dashboard._input_loop_unix()
                mock_scroll_up.assert_called_once()
                mock_detach.assert_not_called()
                assert dashboard.is_detached is False

    @patch("cave_cli.utils.display.sys.stdin.fileno", return_value=0)
    @patch("cave_cli.utils.display.termios")
    @patch("cave_cli.utils.display.tty")
    @patch("cave_cli.utils.display.os.read")
    @patch("cave_cli.utils.display.select.select")
    def test_input_loop_unix_esc_detaches(
        self, mock_select, mock_read, mock_tty, mock_termios, mock_fileno
    ):
        dashboard = RunDashboard(app_name="app", url="http://localhost:8000")
        mock_select.side_effect = [
            ([0], [], []),
            ([], [], []),
        ]

        def read_esc_then_stop(*args, **kwargs):
            return b"\x1b"

        mock_read.side_effect = read_esc_then_stop

        dashboard._input_loop_unix()
        assert dashboard.is_detached is True

    def test_mode_cycling(self):
        dashboard = RunDashboard(
            app_name="app",
            url="http://localhost:8000",
            initial_mode=MODE_LIFECYCLE,
        )
        assert dashboard.mode == MODE_LIFECYCLE
        assert dashboard._show_all is False

        # Forward cycling: LIFECYCLE -> STANDARD -> ALL -> VERBOSE -> LIFECYCLE
        dashboard.cycle_mode(forward=True)
        assert dashboard.mode == MODE_STANDARD
        assert dashboard._show_all is False

        dashboard.cycle_mode(forward=True)
        assert dashboard.mode == MODE_ALL
        assert dashboard._show_all is True

        dashboard.cycle_mode(forward=True)
        assert dashboard.mode == MODE_VERBOSE
        assert dashboard._show_all is False

        dashboard.cycle_mode(forward=True)
        assert dashboard.mode == MODE_LIFECYCLE
        assert dashboard._show_all is False

        # Backward cycling: LIFECYCLE -> VERBOSE -> ALL -> STANDARD -> LIFECYCLE
        dashboard.cycle_mode(forward=False)
        assert dashboard.mode == MODE_VERBOSE

        dashboard.cycle_mode(forward=False)
        assert dashboard.mode == MODE_ALL

        dashboard.cycle_mode(forward=False)
        assert dashboard.mode == MODE_STANDARD

        dashboard.cycle_mode(forward=False)
        assert dashboard.mode == MODE_LIFECYCLE

    def test_set_mode_screen_transitions(self, monkeypatch):
        written: list[str] = []
        monkeypatch.setattr(
            "cave_cli.utils.display.sys.stdout.write",
            lambda s: written.append(s),
        )
        monkeypatch.setattr(
            "cave_cli.utils.display.sys.stdout.flush", lambda: None
        )

        dashboard = RunDashboard(app_name="app", url="http://localhost:8000")
        written.clear()

        # Standard -> Verbose transitions mode without exiting to primary
        dashboard.set_mode(MODE_VERBOSE)
        assert dashboard.mode == MODE_VERBOSE
        assert not any(ALT_SCREEN_EXIT in s for s in written)

        written.clear()
        # Verbose -> Standard transitions mode
        dashboard.set_mode(MODE_STANDARD)
        assert dashboard.mode == MODE_STANDARD
        assert not any(ALT_SCREEN_ENTER in s for s in written)

        # Stop while in standard mode: exits alt screen without dumping verbose logs
        written.clear()
        dashboard.stop()
        assert any(ALT_SCREEN_EXIT in s for s in written)
        assert any(ALT_SCROLL_EXIT in s for s in written)
        assert any(CLEAR_BELOW in s for s in written)
        assert not any("Verbose Mode" in s for s in written)

    def test_stop_in_verbose_mode_flushes_to_terminal(self, monkeypatch):
        written: list[str] = []
        monkeypatch.setattr(
            "cave_cli.utils.display.sys.stdout.write",
            lambda s: written.append(s),
        )
        monkeypatch.setattr(
            "cave_cli.utils.display.sys.stdout.flush", lambda: None
        )

        dashboard = RunDashboard(app_name="app", url="http://localhost:8000")
        dashboard._all_log_lines.append(
            LogLine(
                timestamp="16:00:00",
                text="Server started",
                raw="INFO: Server started",
            )
        )
        dashboard.set_mode(MODE_VERBOSE)
        written.clear()

        # Stop while in verbose mode: exits alt screen and dumps logs to primary screen
        dashboard.stop()
        full_out = "".join(written)
        assert ALT_SCREEN_EXIT in full_out
        assert "Verbose Mode" in full_out
        assert "INFO: Server started" in full_out

    @patch("cave_cli.utils.display.sys.stdin.fileno", return_value=0)
    @patch("cave_cli.utils.display.termios")
    @patch("cave_cli.utils.display.tty")
    @patch("cave_cli.utils.display.os.read")
    @patch("cave_cli.utils.display.select.select")
    def test_input_loop_unix_tab_cycles_mode(
        self, mock_select, mock_read, mock_tty, mock_termios, mock_fileno
    ):
        dashboard = RunDashboard(app_name="app", url="http://localhost:8000")
        mock_select.return_value = ([0], [], [])

        def read_tab_then_stop(*args, **kwargs):
            dashboard._stop_event.set()
            return b"\t"

        mock_read.side_effect = read_tab_then_stop

        with patch.object(dashboard, "cycle_mode") as mock_cycle:
            dashboard._input_loop_unix()
            mock_cycle.assert_called_once_with(forward=True)

    @patch("cave_cli.utils.display.sys.stdin.fileno", return_value=0)
    @patch("cave_cli.utils.display.termios")
    @patch("cave_cli.utils.display.tty")
    @patch("cave_cli.utils.display.os.read")
    @patch("cave_cli.utils.display.select.select")
    def test_input_loop_unix_shift_tab_cycles_backward(
        self, mock_select, mock_read, mock_tty, mock_termios, mock_fileno
    ):
        dashboard = RunDashboard(app_name="app", url="http://localhost:8000")
        mock_select.return_value = ([0], [], [])

        def read_shift_tab_then_stop(*args, **kwargs):
            dashboard._stop_event.set()
            return b"\x1b[Z"

        mock_read.side_effect = read_shift_tab_then_stop

        with patch.object(dashboard, "cycle_mode") as mock_cycle:
            dashboard._input_loop_unix()
            mock_cycle.assert_called_once_with(forward=False)

    @patch("cave_cli.utils.display.sys.stdin.fileno", return_value=0)
    @patch("cave_cli.utils.display.termios")
    @patch("cave_cli.utils.display.tty")
    @patch("cave_cli.utils.display.os.read")
    @patch("cave_cli.utils.display.select.select")
    def test_input_loop_unix_mouse_wheel_sgr(
        self, mock_select, mock_read, mock_tty, mock_termios, mock_fileno
    ):
        dashboard = RunDashboard(app_name="app", url="http://localhost:8000")
        dashboard._show_all = True
        mock_select.return_value = ([0], [], [])

        chunks = [b"\x1b[<64;10;10M", b"\x1b[<65;10;10M"]

        def read_wheel_then_stop(*args, **kwargs):
            if chunks:
                return chunks.pop(0)
            dashboard._stop_event.set()
            return b""

        mock_read.side_effect = read_wheel_then_stop

        with patch.object(dashboard, "scroll_up") as mock_up:
            with patch.object(dashboard, "scroll_down") as mock_down:
                dashboard._input_loop_unix()
                mock_up.assert_called_once_with(3)
                mock_down.assert_called_once_with(3)

    @patch("cave_cli.utils.display.sys.stdin.fileno", return_value=0)
    @patch("cave_cli.utils.display.termios")
    @patch("cave_cli.utils.display.tty")
    @patch("cave_cli.utils.display.os.read")
    @patch("cave_cli.utils.display.select.select")
    def test_input_loop_unix_mouse_wheel_x11(
        self, mock_select, mock_read, mock_tty, mock_termios, mock_fileno
    ):
        dashboard = RunDashboard(app_name="app", url="http://localhost:8000")
        dashboard._show_all = True
        mock_select.return_value = ([0], [], [])

        chunks = [b"\x1b[M\x60  ", b"\x1b[M\x61  "]

        def read_wheel_then_stop(*args, **kwargs):
            if chunks:
                return chunks.pop(0)
            dashboard._stop_event.set()
            return b""

        mock_read.side_effect = read_wheel_then_stop

        with patch.object(dashboard, "scroll_up") as mock_up:
            with patch.object(dashboard, "scroll_down") as mock_down:
                dashboard._input_loop_unix()
                mock_up.assert_called_once_with(3)
                mock_down.assert_called_once_with(3)

    @patch("cave_cli.utils.display.sys.stdin.fileno", return_value=0)
    @patch("cave_cli.utils.display.termios")
    @patch("cave_cli.utils.display.tty")
    @patch("cave_cli.utils.display.os.read")
    @patch("cave_cli.utils.display.select.select")
    def test_input_loop_unix_ctrl_c_stops_not_detaches(
        self, mock_select, mock_read, mock_tty, mock_termios, mock_fileno
    ):
        dashboard = RunDashboard(app_name="app", url="http://localhost:8000")
        mock_select.return_value = ([0], [], [])

        def read_ctrl_c(*args, **kwargs):
            return b"\x03"

        mock_read.side_effect = read_ctrl_c

        dashboard._input_loop_unix()
        assert dashboard._stop_event.is_set()
        assert dashboard.is_detached is False

    def test_verbose_mode_log_streaming(self):
        dashboard = RunDashboard(
            app_name="app",
            url="http://localhost:8000",
            initial_mode=MODE_VERBOSE,
        )
        dashboard._process_line("INFO: Testing verbose line streaming")
        assert len(dashboard._all_log_lines) >= 2
        assert any(
            "Testing verbose line streaming" in e.raw
            for e in dashboard._all_log_lines
        )

    def test_process_validation_and_warning_sequence(self):
        dashboard = RunDashboard(
            app_name="test_app", url="http://localhost:8000"
        )
        sequence = [
            "INFO: warning: ['panes', 'data', 'examplePane', 'props', 'pictureExample']",
            "INFO: \tUnknown Fields: ['scaleMode']",
            "INFO: error: ['panes', 'data', 'examplePane', 'props', 'audioExample', 'variant']",
            "INFO: \tInvalid value(s) selected: ['audio']. Accepted Values are ['picture', 'video']",
            "INFO: WS RECEIVE  mutate_session",
            "INFO: The `test` button has been pressed by the user!",
        ]
        for line in sequence:
            dashboard._process_line(line)

        # 1. Total validation count should be 2 (1 warning block + 1 error block)
        assert dashboard._validation_count == 2

        # 2. Check all lines classification in _all_log_lines
        # (index 0 is initial "App Loading")
        all_entries = dashboard._all_log_lines[1:]
        assert all_entries[0].level == "WARN"
        assert all_entries[0].is_validation is True
        assert all_entries[1].level == "WARN"
        assert all_entries[1].is_validation is True
        assert all_entries[2].level == "ERROR"
        assert all_entries[2].is_validation is True
        assert all_entries[3].level == "ERROR"
        assert all_entries[3].is_validation is True
        assert all_entries[4].level == "DEBUG"
        assert all_entries[4].is_validation is False
        assert all_entries[5].level == "INFO"
        assert all_entries[5].is_validation is False

        # 3. WS RECEIVE should NOT be in minimal _log_lines
        minimal_texts = [e.text for e in dashboard._log_lines]
        assert not any("WS RECEIVE" in t for t in minimal_texts)
        assert any("test` button has been pressed" in t for t in minimal_texts)


class TestDashboardRenderer:
    def test_render_show_all_levels(self, capsys):
        renderer = DashboardRenderer()
        logs = [
            LogLine(
                timestamp="16:15:52",
                text="warning: ['panes']",
                raw="INFO: warning: ['panes']",
                level="WARN",
                message="warning: ['panes']",
                is_validation=True,
            ),
            LogLine(
                timestamp="16:15:52",
                text="error: ['panes']",
                raw="INFO: error: ['panes']",
                level="ERROR",
                message="error: ['panes']",
                is_validation=True,
            ),
            LogLine(
                timestamp="16:15:52",
                text="WS RECEIVE  mutate",
                raw="INFO: WS RECEIVE  mutate",
                level="DEBUG",
                message="WS RECEIVE  mutate",
            ),
        ]
        renderer.render(
            app_name="sample",
            status=READY,
            url="http://localhost:8000",
            ws_clients=1,
            log_lines=logs,
            validation_count=2,
            current_error_block=[],
            show_all=True,
        )
        captured = capsys.readouterr().out
        assert "WARN: warning: ['panes']" in captured
        assert "ERROR: error: ['panes']" in captured
        assert "DEBUG: WS RECEIVE  mutate" in captured
        assert "Esc to detach" in captured

    def test_render_minimal_warning_header(self, capsys):
        renderer = DashboardRenderer()
        warnings = [
            LogLine(
                timestamp="16:15:52",
                text="warning: ['panes']",
                raw="INFO: warning: ['panes']",
                level="WARN",
                message="warning: ['panes']",
                is_validation=True,
            ),
            LogLine(
                timestamp="16:15:52",
                text="Unknown Fields: ['a']",
                raw="INFO: Unknown Fields: ['a']",
                level="WARN",
                message="Unknown Fields: ['a']",
                is_validation=True,
            ),
        ]
        renderer.render(
            app_name="sample",
            status=READY,
            url="http://localhost:8000",
            ws_clients=1,
            log_lines=[],
            validation_count=1,
            current_error_block=warnings,
            show_all=False,
        )
        captured = capsys.readouterr().out
        assert "Validation Warnings" in captured
        assert "(1 warning)" in captured

    def test_render_lifecycle_view(self, capsys):
        renderer = DashboardRenderer()
        components = [
            StackComponent(
                name="App Server",
                image="cave-app:app",
                container="app_django",
                status="Loading App",
            ),
            StackComponent(
                name="Database",
                image="postgres:15",
                container="app_db",
                status="Starting",
            ),
        ]
        events = [
            LifecycleEvent(
                timestamp="15:30:00",
                text="Network created",
                status="ok",
            ),
            LifecycleEvent(
                timestamp="15:30:02",
                text="Starting Django application server",
                status="ok",
            ),
            LifecycleEvent(
                timestamp="15:30:05",
                text="Loading App",
                status="pending",
            ),
        ]
        renderer.render(
            app_name="app",
            status=LOADING,
            url="http://localhost:8000",
            ws_clients=0,
            log_lines=[],
            validation_count=0,
            current_error_block=[],
            mode=MODE_LIFECYCLE,
            components=components,
            lifecycle_events=events,
        )
        captured = capsys.readouterr().out
        assert "LIFECYCLE" in captured
        assert "Stack Components" in captured
        assert "App Server" in captured
        assert "[Loading App]" in captured
        assert "Database" in captured
        assert "[Starting]" in captured
        assert "Lifecycle Timeline" in captured
        assert "Network created" in captured
        assert "Starting Django application server" in captured
        assert "Loading App" in captured
        assert "Tab / Shift+Tab to cycle" in captured

    def test_step_start_and_done_updates_dashboard(self):
        dashboard = RunDashboard(app_name="app", url="http://localhost:8000")
        dashboard._display_thread = MagicMock()
        dashboard._display_thread.is_alive.return_value = True

        from cave_cli.utils import display

        display._active_dashboard = dashboard
        try:
            step_start("Starting database")
            assert len(dashboard._lifecycle_events) == 1
            assert dashboard._lifecycle_events[0].status == "pending"
            assert "Starting database" in dashboard._lifecycle_events[0].text

            step_done("Starting database")
            assert len(dashboard._lifecycle_events) == 2
            assert dashboard._lifecycle_events[1].status == "ok"

            step_fail("Checking database", "Connection timed out")
            assert len(dashboard._lifecycle_events) == 3
            assert dashboard._lifecycle_events[2].status == "error"
            assert "Connection timed out" in dashboard._lifecycle_events[2].text
        finally:
            display._active_dashboard = None

    def test_flush_verbose_backlog_with_startup_logs(self, monkeypatch):
        written: list[str] = []
        monkeypatch.setattr(
            "cave_cli.utils.display.sys.stdout.write",
            lambda s: written.append(s),
        )
        monkeypatch.setattr(
            "cave_cli.utils.display.sys.stdout.flush", lambda: None
        )

        dashboard = RunDashboard(app_name="app", url="http://localhost:8000")
        dashboard.add_startup_log("docker run -d postgres:latest")
        dashboard.add_startup_log("docker run -d valkey/valkey:7")

        dashboard._all_log_lines.append(
            LogLine(
                timestamp="15:30:10",
                text="Django booted",
                raw="INFO: Django booted",
            )
        )

        dashboard.set_mode(MODE_VERBOSE)
        dashboard.stop()
        full_out = "".join(written)
        assert "[startup]" in full_out
        assert "docker run -d postgres:latest" in full_out
        assert "INFO: Django booted" in full_out

    def test_verbose_mode_scrolling(self, capsys):
        renderer = DashboardRenderer()
        logs = [
            LogLine(
                timestamp=f"12:00:{i:02d}",
                text=f"line {i}",
                raw=f"INFO: line {i}",
            )
            for i in range(50)
        ]
        startup = ["docker run 1", "docker run 2"]

        # 1. Render bottom (no scroll)
        renderer.render(
            app_name="app",
            status="ready",
            url="http://localhost:8000",
            ws_clients=0,
            log_lines=logs,
            validation_count=0,
            current_error_block=[],
            mode=MODE_VERBOSE,
            scroll_offset=0,
            startup_logs=startup,
        )
        captured = capsys.readouterr().out
        assert "VERBOSE" in captured
        assert "INFO: line 49" in captured
        assert "↑/↓ to scroll" in captured

        # 2. Render scrolled up by 40 lines
        renderer.render(
            app_name="app",
            status="ready",
            url="http://localhost:8000",
            ws_clients=0,
            log_lines=logs,
            validation_count=0,
            current_error_block=[],
            mode=MODE_VERBOSE,
            scroll_offset=40,
            startup_logs=startup,
        )
        scrolled_out = capsys.readouterr().out
        assert "[startup]" in scrolled_out
        assert "INFO: line 0" in scrolled_out

    def test_dashboard_verbose_scroll_methods(self):
        dashboard = RunDashboard(
            app_name="app",
            url="http://localhost:8000",
            initial_mode=MODE_VERBOSE,
        )
        for i in range(100):
            dashboard._all_log_lines.append(
                LogLine(
                    timestamp="10:00:00",
                    text=f"log {i}",
                    raw=f"INFO: log {i}",
                )
            )
        dashboard.add_startup_log("startup cmd")

        assert dashboard._scroll_offset == 0
        dashboard.scroll_up(10)
        assert dashboard._scroll_offset == 10

        dashboard.scroll_up(5)
        assert dashboard._scroll_offset == 15

        dashboard.scroll_down(7)
        assert dashboard._scroll_offset == 8

        dashboard.scroll_down(20)
        assert dashboard._scroll_offset == 0

    def test_loading_app_lifecycle_flow(self):
        from cave_cli.utils import display

        dashboard = RunDashboard(
            app_name="app",
            url="http://localhost:8000",
            initial_mode=MODE_LIFECYCLE,
        )
        dashboard.set_components(
            [
                StackComponent(
                    name="App Server",
                    image="cave-app:app",
                    container="app_django",
                    status="Pending",
                )
            ]
        )
        display._active_dashboard = dashboard
        try:
            # 1. Starting Django
            step_start("Starting Django")
            assert dashboard._components[0].status == "Starting"

            # 2. Django started -> App Server running
            step_done("Starting Django")
            assert dashboard._components[0].status == "Running"

            # 3. Loading App initiated
            step_start("Loading App")
            assert dashboard._app_loading is True
            assert dashboard._components[0].status == "Loading App"
            assert any(
                ev.text == "Loading App" and ev.status == "pending"
                for ev in dashboard._lifecycle_events
            )

            # 4. App finishes loading -> READY trigger received
            dashboard._process_line("INFO: Application startup complete.")
            assert dashboard._app_loading is False
            assert dashboard._components[0].status == "Ready"
            assert any(
                ev.text == "Loading App" and ev.status == "ok"
                for ev in dashboard._lifecycle_events
            )
            assert any(
                "App Server ready at" in ev.text and ev.status == "ok"
                for ev in dashboard._lifecycle_events
            )
            # Auto-advanced to MODE_STANDARD
            assert dashboard.mode == MODE_STANDARD
        finally:
            display._active_dashboard = None

    def test_lifecycle_screen_leading_bar_fits(self, capsys):
        import os
        import shutil

        renderer = DashboardRenderer()
        components = [
            StackComponent(
                "App Server", "cave-app:app", "app_django", "Pending"
            ),
            StackComponent("Database", "postgres", "app_db", "Pending"),
            StackComponent("Cache", "valkey", "app_redis", "Pending"),
            StackComponent("Network", "bridge", "app_net", "Pending"),
        ]
        events = [
            LifecycleEvent("12:00:00", f"Event {i}", "ok") for i in range(20)
        ]

        with patch(
            "shutil.get_terminal_size", return_value=os.terminal_size((80, 24))
        ):
            renderer.render(
                app_name="test_app",
                status=LOADING,
                url="http://localhost:8000",
                ws_clients=0,
                log_lines=[],
                validation_count=0,
                current_error_block=[],
                mode=MODE_LIFECYCLE,
                components=components,
                lifecycle_events=events,
            )

        captured = capsys.readouterr().out
        # Line count should be <= 23 (budget = rows - 1) so it never scrolls
        lines = captured.split("\n")
        assert len(lines) <= 23
        # Leading bar should be present in the very first line
        assert "━" in lines[0]

    def test_prompt_rendering_and_budget(self, capsys):
        import os

        renderer = DashboardRenderer()
        with patch(
            "shutil.get_terminal_size", return_value=os.terminal_size((80, 24))
        ):
            renderer.render(
                app_name="test_app",
                status=LOADING,
                url="http://localhost:8000",
                ws_clients=0,
                log_lines=[],
                validation_count=0,
                current_error_block=[],
                mode=MODE_LIFECYCLE,
                prompt_message="The database is not set up.",
                prompt_options="[y/N]",
                prompt_buffer="y",
            )

        captured = capsys.readouterr().out
        lines = captured.split("\n")
        assert len(lines) <= 23
        assert "The database is not set up." in captured
        assert "Continue? [y/N]" in captured
        assert "\033[?25l" in captured  # Cursor hide

    def test_dashboard_prompt_and_confirm(self):
        import threading
        from cave_cli.utils.display import RunDashboard

        stop_ev = threading.Event()
        dashboard = RunDashboard(
            "app", "http://localhost:8000", stop_event=stop_ev
        )

        # auto_yes confirms without prompting
        assert dashboard.confirm("Prompt?", auto_yes=True) is True

        # Simulate user typing 'y' and pressing Enter
        def user_response():
            # Wait until prompt is active
            while not dashboard._prompt_active:
                pass
            dashboard._prompt_buffer = "y"
            dashboard._prompt_result = "y"
            dashboard._prompt_event.set()

        t = threading.Thread(target=user_response)
        t.start()
        res = dashboard.confirm("Initialize DB?", continue_on_no=True)
        t.join()
        assert res is True

        # Simulate user typing 'n' and pressing Enter with continue_on_no
        def user_no():
            while not dashboard._prompt_active:
                pass
            dashboard._prompt_buffer = "n"
            dashboard._prompt_result = "n"
            dashboard._prompt_event.set()

        t2 = threading.Thread(target=user_no)
        t2.start()
        res_no = dashboard.confirm("Initialize DB?", continue_on_no=True)
        t2.join()
        assert res_no is False

    def test_all_mode_headers_present(self, capsys):
        import os
        from cave_cli.utils.display import (
            GREEN,
            BOLD,
            CYAN,
            YELLOW,
            DashboardRenderer,
            MODE_LIFECYCLE,
            MODE_STANDARD,
            MODE_ALL,
            MODE_VERBOSE,
            READY,
        )

        renderer = DashboardRenderer()
        modes_expected = [
            (MODE_LIFECYCLE, "LIFECYCLE", CYAN),
            (MODE_STANDARD, "LOGS", CYAN),
            (MODE_ALL, "DETAILED", CYAN),
            (MODE_VERBOSE, "VERBOSE", CYAN),
        ]

        with patch(
            "shutil.get_terminal_size", return_value=os.terminal_size((80, 24))
        ):
            for m, label, color in modes_expected:
                renderer.render(
                    app_name="test_app",
                    status=READY,
                    url="http://localhost:8000",
                    ws_clients=0,
                    log_lines=[],
                    validation_count=0,
                    current_error_block=[],
                    mode=m,
                )
                captured = capsys.readouterr().out
                first_line = captured.split("\n")[1]
                assert label in first_line
                assert f"{color}{BOLD}{label}" in first_line

    def test_render_exception_filters_traceback_and_limits_to_five(
        self, capsys
    ):
        import os

        renderer = DashboardRenderer()
        # 7 distinct actual error lines + traceback frames mixed in
        entries = [
            LogLine(
                timestamp="10:00:00",
                text="Traceback (most recent call last):",
                raw="Traceback (most recent call last):",
                level="ERROR",
                is_validation=True,
                is_traceback=True,
            ),
            LogLine(
                timestamp="10:00:00",
                text='  File "/app/test.py", line 12, in bad_func',
                raw='  File "/app/test.py", line 12, in bad_func',
                level="ERROR",
                is_validation=True,
                is_traceback=True,
            ),
            LogLine(
                timestamp="10:00:00",
                text="    1 / 0",
                raw="    1 / 0",
                level="ERROR",
                is_validation=True,
                is_traceback=True,
            ),
            LogLine(
                timestamp="10:00:01",
                text="Error 1: initial failure",
                raw="ERROR: Error 1: initial failure",
                level="ERROR",
                is_validation=True,
                is_traceback=False,
            ),
            LogLine(
                timestamp="10:00:02",
                text="Error 2: second failure",
                raw="ERROR: Error 2: second failure",
                level="ERROR",
                is_validation=True,
                is_traceback=False,
            ),
            LogLine(
                timestamp="10:00:03",
                text="Error 3: third failure",
                raw="ERROR: Error 3: third failure",
                level="ERROR",
                is_validation=True,
                is_traceback=False,
            ),
            LogLine(
                timestamp="10:00:04",
                text="Error 4: fourth failure",
                raw="ERROR: Error 4: fourth failure",
                level="ERROR",
                is_validation=True,
                is_traceback=False,
            ),
            LogLine(
                timestamp="10:00:05",
                text="Error 5: fifth failure",
                raw="ERROR: Error 5: fifth failure",
                level="ERROR",
                is_validation=True,
                is_traceback=False,
            ),
            LogLine(
                timestamp="10:00:06",
                text="Error 6: sixth failure",
                raw="ERROR: Error 6: sixth failure",
                level="ERROR",
                is_validation=True,
                is_traceback=False,
            ),
            LogLine(
                timestamp="10:00:07",
                text="ZeroDivisionError: division by zero",
                raw="ZeroDivisionError: division by zero",
                level="ERROR",
                is_validation=True,
                is_traceback=False,
            ),
        ]

        with patch(
            "shutil.get_terminal_size", return_value=os.terminal_size((100, 30))
        ):
            renderer.render(
                app_name="sample",
                status=READY,
                url="http://localhost:8000",
                ws_clients=0,
                log_lines=[],
                validation_count=7,
                current_error_block=entries,
                show_all=False,
            )

        captured = capsys.readouterr().out

        # Header note must be present
        assert "Errors" in captured
        assert "(7 errors)" in captured
        assert "switch (tab) to DETAILED or VERBOSE logs" in captured

        # Traceback lines must NOT appear at all
        assert "Traceback (most recent call last)" not in captured
        assert 'File "/app/test.py"' not in captured
        assert "1 / 0" not in captured

        # Only the last 5 errors must appear
        # Error 1 and Error 2 are older and should be dropped (7 - 5 = 2 dropped)
        assert "Error 1: initial failure" not in captured
        assert "Error 2: second failure" not in captured
        assert "Error 3: third failure" in captured
        assert "Error 4: fourth failure" in captured
        assert "Error 5: fifth failure" in captured
        assert "Error 6: sixth failure" in captured
        assert "ZeroDivisionError: division by zero" in captured

    def test_mouse_tracking_escapes(self, monkeypatch):
        written: list[str] = []
        monkeypatch.setattr(
            "cave_cli.utils.display.sys.stdout.write",
            lambda s: written.append(s),
        )
        dashboard = RunDashboard(app_name="app", url="http://localhost:8000")
        with patch("threading.Thread"):
            dashboard.start()
        assert any(MOUSE_ENTER in s for s in written)

        written.clear()
        dashboard.pause()
        assert any(MOUSE_EXIT in s for s in written)

        written.clear()
        dashboard.resume()
        assert any(MOUSE_ENTER in s for s in written)

        written.clear()
        dashboard.stop()
        assert any(MOUSE_EXIT in s for s in written)

    def test_log_filter_is_traceback(self):
        tb_lines = [
            "Traceback (most recent call last):",
            '  File "/app/views.py", line 45, in get',
            "    raise ValueError('bad')",
            "    ^^^^^^^^^^^^^^^^^^^^^^^",
            "Exception in ASGI application",
            "During handling of the above exception, another exception occurred:",
            "The above exception was the direct cause of the following exception:",
        ]
        for line in tb_lines:
            assert LogFilter.is_traceback(line) is True

        non_tb_lines = [
            "ZeroDivisionError: division by zero",
            "ValueError: bad",
            "django.core.exceptions.ValidationError: ['err']",
            "Database connection failed",
            "warning: ['panes']",
        ]
        for line in non_tb_lines:
            assert LogFilter.is_traceback(line) is False

    def test_render_logs_mode_footer_bottom_aligned(self, capsys):
        import os

        renderer = DashboardRenderer()
        logs = [
            LogLine(
                timestamp="10:00:00",
                text="App Loading",
                raw="INFO: App Loading",
                level="INFO",
            ),
            LogLine(
                timestamp="10:00:01",
                text="Server ready",
                raw="INFO: Server ready",
                level="INFO",
            ),
        ]
        with patch(
            "shutil.get_terminal_size", return_value=os.terminal_size((80, 24))
        ):
            renderer.render(
                app_name="sample",
                status=READY,
                url="http://localhost:8000",
                ws_clients=0,
                log_lines=logs,
                validation_count=0,
                current_error_block=[],
                mode=MODE_STANDARD,
            )

        captured = capsys.readouterr().out
        lines = captured.split("\n")
        # Line count should be exactly 23 (budget = rows - 1)
        assert len(lines) == 23
        # Footer should be on the last line (bottom-aligned)
        assert "Ctrl+C to stop" in lines[-1]
