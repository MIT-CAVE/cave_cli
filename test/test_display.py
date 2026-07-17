import pytest
from cave_cli.utils.display import LogFilter, READY, LOADING, RELOADING

class TestLogFilter:
    def test_strip_level_prefix(self):
        filter_obj = LogFilter()
        assert filter_obj.strip_level_prefix("INFO:     Started server process [134449]") == "Started server process [134449]"
        assert filter_obj.strip_level_prefix("INFO: INFO:     Started server process [134449]") == "Started server process [134449]"
        assert filter_obj.strip_level_prefix("WARNING: Connection lost") == "Connection lost"
        assert filter_obj.strip_level_prefix("connection open") == "connection open"

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
        assert filter_obj.classify_status("Application startup complete.") == READY
        assert filter_obj.classify_status("Started server process [134449]") == LOADING
        assert filter_obj.classify_status("detected changes in 'app.py', reloading") == RELOADING
        assert filter_obj.classify_status("Just some logging") is None

    def test_is_noise(self):
        filter_obj = LogFilter()
        assert filter_obj.is_noise("connection open") is True
        assert filter_obj.is_noise("connection closed") is True
        assert filter_obj.is_noise("SOCKET CONNECTION OPENED") is True
        assert filter_obj.is_noise("WebSocket CONNECT /ws/") is True
        assert filter_obj.is_noise("Started server process ") is True
        assert filter_obj.is_noise("Will watch for changes in these directories: ['/app']") is True
        assert filter_obj.is_noise("Started reloader process [48] using StatReload") is True
        assert filter_obj.is_noise("some actual log line") is False

