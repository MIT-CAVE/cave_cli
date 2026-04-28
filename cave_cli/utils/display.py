import queue
import re
import shutil
import sys
import threading
import time
from dataclasses import dataclass


# ── ANSI escape codes ──────────────────────────────────────────────────────

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"

CURSOR_HIDE = "\033[?25l"
CURSOR_SHOW = "\033[?25h"
ALT_SCREEN_ENTER = "\033[?1049h"
ALT_SCREEN_EXIT = "\033[?1049l"
CURSOR_HOME = "\033[H"
CLEAR_BELOW = "\033[J"
CLEAR_EOL = "\033[K"

# ── Server status constants ────────────────────────────────────────────────

BUILDING = "building"
LOADING = "loading"
READY = "ready"
ERROR = "error"
STOPPING = "stopping"


# ── Data structures ────────────────────────────────────────────────────────


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

    - ``is_validation``:
        - Type: bool
        - What: Whether this line belongs in the Validation Issues panel.
        - Default: False
    """

    timestamp: str
    text: str
    is_validation: bool = False


# ── Log filtering ──────────────────────────────────────────────────────────

_LEVEL_PREFIX_RE = re.compile(
    r"^(INFO|WARNING|WARN|ERROR|DEBUG|CRITICAL): ", re.IGNORECASE
)

# Lines to silently drop in clean mode (very noisy, no user value).
# WebSocket CONNECT/DISCONNECT are processed for client count but not displayed.
_SKIP_PATTERNS: tuple[str, ...] = (
    "WS RECEIVE  ",
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
    # Current Date. EG:  April 28, 2026
    f"{time.strftime('%B %d, %Y')}",
)

# Lines that belong in the Validation Issues panel (matched against stripped text)
_VALIDATION_PATTERNS: tuple[str, ...] = (
    "Traceback (most recent call last)",
    "An error occurred",
    "Exception:",
    "warning:",
    "Unknown Fields:",
    "ValidationError",
    "validation failed",
    "Invalid ",
    "DeprecationWarning",
    "RuntimeWarning",
)

_LOADING_TRIGGER = "Starting ASGI"
_READY_TRIGGER = "Quit the server with CONTROL-C"

_WS_CONNECT = "WebSocket CONNECT "
_WS_DISCONNECT = "WebSocket DISCONNECT "


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
        """
        return _LEVEL_PREFIX_RE.sub("", line, count=1)

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
        if _READY_TRIGGER in stripped:
            return READY
        if "Starting ASGI" in stripped or "Starting development server" in stripped:
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
        """
        if _WS_CONNECT in stripped:
            return "connect"
        if _WS_DISCONNECT in stripped:
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
        """
        raw_upper = raw.upper()
        if raw_upper.startswith("WARNING:") or raw_upper.startswith("ERROR:"):
            return True
        if stripped and stripped[0] in (" ", "\t"):
            return True
        return any(p in stripped for p in _VALIDATION_PATTERNS)


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
    _HEADER_LINES = 4    # ━ + title + ━ + blank
    _LOG_FIXED = 3       # "Recent Activity" + top-rule + bottom-rule
    _FOOTER_LINES = 2    # blank + hint line
    _FIXED_BASE = _HEADER_LINES + _LOG_FIXED + _FOOTER_LINES  # = 9
    _VAL_FIXED = 4       # blank + label + top-rule + bottom-rule
    _MAX_ERROR_LINES = 8 # maximum validation lines shown from current block
    _MIN_LOG_LINES = 3   # guaranteed minimum log lines even with validation

    @staticmethod
    def _status_str(status: str) -> str:
        indicators: dict[str, str] = {
            BUILDING: f"{YELLOW}● Building{RESET}",
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
        """
        cols, rows = shutil.get_terminal_size(fallback=(80, 24))
        bar_width = max(10, cols - 4)

        # Budget: rows - 1 ensures no trailing-newline scroll on a full screen.
        budget = rows - 1

        has_validation = bool(current_error_block) or validation_count > 0

        # Determine how many error lines to show, shrinking if the terminal
        # is too short to guarantee _MIN_LOG_LINES of activity log.
        desired_v = min(len(current_error_block), self._MAX_ERROR_LINES)
        if has_validation:
            available_log = (
                budget - self._FIXED_BASE - self._VAL_FIXED - desired_v
            )
            if available_log < self._MIN_LOG_LINES:
                desired_v = max(
                    0,
                    budget
                    - self._FIXED_BASE
                    - self._VAL_FIXED
                    - self._MIN_LOG_LINES,
                )
                if desired_v == 0:
                    has_validation = False
        shown_errors = current_error_block[-desired_v:] if desired_v > 0 else []

        val_section_height = (
            self._VAL_FIXED + len(shown_errors) if has_validation else 0
        )
        max_log_lines = max(
            0, budget - self._FIXED_BASE - val_section_height
        )
        visible_logs = log_lines[-max_log_lines:]

        lines: list[str] = []

        # ── Header ────────────────────────────────────────────────────────
        lines.append(f"  {BOLD}{'━' * bar_width}{RESET}")
        ws_str = (
            f"  │  {DIM}{ws_clients} client{'s' if ws_clients != 1 else ''}{RESET}"
            if ws_clients > 0
            else ""
        )
        title = (
            f"  {BOLD}{CYAN}CAVE{RESET}"
            f"  │  {BOLD}{app_name}{RESET}"
            f"  │  {self._status_str(status)}"
            f"{ws_str}"
            f"  │  {DIM}{url}{RESET}"
        )
        lines.append(title)
        lines.append(f"  {BOLD}{'━' * bar_width}{RESET}")
        lines.append("")

        # ── Recent Activity ────────────────────────────────────────────────
        lines.append(f"  {BOLD}Recent Activity{RESET}")
        lines.append(f"  {'─' * bar_width}")
        for entry in visible_logs:
            ts = f"{DIM}{entry.timestamp}{RESET}"
            text = self._truncate(entry.text, cols - 14)
            lines.append(f"  {ts}  {text}")
        lines.append(f"  {'─' * bar_width}")

        # ── Validation Issues ──────────────────────────────────────────────
        if has_validation:
            lines.append("")
            count_str = f"{validation_count} issue{'s' if validation_count != 1 else ''}"
            lines.append(
                f"  {BOLD}Validation Issues{RESET}  {RED}({count_str}){RESET}"
            )
            lines.append(f"  {'─' * bar_width}")
            for entry in shown_errors:
                ts = f"{DIM}{entry.timestamp}{RESET}"
                text = self._truncate(entry.text, cols - 14)
                lines.append(f"  {ts}  {RED}{text}{RESET}")
            lines.append(f"  {'─' * bar_width}")

        # ── Footer ─────────────────────────────────────────────────────────
        lines.append("")
        lines.append(f"  {DIM}Ctrl+C to stop  │  --all for raw output{RESET}")

        # Write the full frame atomically: move to top-left, write each line
        # with CLEAR_EOL to erase leftover characters.
        buf = CURSOR_HOME
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

    Notes:

    - Call ``start()`` after setting up signal handlers and starting the
      container. Call ``stop()`` in a finally block to restore the terminal.
    """

    REFRESH_INTERVAL: float = 0.2

    def __init__(self, app_name: str, url: str, stop_event: threading.Event | None = None) -> None:
        self._app_name = app_name
        self._url = url
        self._status: str = BUILDING
        self._ws_clients: int = 0
        self._log_lines: list[LogLine] = []
        self._validation_count: int = 0
        self._current_error_block: list[LogLine] = []
        self._last_was_validation: bool = False
        self._log_queue: queue.Queue[str | None] = queue.Queue()
        self._renderer = DashboardRenderer()
        self._filter = LogFilter()
        self._stop_event = stop_event or threading.Event()
        self._display_thread: threading.Thread | None = None

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

    def _process_line(self, raw: str) -> None:
        stripped = self._filter.strip_level_prefix(raw).expandtabs()
        ts = time.strftime("%H:%M:%S")

        # Status transitions (always checked)
        new_status = self._filter.classify_status(stripped)
        if new_status:
            self._status = new_status
            if new_status == LOADING:
                self._log_lines.append(LogLine(timestamp=ts, text="App Loading"))
            elif new_status == READY:
                self._log_lines.append(LogLine(timestamp=ts, text="Ready"))

        # WebSocket client count (before noise filter so we never miss events)
        ws_ev = self._filter.ws_event(stripped)
        if ws_ev == "connect":
            self._ws_clients += 1
        elif ws_ev == "disconnect":
            self._ws_clients = max(0, self._ws_clients - 1)

        if self._filter.is_validation_issue(raw, stripped):
            entry = LogLine(timestamp=ts, text=stripped, is_validation=True)
            is_indented = bool(stripped) and stripped[0] in (" ", "\t")
            if is_indented or self._last_was_validation:
                # Continuation of the current error block
                self._current_error_block.append(entry)
            else:
                # New error event: start a fresh block
                self._validation_count += 1
                self._current_error_block = [entry]
            self._last_was_validation = True
        elif self._filter.is_noise(stripped):
            # Noise (WS RECEIVE, static files, etc.) — drop silently.
            # Does NOT reset _last_was_validation so noise between traceback
            # lines doesn't break the block grouping.
            pass
        else:
            # Real content line: marks the end of the current error context.
            self._last_was_validation = False
            self._log_lines.append(LogLine(timestamp=ts, text=stripped))

    def _display_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                while True:
                    line = self._log_queue.get_nowait()
                    if line is None:
                        self._stop_event.set()
                        break
                    self._process_line(line)
            except queue.Empty:
                pass
            self._renderer.render(
                app_name=self._app_name,
                status=self._status,
                url=self._url,
                ws_clients=self._ws_clients,
                log_lines=self._log_lines,
                validation_count=self._validation_count,
                current_error_block=self._current_error_block,
            )
            self._stop_event.wait(self.REFRESH_INTERVAL)

    def start(self) -> None:
        """
        Usage:

        - Enters the alternate screen buffer, hides the cursor, and starts
          the background display loop thread.

        Notes:

        - The alternate screen keeps the step-progress output intact in the
          primary screen and gives the dashboard a clean slate with no
          cursor-jump flicker.
        """
        sys.stdout.write(ALT_SCREEN_ENTER + CURSOR_HIDE)
        sys.stdout.flush()
        self._display_thread = threading.Thread(
            target=self._display_loop, daemon=True
        )
        self._display_thread.start()

    def stop(self) -> None:
        """
        Usage:

        - Signals the display loop to stop, waits for it, then restores
          the primary screen buffer and cursor.
        """
        self._stop_event.set()
        self._log_queue.put(None)
        if self._display_thread is not None:
            self._display_thread.join(timeout=2.0)
        sys.stdout.write(CURSOR_SHOW + ALT_SCREEN_EXIT)
        sys.stdout.flush()


# ── Step-progress display (for other commands) ─────────────────────────────


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
    sys.stdout.write(f"\r  {RED}✗{RESET}  {label}\033[K\n")
    if detail:
        for line in detail.strip().splitlines()[-8:]:
            sys.stdout.write(f"       {DIM}{line}{RESET}\n")
    sys.stdout.flush()
