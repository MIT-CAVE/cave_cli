import pytest
from cave_cli.utils.display import (
    DashboardRenderer,
    LogFilter,
    LogLine,
    RunDashboard,
    READY,
    LOADING,
    RELOADING,
    RED,
    YELLOW,
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
