import argparse
import os
import sys
import time

from cave_cli.utils.log_parser import LogParser, ParsedLogLine
from cave_cli.utils.logger import logger
from cave_cli.utils.task_queue import (
    get_run_log_path,
    get_task,
    get_task_log_path,
    list_tasks,
)
from cave_cli.utils.validate import get_app


def _follow_file(
    path: str,
    errors_only: bool = False,
    include_warnings: bool = False,
    show_all: bool = False,
    raw_mode: bool = False,
    color: bool = True,
    start_pos: int | None = None,
    task_id: int | None = None,
    app_dir: str | None = None,
) -> None:
    """
    Usage:

    - Follows an existing file, streaming new lines as they are appended

    Requires:

    - ``path``:
        - Type: str
        - What: Absolute path to the file to follow

    Optional:

    - ``errors_only``:
        - Type: bool
        - What: Whether to output only error and traceback lines
        - Default: False

    - ``include_warnings``:
        - Type: bool
        - What: Whether to include warning lines
        - Default: False

    - ``show_all``:
        - Type: bool
        - What: Whether to show all lines including verbose debug noise
        - Default: False

    - ``raw_mode``:
        - Type: bool
        - What: Whether to output raw lines without level formatting
        - Default: False

    - ``color``:
        - Type: bool
        - What: Whether to apply ANSI colors
        - Default: True

    - ``start_pos``:
        - Type: int | None
        - What: Byte offset to begin reading from (defaults to current file size)
        - Default: None

    - ``task_id``:
        - Type: int | None
        - What: Incremental task ID to track for completion
        - Default: None

    - ``app_dir``:
        - Type: str | None
        - What: Root app directory for checking task completion status
        - Default: None
    """
    while not os.path.exists(path):
        time.sleep(0.2)

    parser = LogParser()
    current_f = None
    try:
        current_f = open(path, "r", encoding="utf-8", errors="replace")
        stat = os.fstat(current_f.fileno())
        current_ino = stat.st_ino
        current_dev = stat.st_dev

        if start_pos is not None:
            current_f.seek(start_pos)
        else:
            current_f.seek(0, os.SEEK_END)

        def _output_line(raw_line: str) -> None:
            if raw_mode:
                sys.stdout.write(raw_line)
                sys.stdout.flush()
                return

            entry = parser.parse_line(raw_line.rstrip())
            if parser.should_display(
                entry,
                errors_only=errors_only,
                include_warnings=include_warnings,
                show_all=show_all,
            ):
                formatted = parser.format_line(entry, color=color)
                sys.stdout.write(formatted + "\n")
                sys.stdout.flush()

        while True:
            line = current_f.readline()
            if line:
                _output_line(line)
                continue

            # No new line available right now. Check if task completed.
            if task_id is not None and app_dir is not None:
                t = get_task(app_dir, task_id)
                if t and t.get("status") in (
                    "completed",
                    "failed",
                    "cancelled",
                ):
                    for rest in current_f:
                        _output_line(rest)
                    break

            time.sleep(0.1)

            # Check if file was rotated (new inode), recreated, or truncated
            try:
                disk_stat = os.stat(path)
                if (
                    disk_stat.st_ino != current_ino
                    or disk_stat.st_dev != current_dev
                ):
                    for rest in current_f:
                        _output_line(rest)
                    current_f.close()
                    current_f = open(
                        path, "r", encoding="utf-8", errors="replace"
                    )
                    stat = os.fstat(current_f.fileno())
                    current_ino = stat.st_ino
                    current_dev = stat.st_dev
                elif disk_stat.st_size < current_f.tell():
                    current_f.seek(0)
            except (FileNotFoundError, OSError):
                time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        if current_f:
            try:
                current_f.close()
            except Exception:
                pass


def logs(args: argparse.Namespace) -> None:
    """
    Usage:

    - Inspects, streams, or locates server run logs or task execution logs

    Requires:

    - ``args``:
        - Type: argparse.Namespace
        - What: Parsed command-line arguments
    """
    app_dir, app_name = get_app()

    task_id_arg = getattr(args, "task", None)
    filter_errors = getattr(args, "errors", False)
    include_warnings = getattr(args, "warnings", False)
    show_all = getattr(args, "all", False)
    raw_mode = getattr(args, "raw", False)
    show_path_only = getattr(args, "path", False)
    follow = getattr(args, "follow", False)
    clear = getattr(args, "clear", False)
    lines_count = getattr(args, "lines", None)
    color = sys.stdout.isatty() and not getattr(args, "no_color", False)

    # Determine target log file
    if task_id_arg is not None:
        if task_id_arg > 0:
            target_id = task_id_arg
        else:
            tasks = list_tasks(app_dir)
            if not tasks:
                logger.info(f"No tasks found for '{app_name}'.")
                return
            target_id = tasks[-1]["id"]
        log_path = get_task_log_path(app_dir, target_id)
        label = f"Task #{target_id}"
    else:
        target_id = None
        log_path = get_run_log_path(app_dir)
        label = f"Server '{app_name}'"

    if show_path_only:
        print(log_path)
        return

    if clear:
        if os.path.exists(log_path):
            try:
                with open(log_path, "w", encoding="utf-8") as f:
                    f.truncate(0)
                logger.success(f"Cleared logs at: {log_path}")
            except Exception as e:
                logger.error(f"Failed to clear log file: {e}")
                sys.exit(1)
        else:
            logger.info("Log file does not exist. Nothing to clear.")
        return

    if not os.path.exists(log_path):
        if follow:
            logger.info(
                f"Waiting for {label} logs at: {log_path} (Press Ctrl+C to cancel)..."
            )
            try:
                while not os.path.exists(log_path):
                    time.sleep(0.2)
            except KeyboardInterrupt:
                return
        else:
            if task_id_arg is not None:
                logger.warn(f"No log file found for {label} at: {log_path}")
            else:
                logger.warn(
                    f"No server logs found at: {log_path}\n"
                    f"Run 'cave run' to start the app and generate server logs."
                )
            return

    start_pos = 0
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            start_pos = f.tell()
    except Exception as e:
        logger.error(f"Failed to read log file: {e}")
        sys.exit(1)

    parser = LogParser()
    display_lines: list[str] = []
    for l in lines:
        if raw_mode:
            display_lines.append(l)
        else:
            entry = parser.parse_line(l.rstrip())
            if parser.should_display(
                entry,
                errors_only=filter_errors,
                include_warnings=include_warnings,
                show_all=show_all,
            ):
                display_lines.append(
                    parser.format_line(entry, color=color) + "\n"
                )

    if filter_errors and not display_lines and not follow:
        logger.info(f"No errors found in {label} logs.")
        return

    if lines_count is not None and lines_count > 0:
        display_lines = display_lines[-lines_count:]
    elif follow and lines_count is None:
        display_lines = display_lines[-50:]

    for l in display_lines:
        sys.stdout.write(l)
    sys.stdout.flush()

    if follow:
        _follow_file(
            path=log_path,
            errors_only=filter_errors,
            include_warnings=include_warnings,
            show_all=show_all,
            raw_mode=raw_mode,
            color=color,
            start_pos=start_pos,
            task_id=target_id,
            app_dir=app_dir,
        )
