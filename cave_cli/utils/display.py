import os
import queue
import re
import shutil
import sys
import threading
import time
from dataclasses import dataclass

try:
    import select
    import termios
    import tty

    IS_WINDOWS = False
except ImportError:
    import msvcrt

    IS_WINDOWS = True


# ── ANSI escape codes ──────────────────────────────────────────────────────

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

# Default (Dark) Colors
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
WHITE = "\033[37m"

THEMES = {
    "dark": {
        "RED": "\033[31m",
        "GREEN": "\033[32m",
        "YELLOW": "\033[33m",
        "BLUE": "\033[34m",
        "MAGENTA": "\033[35m",
        "CYAN": "\033[36m",
        "WHITE": "\033[37m",
    },
    "light": {
        "RED": "\033[91m",
        "GREEN": "\033[92m",
        "YELLOW": "\033[93m",
        "BLUE": "\033[94m",
        "MAGENTA": "\033[95m",
        "CYAN": "\033[96m",
        "WHITE": "\033[97m",
    },
    "solarized": {
        "RED": "\033[38;5;160m",
        "GREEN": "\033[38;5;64m",
        "YELLOW": "\033[38;5;136m",
        "BLUE": "\033[38;5;33m",
        "MAGENTA": "\033[38;5;125m",
        "CYAN": "\033[38;5;37m",
        "WHITE": "\033[38;5;231m",
    },
    "monokai": {
        "RED": "\033[38;5;197m",
        "GREEN": "\033[38;5;148m",
        "YELLOW": "\033[38;5;186m",
        "BLUE": "\033[38;5;81m",
        "MAGENTA": "\033[38;5;141m",
        "CYAN": "\033[38;5;81m",
        "WHITE": "\033[38;5;231m",
    },
}


def set_theme(theme_name: str) -> None:
    """
    Usage:

    - Updates the global color variables based on a theme name

    Requires:

    - ``theme_name``:
        - Type: str
        - What: Name of the theme to apply (e.g. "solarized")
    """
    global RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE
    theme = THEMES.get(theme_name.lower(), THEMES["dark"])
    RED = theme["RED"]
    GREEN = theme["GREEN"]
    YELLOW = theme["YELLOW"]
    BLUE = theme["BLUE"]
    MAGENTA = theme["MAGENTA"]
    CYAN = theme["CYAN"]
    WHITE = theme["WHITE"]


# Initial theme load
from cave_cli.utils.cache import get_setting

set_theme(get_setting("theme", "dark"))

CURSOR_HIDE = "\033[?25l"
CURSOR_SHOW = "\033[?25h"

_QUIET = False


def set_quiet(quiet: bool) -> None:
    """
    Usage:

    - Sets the global quiet mode state

    Requires:

    - ``quiet``:
        - Type: bool
        - What: If True, suppresses most CLI output
    """
    global _QUIET
    _QUIET = quiet


ALT_SCREEN_ENTER = "\033[?1049h"
ALT_SCREEN_EXIT = "\033[?1049l"
ALT_SCROLL_ENTER = "\033[?1007h"
ALT_SCROLL_EXIT = "\033[?1007l"
MOUSE_ENTER = "\033[?1000h\033[?1006h"
MOUSE_EXIT = "\033[?1006l\033[?1000l"
CURSOR_HOME = "\033[H"
CLEAR_BELOW = "\033[J"
CLEAR_EOL = "\033[K"

# ── Server status constants ────────────────────────────────────────────────

RELOADING = "reloading"
LOADING = "loading"
READY = "ready"
ERROR = "error"
STOPPING = "stopping"

# ── Display mode constants ─────────────────────────────────────────────────

MODE_LIFECYCLE = "lifecycle"
MODE_STANDARD = "standard"
MODE_ALL = "all"
MODE_VERBOSE = "verbose"


from cave_cli.utils.log_parser import LogParser

# ── Data structures ────────────────────────────────────────────────────────


@dataclass
class StackComponent:
    """
    Usage:

    - Represents an orchestrated component in the CAVE Docker stack.

    Requires:

    - ``name``:
        - Type: str
        - What: Name of component (e.g. "App Server", "Database").

    - ``image``:
        - Type: str
        - What: Docker image name.

    - ``container``:
        - Type: str
        - What: Docker container or network identifier.

    Optional:

    - ``status``:
        - Type: str
        - What: Current component status (e.g. "Pending", "Starting", "Ready").
        - Default: "Pending"
    """

    name: str
    image: str
    container: str
    status: str = "Pending"


@dataclass
class LifecycleEvent:
    """
    Usage:

    - Represents a single lifecycle milestone during startup or teardown.

    Requires:

    - ``timestamp``:
        - Type: str
        - What: HH:MM:SS timestamp.

    - ``text``:
        - Type: str
        - What: Description of the event.

    Optional:

    - ``status``:
        - Type: str
        - What: Status badge ("ok", "pending", "warn", "error", "info").
        - Default: "ok"
    """

    timestamp: str
    text: str
    status: str = "ok"


@dataclass
class LogLine:
    """
    Usage:

    - Represents a single processed log line from a container.

    Requires:

    - ``timestamp``:
        - Type: str
        - What: HH:MM:SS formatted timestamp when the line was received.

    - ``text``:
        - Type: str
        - What: The log message with the Django level prefix stripped.

    Optional:

    - ``raw``:
        - Type: str
        - What: The original unstripped log line.
        - Default: ""

    - ``is_validation``:
        - Type: bool
        - What: Whether this line belongs in the Validation Issues panel.
        - Default: False

    - ``level``:
        - Type: str
        - What: Normalized severity level (ERROR, WARN, INFO, DEBUG).
        - Default: "INFO"

    - ``message``:
        - Type: str
        - What: Clean message without outer level prefixes.
        - Default: ""

    - ``is_traceback``:
        - Type: bool
        - What: Whether this line is a traceback frame or header.
        - Default: False
    """

    timestamp: str
    text: str
    raw: str = ""
    is_validation: bool = False
    level: str = "INFO"
    message: str = ""
    is_traceback: bool = False


# ── Log filtering ──────────────────────────────────────────────────────────

_LEVEL_PREFIX_RE = re.compile(
    r"^(INFO|WARNING|WARN|ERROR|DEBUG|CRITICAL):[ \t]*"
)

# Uvicorn's own formatter prepends a level prefix to every message (e.g.
# "INFO:     Started server process [1]"), and the container's run script
# wraps that again with its own level prefix, producing nested prefixes such
# as "INFO: INFO:     ...". strip_level_prefix() below strips these
# iteratively so a fully-clean message is left either way.
_ACCESS_LOG_RE = re.compile(r'"[A-Z]+ \S* HTTP/\d\.\d"')

# Lines to silently drop in clean mode (very noisy, no user value).
# WebSocket CONNECT/DISCONNECT (old Channels runserver) and SOCKET CONNECTION
# OPENED/CLOSED (custom markers) are processed for client count but not displayed.
_SKIP_PATTERNS: tuple[str, ...] = (
    "WS RECEIVE",
    "HTTP ",
    # Django Startup Lines
    "WebSocket ",
    "Django version ",
    "Starting ASGI",
    "Starting development server",
    "Quit the server with CONTROL-C",
    "Watching for file changes",
    "Performing system checks",
    "System check identified no issues",
    "changed, reloading",
    # Uvicorn Startup Lines
    "Started server process ",
    "Waiting for application startup",
    "Waiting for application shutdown",
    "Application startup complete",
    "Application shutdown complete",
    "Uvicorn running on",
    "Shutting down",
    "Finished server process ",
    "detected changes in",
    "connection open",
    "connection closed",
    "Will watch for changes in these directories",
    "Started reloader process",
    "StatReload",
    "Reloading",
    "reloading",
    # Custom socket markers (processed for client count, not displayed)
    "SOCKET CONNECTION OPENED",
    "SOCKET CONNECTION CLOSED",
    # Current Date. EG:  April 28, 2026
    f"{time.strftime('%B %d, %Y')}",
)

# Lines that belong in the Validation Issues panel (matched against stripped text)
_VALIDATION_PATTERNS: tuple[str, ...] = (
    "Traceback (most recent call last)",
    "An error occurred",
    "Exception:",
    "error:",
    "warning:",
    "Unknown Fields:",
    "ValidationError",
    "validation failed",
    "Invalid ",
    "DeprecationWarning",
    "RuntimeWarning",
)

# Django (old) and Uvicorn (new) status transition triggers, checked against
# the fully level-prefix-stripped line. Uvicorn only prints its startup
# banner ("Uvicorn running on ...") once per process, not on every autoreload
# cycle, so "Application startup complete" -- which does reprint each
# reload -- is used as the READY trigger instead.
_LOADING_TRIGGERS = (
    "Starting ASGI",
    "Starting development server",
    "Started server process ",
    "Waiting for application startup",
)
_READY_TRIGGERS = (
    "Quit the server with CONTROL-C",
    "Application startup complete",
    "Ready",
    "App Ready",
)
_RELOAD_TRIGGERS = (
    "changed, reloading",
    "detected changes in",
    "Reloading",
    "reloading",
)

_WS_CONNECT = "WebSocket CONNECT "
_WS_DISCONNECT = "WebSocket DISCONNECT "
_SOCKET_OPENED = "SOCKET CONNECTION OPENED"
_SOCKET_CLOSED = "SOCKET CONNECTION CLOSED"


class LogFilter:
    """
    Usage:

    - Classifies and filters raw container log lines.

    Notes:

    - All methods are pure (no side effects) and operate on strings only.
    - Designed to be instantiated once and reused.
    """

    @staticmethod
    def strip_level_prefix(line: str) -> str:
        """
        Usage:

        - Strips the leading Django log-level prefix from a raw line.

        Requires:

        - ``line``:
            - Type: str
            - What: A raw container log line such as ``"INFO: message"``.

        Returns:

        - ``stripped``:
            - Type: str
            - What: The line with the level prefix removed.

        Notes:

        - Strips repeatedly so nested prefixes (e.g. a container run
          script's "INFO: " wrapped around uvicorn's own "INFO:     "
          formatter output) are fully removed, not just the outermost one.
        """
        stripped = line
        while True:
            new = _LEVEL_PREFIX_RE.sub("", stripped, count=1)
            if new == stripped:
                return new
            stripped = new

    @staticmethod
    def classify_status(stripped: str) -> str | None:
        """
        Usage:

        - Returns a new server status if this line triggers a transition.

        Requires:

        - ``stripped``:
            - Type: str
            - What: Log line with the level prefix already removed.

        Returns:

        - ``status``:
            - Type: str | None
            - What: One of the ServerStatus constants, or None if no transition.

        Notes:

        - READY is checked first so a reload cycle correctly resets the status.
        """
        if any(t in stripped for t in _READY_TRIGGERS):
            return READY
        if any(t in stripped for t in _RELOAD_TRIGGERS):
            return RELOADING
        if any(t in stripped for t in _LOADING_TRIGGERS):
            return LOADING
        return None

    @staticmethod
    def ws_event(stripped: str) -> str | None:
        """
        Usage:

        - Returns the WebSocket event type for client count tracking.

        Requires:

        - ``stripped``:
            - Type: str
            - What: Log line with the level prefix already removed.

        Returns:

        - ``event``:
            - Type: str | None
            - What: ``"connect"`` or ``"disconnect"``, or None if not a WS event.

        Notes:

        - Recognizes both the old Django Channels runserver format
          ("WebSocket CONNECT "/"WebSocket DISCONNECT ") and the custom
          uvicorn app markers ("SOCKET CONNECTION OPENED"/"CLOSED").
        """
        if _WS_CONNECT in stripped or _SOCKET_OPENED in stripped:
            return "connect"
        if _WS_DISCONNECT in stripped or _SOCKET_CLOSED in stripped:
            return "disconnect"
        return None

    @staticmethod
    def is_noise(stripped: str) -> bool:
        """
        Usage:

        - Returns True if the line should be silently dropped in clean mode.

        Requires:

        - ``stripped``:
            - Type: str
            - What: Log line with the level prefix already removed.
        """
        if not stripped.strip():
            return True
        if _ACCESS_LOG_RE.search(stripped):
            return True
        return any(p in stripped for p in _SKIP_PATTERNS)

    @staticmethod
    def is_validation_issue(raw: str, stripped: str) -> bool:
        """
        Usage:

        - Returns True if the line belongs in the Validation Issues panel.

        Requires:

        - ``raw``:
            - Type: str
            - What: The original unstripped container log line.

        - ``stripped``:
            - Type: str
            - What: The same line with the level prefix removed.

        Notes:

        - Raw-line starts with WARNING:/ERROR: are always validation.
        - Indented lines are treated as traceback continuation frames.
        - Uvicorn's autoreload notice ("WatchFiles detected changes in
          ...") is logged at WARNING level but is a benign status message,
          not an error, so reload triggers are excluded first.
        """
        if any(t in stripped for t in _RELOAD_TRIGGERS):
            return False
        raw_upper = raw.upper()
        if raw_upper.startswith("WARNING:") or raw_upper.startswith("ERROR:"):
            return True
        if stripped and stripped[0] in (" ", "\t"):
            return True
        return any(p in stripped for p in _VALIDATION_PATTERNS)

    @staticmethod
    def is_traceback(stripped: str) -> bool:
        """
        Usage:

        - Returns True if the line is part of a Python traceback.

        Requires:

        - ``stripped``:
            - Type: str
            - What: Log line with level prefix stripped.

        Returns:

        - ``is_tb``:
            - Type: bool
            - What: True if line is a traceback frame, header, or marker.
        """
        s = stripped.strip()
        if not s:
            return False
        if "Traceback (most recent call last)" in s:
            return True
        if s.startswith('File "') or s.startswith("File '"):
            return True
        if s.startswith("During handling of the above exception"):
            return True
        if s.startswith("The above exception was the direct cause"):
            return True
        if s == "Exception in ASGI application":
            return True
        if all(c in "^~ " for c in s):
            return True
        if stripped.startswith(" ") or stripped.startswith("\t"):
            return True
        return False


# ── Dashboard renderer ─────────────────────────────────────────────────────


class DashboardRenderer:
    """
    Usage:

    - Pure rendering layer: takes state as arguments and writes ANSI output
      to the alternate screen buffer.

    Notes:

    - Each render moves to the top-left of the alternate screen and rewrites
      the full frame in one pass without a trailing newline, preventing the
      terminal from scrolling the top line out of view.
    - All output goes to stdout.
    """

    # Fixed line counts for layout budget calculation
    _HEADER_LINES = 4  # ━ + title + ━ + blank
    _LOG_FIXED = 3  # "Recent Activity" + top-rule + bottom-rule
    _FOOTER_LINES = 2  # blank + hint line
    _FIXED_BASE = _HEADER_LINES + _LOG_FIXED + _FOOTER_LINES  # = 9
    _VAL_FIXED = 4  # blank + label + top-rule + bottom-rule
    _MAX_ERROR_LINES = 5  # maximum validation/error lines shown in LOGS mode
    _MIN_LOG_LINES = 3  # guaranteed minimum log lines even with validation

    @staticmethod
    def _is_traceback_line(text: str) -> bool:
        return LogFilter.is_traceback(text)

    @staticmethod
    def _status_str(status: str) -> str:
        indicators: dict[str, str] = {
            RELOADING: f"{YELLOW}● Reloading{RESET}",
            LOADING: f"{YELLOW}● Loading{RESET}",
            READY: f"{GREEN}● Ready{RESET}",
            ERROR: f"{RED}● Error{RESET}",
            STOPPING: f"{DIM}● Stopping{RESET}",
        }
        return indicators.get(status, f"{DIM}● Unknown{RESET}")

    @staticmethod
    def _truncate(text: str, width: int) -> str:
        if len(text) <= width:
            return text
        return text[: width - 1] + "…"

    def render(
        self,
        app_name: str,
        status: str,
        url: str,
        ws_clients: int,
        log_lines: list[LogLine],
        validation_count: int,
        current_error_block: list[LogLine],
        show_all: bool = False,
        scroll_offset: int = 0,
        mode: str = MODE_STANDARD,
        components: list[StackComponent] | None = None,
        lifecycle_events: list[LifecycleEvent] | None = None,
        startup_logs: list[str] | None = None,
        prompt_message: str | None = None,
        prompt_options: str = "[y/N]",
        prompt_buffer: str = "",
    ) -> None:
        """
        Usage:

        - Writes an updated dashboard frame to the alternate screen buffer.

        Requires:

        - ``app_name``:
            - Type: str
            - What: The CAVE app name shown in the header bar.

        - ``status``:
            - Type: str
            - What: Current server status constant.

        - ``url``:
            - Type: str
            - What: App access URL shown in the header bar.

        - ``ws_clients``:
            - Type: int
            - What: Number of connected WebSocket clients.

        - ``log_lines``:
            - Type: list[LogLine]
            - What: All accumulated main log entries (most recent subset shown).

        - ``validation_count``:
            - Type: int
            - What: Total number of validation issues seen (for the panel label).

        - ``current_error_block``:
            - Type: list[LogLine]
            - What: Lines of the most recent error event (shown in panel body).

        Optional:

        - ``show_all``:
            - Type: bool
            - What: If True, renders all logs without filtering or panels.
            - Default: False

        - ``scroll_offset``:
            - Type: int
            - What: Number of lines to scroll up from the bottom in show_all mode.
            - Default: 0

        - ``mode``:
            - Type: str
            - What: Display mode (MODE_STANDARD, MODE_ALL, MODE_VERBOSE, or MODE_LIFECYCLE).
            - Default: MODE_STANDARD

        - ``components``:
            - Type: list[StackComponent] | None
            - What: Stack components shown in Lifecycle view.
            - Default: None

        - ``lifecycle_events``:
            - Type: list[LifecycleEvent] | None
            - What: Lifecycle events shown in Lifecycle view.
            - Default: None

        - ``startup_logs``:
            - Type: list[str] | None
            - What: Startup orchestration and command log lines shown in Verbose view.
            - Default: None

        - ``prompt_message``:
            - Type: str | None
            - What: Message to display in the prompt area above the footer.
            - Default: None

        - ``prompt_options``:
            - Type: str
            - What: Bracketed prompt options text.
            - Default: "[y/N]"

        - ``prompt_buffer``:
            - Type: str
            - What: User-typed text currently entered into the prompt.
            - Default: ""
        """
        cols, rows = shutil.get_terminal_size(fallback=(80, 24))
        bar_width = max(10, cols - 4)

        # Budget: rows - 1 ensures no trailing-newline scroll on a full screen.
        budget = rows - 1
        prompt_lines = 3 if prompt_message else 0

        lines: list[str] = []

        # ── Header ────────────────────────────────────────────────────────
        lines.append(f"  {BOLD}{'━' * bar_width}{RESET}")
        ws_str = (
            f"  │  {DIM}{ws_clients} client{'s' if ws_clients != 1 else ''}{RESET}"
            if ws_clients > 0
            else ""
        )
        if mode == MODE_LIFECYCLE:
            mode_str = f"  │  {CYAN}{BOLD}LIFECYCLE{RESET}"
        elif mode == MODE_STANDARD:
            mode_str = f"  │  {CYAN}{BOLD}LOGS{RESET}"
        elif mode == MODE_ALL or show_all:
            mode_str = f"  │  {CYAN}{BOLD}DETAILED{RESET}"
        elif mode == MODE_VERBOSE:
            mode_str = f"  │  {CYAN}{BOLD}VERBOSE{RESET}"
        else:
            mode_str = ""
        title = (
            f"  {BOLD}{CYAN}CAVE{RESET}"
            f"  │  {BOLD}{app_name}{RESET}"
            f"  │  {self._status_str(status)}"
            f"{ws_str}"
            f"{mode_str}"
            f"  │  {DIM}{url}{RESET}"
        )
        lines.append(title)
        lines.append(f"  {BOLD}{'━' * bar_width}{RESET}")
        lines.append("")

        if mode == MODE_LIFECYCLE:
            # ── Stack Components Section ─────────────────────────────────────
            lines.append(f"  {BOLD}Stack Components{RESET}")
            lines.append(f"  {'─' * bar_width}")
            comp_list = components or []
            if not comp_list:
                lines.append(f"  {DIM}No components registered{RESET}")
            else:
                for c in comp_list:
                    c_status_lower = c.status.lower()
                    if c_status_lower in (
                        "ready",
                        "running",
                        "active",
                        "done",
                        "built",
                    ):
                        c_color = GREEN
                        dot = f"{GREEN}●{RESET}"
                    elif c_status_lower in (
                        "starting",
                        "building",
                        "checking",
                        "pending",
                        "creating",
                        "loading",
                        "loading app",
                    ):
                        c_color = YELLOW
                        dot = f"{YELLOW}●{RESET}"
                    elif c_status_lower in (
                        "stopping",
                        "stopped",
                        "removed",
                        "inactive",
                    ):
                        c_color = DIM
                        dot = f"{DIM}●{RESET}"
                    else:
                        c_color = RED
                        dot = f"{RED}●{RESET}"

                    name_str = c.name.ljust(14)
                    image_str = self._truncate(c.image, 24).ljust(25)
                    container_str = self._truncate(c.container, 22).ljust(23)
                    status_badge = f"{c_color}[{c.status}]{RESET}"
                    lines.append(
                        f"  {dot} {BOLD}{name_str}{RESET} "
                        f"{DIM}{image_str}{RESET} {container_str} {status_badge}"
                    )
            lines.append(f"  {'─' * bar_width}")
            lines.append("")

            # ── Lifecycle Timeline Section ──────────────────────────────────
            lines.append(f"  {BOLD}Lifecycle Timeline{RESET}")
            lines.append(f"  {'─' * bar_width}")

            comp_lines = 4 + max(1, len(comp_list))
            timeline_fixed = 3
            timeline_budget = max(
                1,
                budget
                - self._HEADER_LINES
                - self._FOOTER_LINES
                - comp_lines
                - timeline_fixed
                - prompt_lines,
            )

            ev_list = lifecycle_events or []
            visible_evs = ev_list[-timeline_budget:]
            if not visible_evs:
                lines.append(f"  {DIM}Waiting for lifecycle events...{RESET}")
            else:
                for ev in visible_evs:
                    ts = f"{DIM}{ev.timestamp}{RESET}"
                    if ev.status == "ok":
                        icon = f"{GREEN}✓{RESET}"
                    elif ev.status == "pending":
                        icon = f"{YELLOW}●{RESET}"
                    elif ev.status == "error":
                        icon = f"{RED}✗{RESET}"
                    elif ev.status == "warn":
                        icon = f"{YELLOW}!{RESET}"
                    else:
                        icon = f"{CYAN}i{RESET}"
                    msg = self._truncate(ev.text, cols - 16)
                    lines.append(f"  {ts}  {icon}  {msg}")
            lines.append(f"  {'─' * bar_width}")

            rendered_tl = max(1, len(visible_evs))
            for _ in range(timeline_budget - rendered_tl):
                lines.append("")

        elif mode == MODE_VERBOSE:
            # ── Verbose Mode ───────────────────────────────────────────────
            max_log_lines = max(
                0,
                budget - self._HEADER_LINES - self._FOOTER_LINES - prompt_lines,
            )
            all_verbose: list[tuple[str, str]] = []
            if startup_logs:
                for s_line in startup_logs:
                    all_verbose.append((f"{DIM}[startup]{RESET}", s_line))
            for entry in log_lines:
                ts = f"{DIM}{entry.timestamp}{RESET}"
                all_verbose.append((ts, entry.raw))

            max_scroll = max(0, len(all_verbose) - max_log_lines)
            effective_scroll = min(scroll_offset, max_scroll)

            end_idx = len(all_verbose) - effective_scroll
            start_idx = max(0, end_idx - max_log_lines)
            visible_logs = all_verbose[start_idx:end_idx]

            for ts_prefix, raw_text in visible_logs:
                text = self._truncate(raw_text.expandtabs(), cols - 14)
                lines.append(f"  {ts_prefix}  {text}")

            for _ in range(max_log_lines - len(visible_logs)):
                lines.append("")

        elif show_all or mode == MODE_ALL:
            # ── All Logs Mode ──────────────────────────────────────────────
            max_log_lines = max(
                0,
                budget - self._HEADER_LINES - self._FOOTER_LINES - prompt_lines,
            )

            # Clamp scroll_offset so we don't scroll past the first line
            # (i.e., ensure we always show a full screen of logs if available)
            max_scroll = max(0, len(log_lines) - max_log_lines)
            effective_scroll = min(scroll_offset, max_scroll)

            end_idx = len(log_lines) - effective_scroll
            start_idx = max(0, end_idx - max_log_lines)
            visible_logs = log_lines[start_idx:end_idx]

            for entry in visible_logs:
                ts = f"{DIM}{entry.timestamp}{RESET}"
                level = entry.level or "INFO"
                level_prefix = f"{level}:"
                display_msg = (
                    entry.message if entry.message else entry.text
                ).expandtabs()
                display_text = f"{level_prefix} {display_msg}"

                text = self._truncate(display_text, cols - 14)
                if level == "ERROR":
                    color = RED
                elif level == "WARN":
                    color = YELLOW
                elif level == "DEBUG":
                    color = DIM
                else:
                    color = ""
                lines.append(f"  {ts}  {color}{text}{RESET}")

            # Fill remaining space to keep footer at bottom
            for _ in range(max_log_lines - len(visible_logs)):
                lines.append("")
        else:
            # ── Minimal Mode (Default) ─────────────────────────────────────
            # Filter out traceback lines from current_error_block so only actual errors are shown
            non_traceback_errors = [
                e
                for e in current_error_block
                if not getattr(e, "is_traceback", False)
                and not self._is_traceback_line(e.text)
            ]
            has_validation = bool(non_traceback_errors) or validation_count > 0

            # Determine how many error lines to show, shrinking if the terminal
            # is too short to guarantee _MIN_LOG_LINES of activity log.
            desired_v = min(len(non_traceback_errors), self._MAX_ERROR_LINES)
            if has_validation:
                available_log = (
                    budget
                    - self._FIXED_BASE
                    - self._VAL_FIXED
                    - desired_v
                    - prompt_lines
                )
                if available_log < self._MIN_LOG_LINES:
                    desired_v = max(
                        0,
                        budget
                        - self._FIXED_BASE
                        - self._VAL_FIXED
                        - self._MIN_LOG_LINES
                        - prompt_lines,
                    )
                    if desired_v == 0:
                        has_validation = False
            shown_errors = (
                non_traceback_errors[-desired_v:] if desired_v > 0 else []
            )

            val_section_height = (
                self._VAL_FIXED + len(shown_errors) if has_validation else 0
            )
            max_log_lines = max(
                0,
                budget - self._FIXED_BASE - val_section_height - prompt_lines,
            )
            visible_logs = log_lines[-max_log_lines:]

            # ── Recent Activity ────────────────────────────────────────────────
            lines.append(f"  {BOLD}Recent Activity{RESET}")
            lines.append(f"  {'─' * bar_width}")
            for entry in visible_logs:
                ts = f"{DIM}{entry.timestamp}{RESET}"
                text = self._truncate(entry.text, cols - 14)
                color = YELLOW if entry.level == "WARN" else ""
                lines.append(f"  {ts}  {color}{text}{RESET}")
            lines.append(f"  {'─' * bar_width}")

            # ── Errors / Warnings ─────────────────────────────────────────────
            if has_validation:
                lines.append("")
                has_errors = any(
                    e.level == "ERROR"
                    for e in (shown_errors or current_error_block)
                ) or not (shown_errors or current_error_block)
                if has_errors:
                    label = "error" if validation_count == 1 else "errors"
                    title_color = RED
                    title_text = "Errors"
                    hint_text = "(switch (tab) to DETAILED or VERBOSE logs to see tracebacks)"
                else:
                    label = "warning" if validation_count == 1 else "warnings"
                    title_color = YELLOW
                    title_text = "Validation Warnings"
                    hint_text = "(switch (tab) to DETAILED or VERBOSE logs to see details)"

                count_str = f"{validation_count} {label}"
                header_prefix = f"  {title_text}  ({count_str})"
                if len(header_prefix) + len(hint_text) + 2 <= cols:
                    hint = f"  {DIM}{hint_text}{RESET}"
                elif (
                    len(header_prefix) + len("(see DETAILED logs)") + 2 <= cols
                ):
                    hint = f"  {DIM}(see DETAILED logs){RESET}"
                else:
                    hint = ""

                lines.append(
                    f"  {BOLD}{title_text}{RESET}  {title_color}({count_str}){RESET}{hint}"
                )
                lines.append(f"  {'─' * bar_width}")
                for entry in shown_errors:
                    ts = f"{DIM}{entry.timestamp}{RESET}"
                    text = self._truncate(entry.text, cols - 14)
                    color = YELLOW if entry.level == "WARN" else RED
                    lines.append(f"  {ts}  {color}{text}{RESET}")
                lines.append(f"  {'─' * bar_width}")

        # ── Prompt Overlay ─────────────────────────────────────────────────
        if prompt_message:
            lines.append("")
            lines.append(f"  {YELLOW}⚠{RESET}  {BOLD}{prompt_message}{RESET}")
            lines.append(
                f"  {BOLD}Continue? {prompt_options} {CYAN}{prompt_buffer}{RESET}█"
            )

        # ── Footer ─────────────────────────────────────────────────────────
        while len(lines) < budget - 2:
            lines.append("")

        lines.append("")
        if show_all or mode in (MODE_ALL, MODE_VERBOSE):
            lines.append(
                f"  {DIM}Ctrl+C to stop  │  Esc to detach  │  Tab / Shift+Tab to cycle  │  ↑/↓ to scroll{RESET}"
            )
        else:
            lines.append(
                f"  {DIM}Ctrl+C to stop  │  Esc to detach  │  Tab / Shift+Tab to cycle{RESET}"
            )

        # Write the full frame atomically: move to top-left, write each line
        # with CLEAR_EOL to erase leftover characters.
        buf = CURSOR_HOME + CURSOR_HIDE
        for i, line in enumerate(lines):
            buf += CLEAR_EOL + line
            if i < len(lines) - 1:
                buf += "\n"
        buf += CLEAR_BELOW
        sys.stdout.write(buf)
        sys.stdout.flush()


# ── Live dashboard controller ──────────────────────────────────────────────


class RunDashboard:
    """
    Usage:

    - Stateful controller for the cave run TUI: owns the log buffer,
      display loop thread, and queue that receives streamed container lines.

    Requires:

    - ``app_name``:
        - Type: str
        - What: CAVE app name shown in the header.

    - ``url``:
        - Type: str
        - What: App access URL shown in the header.

    Optional:

    - ``stop_event``:
        - Type: threading.Event | None
        - What: Event to signal shutdown.
        - Default: None

    - ``max_logs``:
        - Type: int
        - What: Maximum number of log lines to keep in memory buffers.
        - Default: 10000

    - ``initial_mode``:
        - Type: str
        - What: Initial display mode (MODE_STANDARD, MODE_ALL, or MODE_VERBOSE).
        - Default: MODE_STANDARD

    Notes:

    - Call ``start()`` after setting up signal handlers and starting the
      container. Call ``stop()`` in a finally block to restore the terminal.
    """

    REFRESH_INTERVAL: float = 0.2
    is_detached: bool = False
    MODES: tuple[str, ...] = (
        MODE_LIFECYCLE,
        MODE_STANDARD,
        MODE_ALL,
        MODE_VERBOSE,
    )

    def __init__(
        self,
        app_name: str,
        url: str,
        stop_event: threading.Event | None = None,
        max_logs: int = 10000,
        initial_mode: str = MODE_STANDARD,
    ) -> None:
        self._app_name = app_name
        self._url = url
        self._max_logs = max_logs
        self._status: str = LOADING
        self._ws_clients: int = 0
        self._mode: str = initial_mode

        # Initial log entry
        ts = time.strftime("%H:%M:%S")
        initial_entry = LogLine(
            timestamp=ts,
            text="App Loading",
            raw="INFO: App Loading",
            level="INFO",
            message="App Loading",
        )
        self._log_lines: list[LogLine] = [initial_entry]
        self._all_log_lines: list[LogLine] = [initial_entry]

        self._components: list[StackComponent] = []
        self._lifecycle_events: list[LifecycleEvent] = []
        self._startup_logs: list[str] = []
        self._last_verbose_index: int = 0
        self._initial_auto_advanced: bool = False
        self._app_loading: bool = False
        self._verbose_header_printed: bool = False
        self._paused: bool = False
        self._old_settings: object | None = None

        self._scroll_offset: int = 0
        self._validation_count: int = 0
        self._current_error_block: list[LogLine] = []
        self._last_was_validation: bool = False
        self._log_queue: queue.Queue[str | None] = queue.Queue()
        self._renderer = DashboardRenderer()
        self._filter = LogFilter()
        self._parser: LogParser = LogParser()
        self._stop_event = stop_event or threading.Event()
        self._terminate_event = threading.Event()
        self._display_thread: threading.Thread | None = None
        self.is_detached: bool = False
        self.container_exited: bool = False

        self._prompt_active: bool = False
        self._prompt_message: str = ""
        self._prompt_options: str = "[y/N]"
        self._prompt_buffer: str = ""
        self._prompt_result: str = ""
        self._prompt_event: threading.Event = threading.Event()
        self._render_event: threading.Event = threading.Event()

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def startup_logs(self) -> list[str]:
        return list(self._startup_logs)

    @property
    def is_active_tui(self) -> bool:
        return (
            self._display_thread is not None
            and self._display_thread.is_alive()
            and not self._paused
            and not self._terminate_event.is_set()
        )

    def set_components(self, components: list[StackComponent]) -> None:
        """
        Usage:

        - Sets the list of stack components displayed on the Lifecycle page.

        Requires:

        - ``components``:
            - Type: list[StackComponent]
            - What: Stack components to track.
        """
        self._components = list(components)

    def update_component(self, name: str, status: str) -> None:
        """
        Usage:

        - Updates the status of a specific component by name.

        Requires:

        - ``name``:
            - Type: str
            - What: Component name (e.g. "Database", "App Server").

        - ``status``:
            - Type: str
            - What: New status badge (e.g. "Starting", "Ready", "Stopped").
        """
        for comp in self._components:
            if comp.name.lower() == name.lower():
                comp.status = status
                return
        # If not present, create it dynamically
        self._components.append(
            StackComponent(name=name, image="", container="", status=status)
        )

    def add_lifecycle_event(self, text: str, status: str = "ok") -> None:
        """
        Usage:

        - Records a new lifecycle milestone event with a timestamp.

        Requires:

        - ``text``:
            - Type: str
            - What: Event description text.

        Optional:

        - ``status``:
            - Type: str
            - What: Status badge: "ok", "pending", "warn", "error", or "info".
            - Default: "ok"
        """
        ts = time.strftime("%H:%M:%S")
        self._lifecycle_events.append(
            LifecycleEvent(timestamp=ts, text=text, status=status)
        )
        if len(self._lifecycle_events) > 500:
            self._lifecycle_events.pop(0)

    def add_startup_log(self, line: str) -> None:
        """
        Usage:

        - Records raw orchestration command or debug output line.

        Requires:

        - ``line``:
            - Type: str
            - What: Log line to buffer.
        """
        self._startup_logs.append(line)
        if len(self._startup_logs) > 2000:
            self._startup_logs.pop(0)

    def infer_component_from_step(
        self, label: str, default_status: str
    ) -> None:
        """
        Usage:

        - Updates component status based on step label keywords.

        Requires:

        - ``label``:
            - Type: str
            - What: Step label (e.g. "Starting database").

        - ``default_status``:
            - Type: str
            - What: Status to apply ("Starting", "Ready", "Error").
        """
        l_lower = label.lower()
        if l_lower.startswith("running"):
            self.update_component(
                "App Server",
                "Running" if default_status != "Ready" else "Done",
            )
        elif "starting database" in l_lower:
            self.update_component("Database", default_status)
        elif "checking database" in l_lower:
            self.update_component(
                "Database",
                "Checking" if default_status == "Starting" else "Ready",
            )
        elif "initializing database" in l_lower:
            self.update_component(
                "Database",
                "Initializing" if default_status == "Starting" else "Ready",
            )
        elif "database" in l_lower:
            self.update_component("Database", default_status)
        elif "cache" in l_lower or "redis" in l_lower:
            self.update_component("Cache", default_status)
        elif "loading app" in l_lower:
            if default_status == "Starting":
                self._app_loading = True
                self.update_component("App Server", "Loading App")
            else:
                self._app_loading = False
                self.update_component("App Server", "Ready")
        elif "starting django" in l_lower:
            self.update_component(
                "App Server",
                "Starting" if default_status == "Starting" else "Running",
            )
        elif "django" in l_lower or "app" in l_lower:
            self.update_component("App Server", default_status)
        elif "network" in l_lower:
            self.update_component("Network", default_status)
        elif "proxy" in l_lower or "nginx" in l_lower:
            self.update_component("Proxy", default_status)

    @property
    def _show_all(self) -> bool:
        return self._mode == MODE_ALL

    @_show_all.setter
    def _show_all(self, val: bool) -> None:
        self._mode = MODE_ALL if val else MODE_STANDARD

    def cycle_mode(self, forward: bool = True) -> None:
        """
        Usage:

        - Cycles through display modes in forward or reverse order.

        Optional:

        - ``forward``:
            - Type: bool
            - What: True to cycle forward, False for reverse (Shift+Tab).
            - Default: True
        """
        try:
            curr_idx = self.MODES.index(self._mode)
        except ValueError:
            curr_idx = 0
        step = 1 if forward else -1
        next_mode = self.MODES[(curr_idx + step) % len(self.MODES)]
        self.set_mode(next_mode)

    def set_mode(self, mode: str) -> None:
        """
        Usage:

        - Switches display mode between Lifecycle, Standard, All, and Verbose.

        Requires:

        - ``mode``:
            - Type: str
            - What: One of MODE_LIFECYCLE, MODE_STANDARD, MODE_ALL, MODE_VERBOSE.
        """
        if mode == self._mode:
            return

        self._mode = mode
        self._scroll_offset = 0

    def _flush_verbose_backlog(self, from_start: bool = False) -> None:
        """
        Usage:

        - Flushes unprinted startup and container log lines to stdout in Verbose mode.

        Optional:

        - ``from_start``:
            - Type: bool
            - What: If True, prints all buffered logs from the beginning.
            - Default: False
        """
        start_idx = 0 if from_start else self._last_verbose_index
        if start_idx == 0 and self._startup_logs:
            for s_line in self._startup_logs:
                sys.stdout.write(f"  {DIM}[startup]{RESET}  {s_line}\n")
        unprinted = self._all_log_lines[start_idx:]
        for entry in unprinted:
            ts = f"{DIM}{entry.timestamp}{RESET}"
            sys.stdout.write(f"  {ts}  {entry.raw}\n")
        self._last_verbose_index = len(self._all_log_lines)
        sys.stdout.flush()

    def pause(self) -> None:
        """
        Usage:

        - Temporarily leaves the TUI alternate screen so interactive prompts can run.
        """
        self._paused = True
        if self._mode in (
            MODE_LIFECYCLE,
            MODE_STANDARD,
            MODE_ALL,
            MODE_VERBOSE,
        ):
            sys.stdout.write(
                CURSOR_SHOW + MOUSE_EXIT + ALT_SCROLL_EXIT + ALT_SCREEN_EXIT
            )
            sys.stdout.flush()
        if self._old_settings is not None and not IS_WINDOWS:
            try:
                import termios

                termios.tcsetattr(
                    sys.stdin.fileno(), termios.TCSANOW, self._old_settings
                )
            except Exception:
                pass

    def resume(self) -> None:
        """
        Usage:

        - Resumes the TUI alternate screen after an interactive prompt.
        """
        self._paused = False
        if not IS_WINDOWS:
            try:
                import tty

                tty.setcbreak(sys.stdin.fileno())
            except Exception:
                pass
        if self._mode in (
            MODE_LIFECYCLE,
            MODE_STANDARD,
            MODE_ALL,
            MODE_VERBOSE,
        ):
            sys.stdout.write(
                ALT_SCREEN_ENTER + ALT_SCROLL_ENTER + MOUSE_ENTER + CURSOR_HIDE
            )
            sys.stdout.flush()

    def prompt(self, message: str, options: str = "[y/N]") -> str:
        """
        Usage:

        - Displays a prompt message in the active TUI and waits for user input.

        Requires:

        - ``message``:
            - Type: str
            - What: The prompt message to display.

        Optional:

        - ``options``:
            - Type: str
            - What: Bracketed prompt options text.
            - Default: '[y/N]'

        Returns:

        - ``response``:
            - Type: str
            - What: The user's input string.
        """
        self._prompt_message = message
        self._prompt_options = options
        self._prompt_buffer = ""
        self._prompt_result = ""
        self._prompt_event.clear()
        self._prompt_active = True
        self._render_event.set()

        self._prompt_event.wait()
        self._prompt_active = False
        self._render_event.set()
        return self._prompt_result

    def confirm(
        self,
        message: str,
        auto_yes: bool = False,
        continue_on_no: bool = False,
    ) -> bool:
        """
        Usage:

        - Displays a confirmation prompt inside the TUI and returns True/False.

        Requires:

        - ``message``:
            - Type: str
            - What: The action description to display.

        Optional:

        - ``auto_yes``:
            - Type: bool
            - What: If True, bypasses the prompt and returns True.
            - Default: False

        - ``continue_on_no``:
            - Type: bool
            - What: If True, a 'no' returns False; otherwise exits.
            - Default: False

        Returns:

        - ``confirmed``:
            - Type: bool
            - What: True if confirmed, False if declined and continue_on_no is True.
        """
        if auto_yes:
            return True

        bracket = "[y/n]" if continue_on_no else "[y/N]"
        raw_response = self.prompt(message, options=bracket)
        normalized = raw_response.strip().lower()

        if normalized in ("y", "yes"):
            return True
        if continue_on_no:
            if normalized in ("n", "no"):
                return False
            self.stop()
            from cave_cli.utils.logger import logger

            logger.error("Operation canceled.")
            sys.exit(1)
        else:
            self.stop()
            from cave_cli.utils.logger import logger

            logger.error("Operation canceled.")
            sys.exit(1)

    def detach(self) -> None:
        """
        Usage:

        - Signals the dashboard to detach from the running app, leaving
          containers alive.
        """
        self.is_detached = True
        self._stop_event.set()

    def get_queue(self) -> "queue.Queue[str | None]":
        """
        Usage:

        - Returns the queue that the log-streaming thread should push into.
        """
        return self._log_queue

    def set_status(self, status: str) -> None:
        """
        Usage:

        - Updates the server status displayed in the header bar.

        Requires:

        - ``status``:
            - Type: str
            - What: One of the module-level status constants.
        """
        self._status = status

    def toggle_show_all(self) -> None:
        """
        Usage:

        - Cycles through display modes.
        """
        self.cycle_mode()

    def scroll_up(self, amount: int = 1) -> None:
        """
        Usage:

        - Scrolls up in show_all or verbose mode.

        Optional:

        - ``amount``:
            - Type: int
            - What: Number of lines to scroll up.
            - Default: 1
        """
        if self._mode in (MODE_ALL, MODE_VERBOSE):
            total_lines = len(self._all_log_lines) + (
                len(self._startup_logs) if self._mode == MODE_VERBOSE else 0
            )
            self._scroll_offset = min(total_lines, self._scroll_offset + amount)
            self._render_event.set()

    def scroll_down(self, amount: int = 1) -> None:
        """
        Usage:

        - Scrolls down in show_all or verbose mode.

        Optional:

        - ``amount``:
            - Type: int
            - What: Number of lines to scroll down.
            - Default: 1
        """
        if self._mode in (MODE_ALL, MODE_VERBOSE):
            self._scroll_offset = max(0, self._scroll_offset - amount)
            self._render_event.set()

    def _process_line(self, raw: str) -> None:
        parsed = self._parser.parse_line(raw)
        stripped = self._filter.strip_level_prefix(raw).expandtabs()
        ts = time.strftime("%H:%M:%S")

        def add_minimal(entry: LogLine) -> None:
            self._log_lines.append(entry)
            if len(self._log_lines) > self._max_logs:
                self._log_lines.pop(0)

        def add_all(entry: LogLine) -> None:
            self._all_log_lines.append(entry)
            if len(self._all_log_lines) > self._max_logs:
                self._all_log_lines.pop(0)
                # If we pruned a line while scrolled up, we must decrement offset
                # to keep the view static relative to the content.
                if self._scroll_offset > 0:
                    self._scroll_offset = max(0, self._scroll_offset - 1)

        # Status transitions (always checked)
        new_status = self._filter.classify_status(stripped)
        if new_status:
            # During reload, do not transition status back to LOADING when the new worker process starts
            if self._status == RELOADING and new_status == LOADING:
                pass
            else:
                self._status = new_status
                if new_status == RELOADING:
                    self._ws_clients = 0
                    reloading_entry = LogLine(
                        timestamp=ts,
                        text="App Reloading",
                        raw="INFO: App Reloading",
                        level="INFO",
                        message="App Reloading",
                    )
                    add_minimal(reloading_entry)
                    add_all(reloading_entry)
                    if (
                        self._mode in (MODE_ALL, MODE_VERBOSE)
                        and self._scroll_offset > 0
                    ):
                        self._scroll_offset += 1
                elif new_status == READY:
                    ready_entry = LogLine(
                        timestamp=ts,
                        text="App Ready",
                        raw="INFO: App Ready",
                        level="INFO",
                        message="App Ready",
                    )
                    add_minimal(ready_entry)
                    add_all(ready_entry)
                    if (
                        self._mode in (MODE_ALL, MODE_VERBOSE)
                        and self._scroll_offset > 0
                    ):
                        self._scroll_offset += 1
                    if self._app_loading:
                        self._app_loading = False
                        self.add_lifecycle_event("Loading App", status="ok")
                        if not self.is_active_tui:
                            sys.stdout.write(
                                f"\r  {GREEN}✓{RESET}  Loading App\033[K\n"
                            )
                            sys.stdout.flush()
                    self.update_component("App Server", "Ready")
                    self.add_lifecycle_event(
                        f"App Server ready at {self._url}", status="ok"
                    )
                    if (
                        self._mode == MODE_LIFECYCLE
                        and not self._initial_auto_advanced
                    ):
                        self._initial_auto_advanced = True
                        self.set_mode(MODE_STANDARD)

        # WebSocket client count (before noise filter so we never miss events)
        ws_ev = self._filter.ws_event(stripped)
        if ws_ev == "connect":
            self._ws_clients += 1
        elif ws_ev == "disconnect":
            self._ws_clients = max(0, self._ws_clients - 1)

        is_validation = (
            parsed.is_error
            or parsed.is_warning
            or self._filter.is_validation_issue(raw, stripped)
        )
        is_noise = parsed.is_noise or self._filter.is_noise(stripped)

        entry = LogLine(
            timestamp=ts,
            text=stripped,
            raw=raw,
            is_validation=is_validation,
            level=parsed.level,
            message=parsed.message,
            is_traceback=getattr(parsed, "is_traceback", False)
            or self._filter.is_traceback(stripped),
        )
        add_all(entry)
        if self._mode in (MODE_ALL, MODE_VERBOSE) and self._scroll_offset > 0:
            self._scroll_offset += 1

        if is_validation:
            is_indented = bool(stripped) and stripped[0] in (" ", "\t")
            if (
                is_indented or self._last_was_validation
            ) and not parsed.is_block_start:
                # Continuation of the current error block
                self._current_error_block.append(entry)
                if len(self._current_error_block) > self._max_logs:
                    self._current_error_block.pop(0)
            else:
                # New error event: start a fresh block
                self._validation_count += 1
                self._current_error_block.append(entry)
                if len(self._current_error_block) > self._max_logs:
                    self._current_error_block.pop(0)
            self._last_was_validation = True
        elif is_noise:
            # Noise (WS RECEIVE, static files, etc.) — drop from minimal log.
            pass
        else:
            # Real content line: marks the end of the current error context.
            self._last_was_validation = False
            add_minimal(entry)

    def _display_loop(self) -> None:
        while not self._terminate_event.is_set():
            try:
                while True:
                    line = self._log_queue.get_nowait()
                    if line is None:
                        self.container_exited = True
                        self._stop_event.set()
                        break
                    self._process_line(line)
            except queue.Empty:
                pass

            if not self._paused and self._mode in (
                MODE_LIFECYCLE,
                MODE_STANDARD,
                MODE_ALL,
                MODE_VERBOSE,
            ):
                self._renderer.render(
                    app_name=self._app_name,
                    status=self._status,
                    url=self._url,
                    ws_clients=self._ws_clients,
                    log_lines=(
                        self._all_log_lines
                        if self._mode in (MODE_ALL, MODE_VERBOSE)
                        else self._log_lines
                    ),
                    validation_count=self._validation_count,
                    current_error_block=self._current_error_block,
                    show_all=(self._mode == MODE_ALL),
                    scroll_offset=self._scroll_offset,
                    mode=self._mode,
                    components=self._components,
                    lifecycle_events=self._lifecycle_events,
                    startup_logs=self._startup_logs,
                    prompt_message=(
                        self._prompt_message if self._prompt_active else None
                    ),
                    prompt_options=self._prompt_options,
                    prompt_buffer=self._prompt_buffer,
                )
            self._render_event.wait(self.REFRESH_INTERVAL)
            self._render_event.clear()

    def _input_loop(self) -> None:
        if IS_WINDOWS:
            self._input_loop_windows()
        else:
            self._input_loop_unix()

    def _input_loop_windows(self) -> None:
        while not self._stop_event.is_set():
            if self._paused:
                time.sleep(0.05)
                continue
            if msvcrt.kbhit():
                ch = msvcrt.getch()
                if self._prompt_active:
                    if ch == b"\x03":  # Ctrl+C
                        self._prompt_result = ""
                        self._prompt_event.set()
                        self.set_status(STOPPING)
                        self._stop_event.set()
                    elif ch in (b"\r", b"\n"):
                        self._prompt_result = self._prompt_buffer
                        self._prompt_event.set()
                    elif ch in (b"\x08", b"\x7f"):  # Backspace
                        self._prompt_buffer = self._prompt_buffer[:-1]
                        self._render_event.set()
                    elif ch not in (b"\x00", b"\xe0", b"\x1b"):
                        try:
                            text = ch.decode("utf-8")
                            if text.isprintable():
                                self._prompt_buffer += text
                                self._render_event.set()
                        except Exception:
                            pass
                    continue

                if ch in (b"\t", b"\x09", b"\x01"):  # Tab or Ctrl+A
                    self.cycle_mode(forward=True)
                elif ch == b"\x00":  # Special key prefix
                    next_ch = msvcrt.getch()
                    if next_ch == b"\x0f":  # Shift+Tab on Windows
                        self.cycle_mode(forward=False)
                elif ch == b"\x03":  # Ctrl+C
                    self.set_status(STOPPING)
                    self._stop_event.set()
                elif ch == b"\x1b":  # ESC or ANSI sequence
                    time.sleep(0.02)
                    if msvcrt.kbhit():
                        next_ch = msvcrt.getch()
                        if next_ch in (b"[", b"O"):
                            if msvcrt.kbhit():
                                dir_ch = msvcrt.getch()
                                if dir_ch == b"A":
                                    self.scroll_up()
                                elif dir_ch == b"B":
                                    self.scroll_down()
                                elif dir_ch == b"<":
                                    seq = b""
                                    while msvcrt.kbhit():
                                        m_ch = msvcrt.getch()
                                        seq += m_ch
                                        if m_ch in (b"M", b"m"):
                                            break
                                    if seq.startswith(b"64;"):
                                        self.scroll_up(3)
                                    elif seq.startswith(b"65;"):
                                        self.scroll_down(3)
                    else:
                        self.detach()
                elif ch == b"\xe0":  # Special key prefix
                    next_ch = msvcrt.getch()
                    if next_ch in (b"H", b"\x48"):  # Up
                        self.scroll_up()
                    elif next_ch in (b"P", b"\x50"):  # Down
                        self.scroll_down()
                    elif next_ch in (b"I", b"\x49"):  # Page Up
                        self.scroll_up(5)
                    elif next_ch in (b"Q", b"\x51"):  # Page Down
                        self.scroll_down(5)
            time.sleep(0.1)

    def _input_loop_unix(self) -> None:
        try:
            fd = sys.stdin.fileno()
            self._old_settings = termios.tcgetattr(fd)
        except Exception:
            return

        try:
            tty.setcbreak(fd)
            while not self._stop_event.is_set():
                if self._paused:
                    time.sleep(0.05)
                    continue
                if select.select([fd], [], [], 0.1)[0]:
                    chunk = os.read(fd, 128)
                    if not chunk:
                        continue
                    if self._prompt_active:
                        if chunk == b"\x03":  # Ctrl+C
                            self._prompt_result = ""
                            self._prompt_event.set()
                            self.set_status(STOPPING)
                            self._stop_event.set()
                        elif chunk in (b"\r", b"\n"):
                            self._prompt_result = self._prompt_buffer
                            self._prompt_event.set()
                        elif chunk in (b"\x7f", b"\x08"):  # Backspace
                            self._prompt_buffer = self._prompt_buffer[:-1]
                            self._render_event.set()
                        elif not chunk.startswith(b"\x1b"):
                            try:
                                text = chunk.decode("utf-8")
                                if text.isprintable():
                                    self._prompt_buffer += text
                                    self._render_event.set()
                            except Exception:
                                pass
                        continue

                    if chunk in (b"\t", b"\x09", b"\x01"):  # Tab or Ctrl+A
                        self.cycle_mode(forward=True)
                    elif chunk == b"\x03":  # Ctrl+C
                        self.set_status(STOPPING)
                        self._stop_event.set()
                    elif chunk.startswith(b"\x1b"):
                        if chunk in (b"\x1b", b"\x1b[", b"\x1bO"):
                            if select.select([fd], [], [], 0.05)[0]:
                                chunk += os.read(fd, 128)
                        if chunk == b"\x1b":
                            self.detach()
                        elif chunk == b"\x1b[Z":  # Shift+Tab (Backtab)
                            self.cycle_mode(forward=False)
                        elif chunk in (b"\x1b[A", b"\x1bOA"):
                            self.scroll_up()
                        elif chunk in (b"\x1b[B", b"\x1bOB"):
                            self.scroll_down()
                        elif b"\x1b[<64;" in chunk or (
                            chunk.startswith(b"\x1b[M")
                            and len(chunk) >= 4
                            and chunk[3] == 0x60
                        ):  # Mouse Wheel Up (SGR or X11)
                            count = max(1, chunk.count(b"\x1b[<64;"))
                            self.scroll_up(3 * count)
                        elif b"\x1b[<65;" in chunk or (
                            chunk.startswith(b"\x1b[M")
                            and len(chunk) >= 4
                            and chunk[3] == 0x61
                        ):  # Mouse Wheel Down (SGR or X11)
                            count = max(1, chunk.count(b"\x1b[<65;"))
                            self.scroll_down(3 * count)
                        elif chunk in (b"\x1b[5~",):
                            self.scroll_up(5)
                        elif chunk in (b"\x1b[6~",):
                            self.scroll_down(5)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, self._old_settings)

    def start(self) -> None:
        """
        Usage:

        - Enters the alternate screen buffer, hides the cursor, and starts
          the background display and input loop threads.

        Notes:

        - The alternate screen keeps the step-progress output intact in the
          primary screen and gives the dashboard a clean slate with no
          cursor-jump flicker.
        """
        global _active_dashboard
        _active_dashboard = self
        try:
            import atexit

            atexit.register(self.stop)
        except Exception:
            pass
        try:
            from cave_cli.utils.logger import logger

            logger.add_listener(self._on_logger_message)
        except Exception:
            pass

        sys.stdout.write(
            ALT_SCREEN_ENTER + ALT_SCROLL_ENTER + MOUSE_ENTER + CURSOR_HIDE
        )
        sys.stdout.flush()
        self._display_thread = threading.Thread(
            target=self._display_loop, daemon=True
        )
        self._input_thread = threading.Thread(
            target=self._input_loop, daemon=True
        )
        self._display_thread.start()
        self._input_thread.start()

    def _on_logger_message(self, message: str, level: str) -> None:
        raw_msg = f"{level}: {message}" if level != "INFO" else message
        self.add_startup_log(raw_msg)

    def stop(self) -> None:
        """
        Usage:

        - Signals the display loop to stop, waits for it, then restores
          the primary screen buffer and cursor.
        """
        global _active_dashboard
        if _active_dashboard is self:
            _active_dashboard = None
        try:
            import atexit

            atexit.unregister(self.stop)
        except Exception:
            pass
        try:
            from cave_cli.utils.logger import logger

            logger.remove_listener(self._on_logger_message)
        except Exception:
            pass

        self._stop_event.set()
        self._terminate_event.set()
        self._render_event.set()
        self._log_queue.put(None)
        if self._display_thread is not None:
            self._display_thread.join(timeout=2.0)
        if hasattr(self, "_input_thread") and self._input_thread is not None:
            self._input_thread.join(timeout=2.0)

        sys.stdout.write(
            CURSOR_SHOW + MOUSE_EXIT + ALT_SCROLL_EXIT + ALT_SCREEN_EXIT
        )
        if self._mode == MODE_VERBOSE:
            cols, _ = shutil.get_terminal_size(fallback=(80, 24))
            bar_width = max(10, cols - 4)
            sys.stdout.write(
                f"\n  {BOLD}{CYAN}CAVE App (Verbose Mode){RESET}\n"
                f"  {'─' * bar_width}\n"
            )
            if self._startup_logs:
                for s_line in self._startup_logs:
                    sys.stdout.write(f"  {DIM}[startup]{RESET}  {s_line}\n")
            for entry in self._all_log_lines:
                ts = f"{DIM}{entry.timestamp}{RESET}"
                sys.stdout.write(f"  {ts}  {entry.raw}\n")
        else:
            sys.stdout.write(CLEAR_BELOW)
        sys.stdout.flush()


# ── Step-progress display (for other commands) ─────────────────────────────


_active_dashboard: RunDashboard | None = None


def get_active_dashboard() -> RunDashboard | None:
    """
    Usage:

    - Returns the currently active RunDashboard instance, if any.

    Returns:

    - ``dashboard``:
        - Type: RunDashboard | None
        - What: Active RunDashboard or None.
    """
    return _active_dashboard


def print_key_value(key: str, value: str, key_color: str = CYAN) -> None:
    """
    Usage:

    - Prints a key-value pair with a colored key and a separator.

    Requires:

    - ``key``:
        - Type: str
        - What: The label.

    - ``value``:
        - Type: str
        - What: The value.

    Optional:

    - ``key_color``:
        - Type: str
        - What: ANSI color code for the key.
        - Default: CYAN
    """
    if _QUIET:
        return
    sys.stdout.write(f"  {key_color}{key}{RESET}: {value}\n")
    sys.stdout.flush()


def print_section(title: str) -> None:
    """
    Usage:

    - Prints a bold section header with a separator line.

    Requires:

    - ``title``:
        - Type: str
        - What: Section label to display.
    """
    if _active_dashboard is not None and _active_dashboard.is_active_tui:
        _active_dashboard.add_lifecycle_event(title, status="info")
        return
    if _QUIET:
        return
    cols, _ = shutil.get_terminal_size(fallback=(80, 24))
    width = min(cols - 4, 60)
    sys.stdout.write(f"\n  {BOLD}{title}{RESET}\n  {'─' * width}\n")
    sys.stdout.flush()


def step_start(label: str) -> None:
    """
    Usage:

    - Prints an in-progress step indicator on the current line (no newline).
      Intended to be overwritten by ``step_done`` or ``step_fail``.

    Requires:

    - ``label``:
        - Type: str
        - What: Description of the step being started.
    """
    if _active_dashboard is not None:
        _active_dashboard.add_lifecycle_event(label, status="pending")
        _active_dashboard.infer_component_from_step(label, "Starting")
        if _active_dashboard.is_active_tui:
            return
    if _QUIET:
        return
    sys.stdout.write(f"  {YELLOW}●{RESET}  {label}...\033[K\r")
    sys.stdout.flush()


def step_done(label: str) -> None:
    """
    Usage:

    - Overwrites the current line with a green success indicator.

    Requires:

    - ``label``:
        - Type: str
        - What: Description of the completed step.
    """
    if _active_dashboard is not None:
        _active_dashboard.add_lifecycle_event(label, status="ok")
        _active_dashboard.infer_component_from_step(label, "Ready")
        if _active_dashboard.is_active_tui:
            return
    if _QUIET:
        return
    sys.stdout.write(f"\r  {GREEN}✓{RESET}  {label}\033[K\n")
    sys.stdout.flush()


def step_fail(label: str, detail: str = "") -> None:
    """
    Usage:

    - Overwrites the current line with a red failure indicator and
      optionally prints truncated detail lines below.

    Requires:

    - ``label``:
        - Type: str
        - What: Description of the failed step.

    Optional:

    - ``detail``:
        - Type: str
        - What: Multi-line detail text; last 8 lines are shown indented.
        - Default: ""
    """
    if _active_dashboard is not None:
        msg = f"{label}: {detail}" if detail else label
        _active_dashboard.add_lifecycle_event(msg, status="error")
        _active_dashboard.infer_component_from_step(label, "Error")
        if _active_dashboard.is_active_tui:
            return
    if _QUIET:
        return
    sys.stdout.write(f"\r  {RED}✗{RESET}  {label}\033[K\n")
    if detail:
        for line in detail.strip().splitlines()[-8:]:
            sys.stdout.write(f"       {DIM}{line}{RESET}\n")
    sys.stdout.flush()
