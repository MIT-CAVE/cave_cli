from unittest.mock import MagicMock, patch
import pytest
from cave_cli.utils.display import (
    ALT_SCREEN_ENTER,
    ALT_SCREEN_EXIT,
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

        # Standard -> Verbose displays header in alternate screen without exiting to primary
        dashboard.set_mode(MODE_VERBOSE)
        assert not any(ALT_SCREEN_EXIT in s for s in written)
        assert "Verbose Mode" in "".join(written)

        written.clear()
        # Verbose -> Standard stays in alternate screen
        dashboard.set_mode(MODE_STANDARD)
        assert dashboard.mode == MODE_STANDARD
        assert not any(ALT_SCREEN_ENTER in s for s in written)

        # Stop while in standard mode: exits alt screen without dumping verbose logs
        written.clear()
        dashboard.stop()
        assert any(ALT_SCREEN_EXIT in s for s in written)
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

    def test_verbose_mode_log_streaming(self, monkeypatch):
        written: list[str] = []
        monkeypatch.setattr(
            "cave_cli.utils.display.sys.stdout.write",
            lambda s: written.append(s),
        )
        monkeypatch.setattr(
            "cave_cli.utils.display.sys.stdout.flush", lambda: None
        )

        dashboard = RunDashboard(
            app_name="app",
            url="http://localhost:8000",
            initial_mode=MODE_VERBOSE,
        )
        written.clear()

        dashboard._process_line("INFO: Testing verbose line streaming")
        full_out = "".join(written)
        assert "INFO: Testing verbose line streaming" in full_out

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
        full_out = "".join(written)
        assert "[startup]" in full_out
        assert "docker run -d postgres:latest" in full_out
        assert "INFO: Django booted" in full_out

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
