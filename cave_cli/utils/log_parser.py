import re
import sys
from typing import NamedTuple

_OUTER_PREFIX_RE = re.compile(
    r"^(INFO|WARNING|WARN|ERROR|DEBUG|CRITICAL):[ \t]?"
)
_HTTP_ACCESS_RE = re.compile(r'"[A-Z]+ \S* HTTP/\d\.\d"\s+(\d{3})')
_EXCEPTION_LINE_RE = re.compile(
    r"^([a-zA-Z_][a-zA-Z0-9_.]*(?:Error|Exception|Warning|Interrupt|Exit)|[a-zA-Z_][a-zA-Z0-9_.]*):(\s.*)?$"
)
_VALIDATION_START_RE = re.compile(r"^error\s*:\s*(\[|\{)", re.IGNORECASE)
_WARNING_START_RE = re.compile(r"^warning\s*:\s*(\[|\{)", re.IGNORECASE)

_NOISE_PATTERNS: tuple[str, ...] = (
    "WS RECEIVE",
    "SOCKET CONNECTION OPENED",
    "SOCKET CONNECTION CLOSED",
    "connection open",
    "connection closed",
    "WebSocket /cave/ws/ [accepted]",
    "Waiting for application startup",
    "Waiting for application shutdown",
    "Application startup complete",
    "Application shutdown complete",
    "Started server process ",
    "Finished server process ",
    "Uvicorn running on",
    "StatReload",
    "detected changes in",
    "changed, reloading",
    "Reloading",
    "reloading",
    "Started reloader process",
)


class ParsedLogLine(NamedTuple):
    level: str
    message: str
    raw: str
    is_noise: bool
    is_error: bool
    is_warning: bool
    is_block_start: bool = False
    is_traceback: bool = False


class LogParser:
    """
    Usage:

    - Normalizes raw container log output into consistent, filterable log entries

    Notes:

    - Strips redundant nested logger prefixes (e.g. ``INFO: INFO:     ...``)
    - Re-classifies soft validation errors and complete Python tracebacks as ERROR
    - Identifies repetitive websocket and HTTP access logs as DEBUG noise
    - Statefully tracks multiline tracebacks and validation blocks
    """

    def __init__(self) -> None:
        self.in_traceback: bool = False
        self.in_validation: bool = False
        self.in_warning: bool = False

    @staticmethod
    def strip_outer_prefixes(line: str) -> str:
        """
        Usage:

        - Strips outer uppercase log level prefixes like INFO: or WARNING:

        Requires:

        - ``line``:
            - Type: str
            - What: Raw log line

        Returns:

        - ``stripped``:
            - Type: str
            - What: Line with outer logger prefixes iteratively removed
        """
        result = line
        while True:
            sub = _OUTER_PREFIX_RE.sub("", result, count=1)
            if sub == result:
                break
            result = sub
        return result

    def parse_line(self, raw: str) -> ParsedLogLine:
        """
        Usage:

        - Parses a single raw log line, maintaining multiline error context

        Requires:

        - ``raw``:
            - Type: str
            - What: Raw log line

        Returns:

        - ``entry``:
            - Type: ParsedLogLine
            - What: Structured entry with level, clean message, and classification flags
        """
        cleaned = self.strip_outer_prefixes(raw)
        stripped = cleaned.strip()

        # 1. Traceback detection
        if (
            "Traceback (most recent call last):" in cleaned
            or "During handling of the above exception" in stripped
            or "The above exception was the direct cause" in stripped
        ):
            self.in_traceback = True
            self.in_validation = False
            self.in_warning = False
            return ParsedLogLine(
                level="ERROR",
                message=cleaned,
                raw=raw,
                is_noise=False,
                is_error=True,
                is_warning=False,
                is_block_start=True,
                is_traceback=True,
            )

        if stripped == "Exception in ASGI application":
            return ParsedLogLine(
                level="ERROR",
                message=cleaned,
                raw=raw,
                is_noise=False,
                is_error=True,
                is_warning=False,
                is_traceback=True,
            )

        if self.in_traceback:
            is_file_frame = stripped.startswith(
                'File "'
            ) or stripped.startswith("File '")
            is_indented = cleaned.startswith(" ") or cleaned.startswith("\t")
            is_code_marker = (
                any(c in cleaned for c in ("^", "~")) or not stripped
            )

            if (
                not is_file_frame
                and not is_code_marker
                and _EXCEPTION_LINE_RE.match(stripped)
            ):
                self.in_traceback = False
                return ParsedLogLine(
                    level="ERROR",
                    message=cleaned,
                    raw=raw,
                    is_noise=False,
                    is_error=True,
                    is_warning=False,
                    is_traceback=False,
                )

            return ParsedLogLine(
                level="ERROR",
                message=cleaned,
                raw=raw,
                is_noise=False,
                is_error=True,
                is_warning=False,
                is_traceback=True,
            )

        # 2. Validation error detection (cave_utils soft errors)
        is_val_start = bool(_VALIDATION_START_RE.match(stripped)) or any(
            stripped.lower().startswith(p)
            for p in ("error:", "validation failed", "validationerror")
        )
        if is_val_start:
            self.in_validation = True
            self.in_warning = False
            self.in_traceback = False
            return ParsedLogLine(
                level="ERROR",
                message=cleaned,
                raw=raw,
                is_noise=False,
                is_error=True,
                is_warning=False,
                is_block_start=True,
            )

        if self.in_validation:
            is_indented = cleaned.startswith(" ") or cleaned.startswith("\t")
            has_val_keywords = any(
                k in cleaned for k in ("Invalid value", "Accepted Values")
            )
            if is_indented or has_val_keywords:
                return ParsedLogLine(
                    level="ERROR",
                    message=cleaned,
                    raw=raw,
                    is_noise=False,
                    is_error=True,
                    is_warning=False,
                )
            self.in_validation = False

        # 3. Validation warning detection
        is_new_warn_header = bool(_WARNING_START_RE.match(stripped))
        if self.in_warning and not is_new_warn_header:
            if (
                cleaned.startswith(" ")
                or cleaned.startswith("\t")
                or stripped.startswith("Unknown Fields:")
            ):
                return ParsedLogLine(
                    level="WARN",
                    message=cleaned,
                    raw=raw,
                    is_noise=False,
                    is_error=False,
                    is_warning=True,
                    is_block_start=False,
                )
            self.in_warning = False

        is_warn_start = (
            is_new_warn_header
            or stripped.startswith("Unknown Fields:")
            or stripped.startswith("DeprecationWarning")
            or stripped.startswith("RuntimeWarning")
        )
        if is_warn_start:
            self.in_warning = True
            self.in_validation = False
            self.in_traceback = False
            return ParsedLogLine(
                level="WARN",
                message=cleaned,
                raw=raw,
                is_noise=False,
                is_error=False,
                is_warning=True,
                is_block_start=True,
            )

        # 4. HTTP Access logs
        access_match = _HTTP_ACCESS_RE.search(stripped)
        if access_match:
            status_code = int(access_match.group(1))
            display_msg = stripped
            if status_code >= 500:
                return ParsedLogLine(
                    level="ERROR",
                    message=display_msg,
                    raw=raw,
                    is_noise=False,
                    is_error=True,
                    is_warning=False,
                )
            if status_code >= 400:
                return ParsedLogLine(
                    level="WARN",
                    message=display_msg,
                    raw=raw,
                    is_noise=False,
                    is_error=False,
                    is_warning=True,
                )
            return ParsedLogLine(
                level="DEBUG",
                message=display_msg,
                raw=raw,
                is_noise=True,
                is_error=False,
                is_warning=False,
            )

        # 5. Websocket and protocol noise
        if any(p in stripped for p in _NOISE_PATTERNS):
            self.in_traceback = False
            self.in_validation = False
            self.in_warning = False
            return ParsedLogLine(
                level="DEBUG",
                message=stripped,
                raw=raw,
                is_noise=True,
                is_error=False,
                is_warning=False,
            )

        # 6. Explicit Error or Warning lines
        raw_upper = raw.upper()
        if raw_upper.startswith("ERROR:") or raw_upper.startswith("CRITICAL:"):
            self.in_traceback = False
            self.in_validation = False
            self.in_warning = False
            return ParsedLogLine(
                level="ERROR",
                message=cleaned,
                raw=raw,
                is_noise=False,
                is_error=True,
                is_warning=False,
                is_block_start=True,
            )
        if raw_upper.startswith("WARN:") or raw_upper.startswith("WARNING:"):
            self.in_traceback = False
            self.in_validation = False
            self.in_warning = False
            return ParsedLogLine(
                level="WARN",
                message=cleaned,
                raw=raw,
                is_noise=False,
                is_error=False,
                is_warning=True,
                is_block_start=True,
            )

        # 7. Default: INFO application log
        self.in_traceback = False
        self.in_validation = False
        self.in_warning = False
        return ParsedLogLine(
            level="INFO",
            message=cleaned,
            raw=raw,
            is_noise=False,
            is_error=False,
            is_warning=False,
        )

    @staticmethod
    def format_line(entry: ParsedLogLine, color: bool = True) -> str:
        """
        Usage:

        - Formats a ParsedLogLine for display with optional ANSI styling

        Requires:

        - ``entry``:
            - Type: ParsedLogLine
            - What: Parsed log entry

        Optional:

        - ``color``:
            - Type: bool
            - What: Whether to apply ANSI color codes
            - Default: True

        Returns:

        - ``formatted``:
            - Type: str
            - What: Formatted line string
        """
        if not color:
            return f"{entry.level}: {entry.message}"

        from cave_cli.utils.display import (
            BOLD,
            CYAN,
            DIM,
            GREEN,
            RED,
            RESET,
            YELLOW,
        )

        if entry.level == "ERROR":
            return f"{RED}{BOLD}ERROR:{RESET} {entry.message}"
        if entry.level == "WARN":
            return f"{YELLOW}{BOLD}WARN:{RESET} {entry.message}"
        if entry.level == "DEBUG":
            return f"{DIM}DEBUG: {entry.message}{RESET}"
        return f"{CYAN}INFO:{RESET} {entry.message}"

    @staticmethod
    def should_display(
        entry: ParsedLogLine,
        errors_only: bool = False,
        include_warnings: bool = False,
        show_all: bool = False,
    ) -> bool:
        """
        Usage:

        - Determines if an entry matches the active filter criteria

        Requires:

        - ``entry``:
            - Type: ParsedLogLine
            - What: Parsed log entry

        Optional:

        - ``errors_only``:
            - Type: bool
            - What: Only show errors
            - Default: False

        - ``include_warnings``:
            - Type: bool
            - What: Include warnings with errors
            - Default: False

        - ``show_all``:
            - Type: bool
            - What: Show all lines including debug noise
            - Default: False

        Returns:

        - ``display``:
            - Type: bool
            - What: Whether to output this line
        """
        if errors_only:
            return entry.is_error
        if include_warnings:
            return entry.is_error or entry.is_warning
        if show_all:
            return True
        return not entry.is_noise
