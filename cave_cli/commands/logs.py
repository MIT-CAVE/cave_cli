import argparse
import os
import sys
import time

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
    filter_errors: bool = False,
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

    - ``filter_errors``:
        - Type: bool
        - What: Whether to output only error and traceback lines
        - Default: False

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

        while True:
            line = current_f.readline()
            if line:
                if filter_errors:
                    is_err = any(
                        k in line
                        for k in ("ERROR", "CRITICAL", "Traceback", "Exception")
                    )
                    if not is_err:
                        continue
                sys.stdout.write(line)
                sys.stdout.flush()
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
                        if not filter_errors or any(
                            k in rest
                            for k in (
                                "ERROR",
                                "CRITICAL",
                                "Traceback",
                                "Exception",
                            )
                        ):
                            sys.stdout.write(rest)
                    sys.stdout.flush()
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
                        if not filter_errors or any(
                            k in rest
                            for k in (
                                "ERROR",
                                "CRITICAL",
                                "Traceback",
                                "Exception",
                            )
                        ):
                            sys.stdout.write(rest)
                    sys.stdout.flush()
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
    show_path_only = getattr(args, "path", False)
    follow = getattr(args, "follow", False)
    clear = getattr(args, "clear", False)
    lines_count = getattr(args, "lines", None)

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

    if filter_errors:
        display_lines = [
            l
            for l in lines
            if any(
                k in l for k in ("ERROR", "CRITICAL", "Traceback", "Exception")
            )
        ]
        if not display_lines and not follow:
            logger.info(f"No errors found in {label} logs.")
            return
    else:
        display_lines = lines

    if lines_count is not None:
        if lines_count > 0:
            display_lines = display_lines[-lines_count:]
        else:
            display_lines = []
    elif follow:
        display_lines = display_lines[-50:]

    for l in display_lines:
        sys.stdout.write(l)
    sys.stdout.flush()

    if follow:
        _follow_file(
            path=log_path,
            filter_errors=filter_errors,
            start_pos=start_pos,
            task_id=target_id,
            app_dir=app_dir,
        )
