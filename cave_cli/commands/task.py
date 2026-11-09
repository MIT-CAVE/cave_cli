import argparse
import os
import shlex
import subprocess
import sys
import time
from typing import IO, Any

from cave_cli.utils.display import print_section
from cave_cli.utils.logger import logger
from cave_cli.utils.task_queue import (
    TaskQueueCancelledError,
    TaskQueueLock,
    cancel_all_tasks,
    cancel_task,
    clean_completed_tasks,
    get_task,
    get_task_log_path,
    list_tasks,
    register_task,
    update_task_pid,
    update_task_status,
)
from cave_cli.utils.task_server import (
    ensure_task_idle_watcher,
    is_task_server_running,
    reset_task_server,
    run_command_in_task_server,
    start_task_server,
    stop_task_server,
    touch_task_activity,
)
from cave_cli.utils.validate import get_app


def _format_duration(task: dict) -> str:
    started = task.get("started_at")
    ended = task.get("ended_at")
    status = task.get("status")
    if started and ended:
        diff = max(0, int(ended - started))
        return f"{diff}s"
    if started and status == "running":
        diff = max(0, int(time.time() - started))
        return f"{diff}s"
    if status == "queued":
        return "queued"
    return "-"


def _print_tasks_table(
    tasks: list[dict], app_name: str, only_active: bool = False
) -> None:
    print_section(f"Tasks for {app_name}")
    if not tasks:
        if only_active:
            logger.info(f"No active tasks for '{app_name}'.")
        else:
            logger.info(f"No tasks recorded for '{app_name}'.")
        return

    headers = ["ID", "Status", "Command", "Arguments", "Duration", "PID"]
    rows = []
    for t in tasks:
        t_id = str(t.get("id", ""))
        status = str(t.get("status", ""))
        cmd = str(t.get("command", ""))
        args = " ".join(t.get("args", [])) or "-"
        dur = _format_duration(t)
        pid = str(t.get("pid", ""))
        rows.append([t_id, status, cmd, args, dur, pid])

    # Calculate column widths
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(val))

    def format_row(values: list[str]) -> str:
        padded = [val.ljust(col_widths[i]) for i, val in enumerate(values)]
        return f"│ {' │ '.join(padded)} │"

    def format_sep(left: str, mid: str, right: str) -> str:
        pieces = ["─" * (w + 2) for w in col_widths]
        return f"{left}{mid.join(pieces)}{right}"

    top_border = format_sep("┌", "┬", "┐")
    header_sep = format_sep("├", "┼", "┤")
    bottom_border = format_sep("└", "┴", "┘")

    print(top_border)
    print(format_row(headers))
    print(header_sep)
    for row in rows:
        print(format_row(row))
    print(bottom_border)


def resolve_container_command(cmd: list[str]) -> list[str]:
    """
    Usage:

    - Prepares a command list for execution inside the task Django container

    Requires:

    - ``cmd``:
        - Type: list[str]
        - What: Raw command and arguments list

    Returns:

    - ``resolved``:
        - Type: list[str]
        - What: Command list with python or bash interpreter prefix applied when appropriate
    """
    if not cmd:
        return []
    token = cmd[0]
    if token.endswith(".py") and token != "python":
        return ["python", token] + cmd[1:]
    if token.endswith(".sh") and token not in ("bash", "sh"):
        return ["bash", token] + cmd[1:]
    return list(cmd)


def spawn_task_runner(
    app_dir: str,
    app_name: str,
    task_id: int,
    docker_args: list[str] | None = None,
) -> int:
    """
    Usage:

    - Spawns a background detached process to execute the task in the queue

    Requires:

    - ``app_dir``:
        - Type: str
        - What: Root directory of CAVE app

    - ``app_name``:
        - Type: str
        - What: Name of CAVE app

    - ``task_id``:
        - Type: int
        - What: Incremental ID of task to run

    Optional:

    - ``docker_args``:
        - Type: list[str] | None
        - What: Additional docker args
        - Default: None

    Returns:

    - ``pid``:
        - Type: int
        - What: PID of spawned process
    """
    cmd = [
        sys.executable,
        "-m",
        "cave_cli.cli",
        "_task-runner",
        app_dir,
        app_name,
        str(task_id),
    ]
    if docker_args:
        cmd.extend(["--docker-args", " ".join(docker_args)])

    kwargs: dict = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }
    if sys.platform != "win32":
        kwargs["start_new_session"] = True
    else:
        kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        )

    proc = subprocess.Popen(cmd, **kwargs)
    return proc.pid


def run_task_worker(
    app_dir: str,
    app_name: str,
    task_id: int,
    docker_args_str: str = "",
) -> None:
    """
    Usage:

    - Internal worker process that waits for task queue lock and executes command in container

    Requires:

    - ``app_dir``:
        - Type: str
        - What: Root directory of CAVE app

    - ``app_name``:
        - Type: str
        - What: Name of CAVE app

    - ``task_id``:
        - Type: int
        - What: Incremental ID of task to execute

    Optional:

    - ``docker_args_str``:
        - Type: str
        - What: Docker arguments string
        - Default: ""
    """
    update_task_pid(app_dir, task_id, os.getpid())
    task_info = get_task(app_dir, task_id)
    if not task_info:
        return

    extra_docker_args = shlex.split(docker_args_str) if docker_args_str else []
    exec_cmd = task_info.get("exec_command") or (
        [task_info["command"]] + task_info.get("args", [])
    )
    container_cmd = resolve_container_command(exec_cmd)
    extra_env = task_info.get("extra_env") or {}
    log_path = get_task_log_path(app_dir, task_id)

    try:
        with TaskQueueLock(
            app_dir,
            app_name,
            command=task_info["command"],
            command_args=task_info.get("args", []),
            task_id=task_id,
        ):
            # Ensure log file exists and is cleanly truncated for this run
            with open(log_path, "w", encoding="utf-8") as f:
                pass

            if not is_task_server_running(app_name):
                start_task_server(app_dir, app_name, extra_docker_args)
            else:
                logger.debug(f"Reusing warm task server for '{app_name}'.")

            with open(log_path, "a", encoding="utf-8", buffering=1) as log_f:
                exit_code = run_command_in_task_server(
                    app_name=app_name,
                    command=container_cmd,
                    extra_env=extra_env,
                    log_file=log_f,
                )

            touch_task_activity(app_dir, app_name)
            ensure_task_idle_watcher(app_dir, app_name, 10)
            cur_task = get_task(app_dir, task_id)
            if not cur_task or cur_task.get("status") != "cancelled":
                update_task_status(
                    app_dir,
                    task_id,
                    "completed" if exit_code == 0 else "failed",
                    exit_code=exit_code,
                )
    except TaskQueueCancelledError:
        with open(log_path, "a", encoding="utf-8") as log_f:
            log_f.write("\nTask was canceled before execution.\n")


def _read_nonblocking_key(fd: int | None = None) -> str | None:
    if sys.platform == "win32":
        try:
            import msvcrt

            if msvcrt.kbhit():
                ch = msvcrt.getch()
                if ch in (b"\x1b", b"q"):
                    return "ESC"
        except Exception:
            pass
        return None

    if fd is not None:
        try:
            import select

            if select.select([fd], [], [], 0)[0]:
                ch = os.read(fd, 1)
                if ch == b"\x1b":
                    if select.select([fd], [], [], 0.05)[0]:
                        os.read(fd, 2)
                        return None
                    return "ESC"
                if ch in (b"q", b"Q"):
                    return "ESC"
        except Exception:
            pass
    return None


def _get_next_active_task(
    app_dir: str, after_id: int | None = None
) -> dict[str, Any] | None:
    """
    Usage:

    - Resolves the next running or queued task in the queue

    Requires:

    - ``app_dir``:
        - Type: str
        - What: Root directory of CAVE app

    Optional:

    - ``after_id``:
        - Type: int | None
        - What: Optional task ID threshold; only considers tasks with ID strictly greater than after_id
        - Default: None

    Returns:

    - ``task``:
        - Type: dict[str, Any] | None
        - What: Next active task dictionary or None if no active tasks remain
    """
    tasks = list_tasks(app_dir)
    if after_id is not None:
        tasks = [t for t in tasks if t.get("id", 0) > after_id]

    running = [t for t in tasks if t.get("status") == "running"]
    if running:
        return min(running, key=lambda t: t.get("id", 0))

    queued = [t for t in tasks if t.get("status") == "queued"]
    if queued:
        return min(queued, key=lambda t: t.get("id", 0))

    return None


def _stream_task(
    app_dir: str,
    app_name: str,
    task_id: int,
    fd: int | None,
    follow_all: bool = False,
) -> tuple[int, bool]:
    """
    Usage:

    - Streams logs and progress for a single task until completion or detachment

    Requires:

    - ``app_dir``:
        - Type: str
        - What: Root directory of CAVE app

    - ``app_name``:
        - Type: str
        - What: Name of CAVE app

    - ``task_id``:
        - Type: int
        - What: Incremental ID of task to stream

    - ``fd``:
        - Type: int | None
        - What: File descriptor for nonblocking key reads or None

    Optional:

    - ``follow_all``:
        - Type: bool
        - What: Whether attachment is in multi-task follow mode
        - Default: False

    Returns:

    - ``result``:
        - Type: tuple[int, bool]
        - What: Tuple containing (exit_code, detached)
    """
    task_info = get_task(app_dir, task_id)
    if not task_info:
        logger.error(f"Task #{task_id} not found.")
        return 1, False

    shown_queued_msg = False
    while True:
        task_info = get_task(app_dir, task_id) or task_info
        status = task_info.get("status")
        if status != "queued":
            break

        if not shown_queued_msg:
            print_section(f"Task #{task_id} Queued")
            print(
                "Waiting for previous tasks to finish... (Press Esc to detach, Ctrl+C to cancel)\n"
            )
            shown_queued_msg = True

        key = _read_nonblocking_key(fd)
        if key == "ESC":
            rejoin_cmd = (
                "cave task attach"
                if follow_all
                else f"cave task attach {task_id}"
            )
            print(f"\nDetached from task #{task_id}. Rejoin with: {rejoin_cmd}")
            return 0, True

        time.sleep(0.1)

    print_section(f"Task #{task_id} [{task_info.get('status', '').upper()}]")
    if task_info.get("status") == "running":
        print(
            f"Running: {task_info.get('command')} {' '.join(task_info.get('args', []))}"
        )
        print("Streaming output... (Press Esc to detach, Ctrl+C to cancel)\n")

    log_path = get_task_log_path(app_dir, task_id)
    log_file: IO[str] | None = None
    if os.path.exists(log_path):
        log_file = open(log_path, "r", encoding="utf-8", errors="replace")

    try:
        while True:
            if log_file is None and os.path.exists(log_path):
                log_file = open(
                    log_path, "r", encoding="utf-8", errors="replace"
                )

            if log_file:
                chunk = log_file.read(4096)
                if chunk:
                    sys.stdout.write(chunk)
                    sys.stdout.flush()

            key = _read_nonblocking_key(fd)
            if key == "ESC":
                rejoin_cmd = (
                    "cave task attach"
                    if follow_all
                    else f"cave task attach {task_id}"
                )
                print(
                    f"\nDetached from task #{task_id}. Rejoin with: {rejoin_cmd}"
                )
                return 0, True

            task_info = get_task(app_dir, task_id) or task_info
            status = task_info.get("status")
            if status in ("completed", "failed", "cancelled"):
                if log_file is None and os.path.exists(log_path):
                    log_file = open(
                        log_path, "r", encoding="utf-8", errors="replace"
                    )
                if log_file:
                    remaining = log_file.read()
                    if remaining:
                        sys.stdout.write(remaining)
                        sys.stdout.flush()
                exit_code = task_info.get("exit_code", 0)
                if status == "completed":
                    logger.success(f"Task #{task_id} finished successfully.")
                elif status == "cancelled":
                    logger.warn(f"Task #{task_id} was cancelled.")
                else:
                    logger.error(
                        f"Task #{task_id} failed with exit code {exit_code}."
                    )
                final_code = exit_code or (0 if status == "completed" else 1)
                return final_code, False

            time.sleep(0.05)
    finally:
        if log_file:
            log_file.close()


def attach_to_task(
    app_dir: str,
    app_name: str,
    task_id: int | None = None,
) -> int:
    """
    Usage:

    - Attaches to a queued or running task, streaming output with Esc to detach and Ctrl+C to cancel.
    - If task_id is specified, streams that task until it completes and exits.
    - If task_id is None, joins the current active task and follows subsequent tasks until all are finished.

    Requires:

    - ``app_dir``:
        - Type: str
        - What: Root directory of CAVE app

    - ``app_name``:
        - Type: str
        - What: CAVE application name

    Optional:

    - ``task_id``:
        - Type: int | None
        - What: Specific task ID to attach to, or None to follow all active tasks sequentially
        - Default: None

    Returns:

    - ``exit_code``:
        - Type: int
        - What: Exit code of the task(s), or 0 if detached
    """
    follow_all = task_id is None or task_id <= 0
    current_id: int | None = None

    if follow_all:
        first_task = _get_next_active_task(app_dir)
        if not first_task:
            tasks = list_tasks(app_dir)
            if not tasks:
                logger.info(f"No tasks recorded for '{app_name}'.")
            else:
                logger.info(f"No active tasks for '{app_name}'.")
            return 0
        current_id = first_task["id"]
    else:
        task_info = get_task(app_dir, task_id)
        if not task_info:
            logger.error(f"Task #{task_id} not found.")
            return 1
        current_id = task_id

    fd: int | None = None
    old_settings = None
    is_tty = sys.stdin.isatty()
    if sys.platform != "win32" and is_tty:
        try:
            import termios
            import tty

            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            tty.setcbreak(fd)
        except Exception:
            fd = None

    overall_exit_code = 0
    try:
        while current_id is not None:
            code, detached = _stream_task(
                app_dir=app_dir,
                app_name=app_name,
                task_id=current_id,
                fd=fd,
                follow_all=follow_all,
            )
            if detached:
                return 0
            if overall_exit_code == 0 and code != 0:
                overall_exit_code = code

            if not follow_all:
                break

            next_task = _get_next_active_task(app_dir, after_id=current_id)
            if not next_task:
                time.sleep(0.1)
                next_task = _get_next_active_task(app_dir, after_id=current_id)

            current_id = next_task["id"] if next_task else None

        return overall_exit_code

    except KeyboardInterrupt:
        if current_id is not None:
            cancel_task(app_dir, app_name, current_id)
            print(f"\nTask #{current_id} canceled.")
        return 130
    finally:
        if old_settings is not None and fd is not None:
            try:
                import termios

                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            except Exception:
                pass


def schedule_task(
    app_dir: str,
    app_name: str,
    command: list[str],
    detached: bool = False,
    docker_args: list[str] | None = None,
    display_command: str | None = None,
    extra_env: dict[str, str] | None = None,
) -> int:
    """
    Usage:

    - Registers and runs a task, either attaching interactively or detaching immediately

    Requires:

    - ``app_dir``:
        - Type: str
        - What: Root directory of CAVE app

    - ``app_name``:
        - Type: str
        - What: Name of CAVE app

    - ``command``:
        - Type: list[str]
        - What: Command tokens to execute

    Optional:

    - ``detached``:
        - Type: bool
        - What: If True, returns immediately without streaming output
        - Default: False

    - ``docker_args``:
        - Type: list[str] | None
        - What: Extra docker arguments
        - Default: None

    - ``display_command``:
        - Type: str | None
        - What: Command name to record in registry
        - Default: None

    - ``extra_env``:
        - Type: dict[str, str] | None
        - What: Extra environment variables for the task
        - Default: None

    Returns:

    - ``exit_code``:
        - Type: int
        - What: Exit code of task or 0 if detached
    """
    if not command:
        logger.error("No command specified to run in task server.")
        return 1

    cmd_name = display_command or command[0]
    cmd_args = command[1:]

    task_record = register_task(
        app_dir=app_dir,
        app_name=app_name,
        command=cmd_name,
        args=cmd_args,
        extra_env=extra_env,
        exec_command=command,
    )
    task_id = task_record["id"]

    runner_pid = spawn_task_runner(app_dir, app_name, task_id, docker_args)
    if runner_pid > 0:
        update_task_pid(app_dir, task_id, runner_pid)

    if detached:
        logger.success(
            f"Task #{task_id} queued in detached mode for '{app_name}'."
        )
        logger.info(f"Rejoin with: cave task attach {task_id}")
        return 0

    return attach_to_task(app_dir, app_name, task_id)


# Backward compatibility alias
run_task_sequence = schedule_task


def task(args: argparse.Namespace) -> None:
    """
    Usage:

    - Inspects, kills, attaches, and manages tasks and the task runner for a CAVE app

    Requires:

    - ``args``:
        - Type: argparse.Namespace
        - What: Parsed CLI arguments
    """
    app_dir, app_name = get_app()

    # Determine action from flags or remaining positional words
    task_action = getattr(args, "task_action", None)
    task_cmd = getattr(args, "task_cmd", []) or []
    kill_id = getattr(args, "kill_id", None) or getattr(args, "task_id", None)
    attach_id = getattr(args, "attach_id", None)
    detached = getattr(args, "detached", False)
    remaining = getattr(args, "remaining", []) or []
    docker_args_str = getattr(args, "docker_args", "") or ""
    extra_docker_args = shlex.split(docker_args_str) if docker_args_str else []

    action = getattr(args, "action", None)
    if task_action in ("start", "run"):
        action = "start"
    elif task_action in ("stop", "kill-server"):
        action = "stop"
    elif task_action in ("list", "ls"):
        if getattr(args, "list_all", False):
            action = "list-all"
        else:
            action = "list"
    elif task_action in ("list-all", "la"):
        action = "list-all"
    elif task_action in ("attach", "join", "log", "logs"):
        action = "attach"
        attach_id = getattr(args, "task_id", None)
    elif task_action in ("kill", "cancel"):
        action = "kill"
        kill_id = getattr(args, "task_id", None)
    elif task_action in ("kill-all", "cancel-all"):
        action = "kill-all"
    elif task_action in ("clean", "clear"):
        action = "clean"
    elif task_action == "reset":
        action = "reset"

    # Check explicit flags if not set by subparser
    if not action:
        if getattr(args, "list_all", False):
            action = "list-all"
        elif getattr(args, "list", False):
            action = "list"
        elif getattr(args, "clean", False):
            action = "clean"
        elif getattr(args, "kill_all", False):
            action = "kill-all"
        elif getattr(args, "reset", False):
            action = "reset"
        elif getattr(args, "stop", False):
            action = "stop"
        elif kill_id is not None:
            action = "kill"
        elif attach_id is not None:
            action = "attach"

    # Map positional subcommands if action not set by flag or subparser
    if not action and remaining:
        first = remaining[0].lower()
        if first in ("list-all", "ls-all", "la"):
            action = "list-all"
        elif first in ("list", "ls", "l"):
            action = "list"
        elif first in ("clean", "clear"):
            action = "clean"
        elif first in ("attach", "join", "log", "logs"):
            action = "attach"
            if len(remaining) > 1 and remaining[1].isdigit():
                attach_id = int(remaining[1])
        elif first in ("kill", "cancel"):
            action = "kill"
            if len(remaining) > 1 and remaining[1].isdigit():
                kill_id = int(remaining[1])
            else:
                logger.error("Task ID required for 'task kill'.")
                sys.exit(1)
        elif first in ("kill-all", "cancel-all"):
            action = "kill-all"
        elif first == "reset":
            action = "reset"
        elif first in ("stop", "kill-server"):
            action = "stop"
        elif first in ("start", "run"):
            action = "start"
            task_cmd = remaining[1:]
        else:
            action = "start"
            task_cmd = remaining

    if action == "start" and not task_cmd and remaining:
        task_cmd = remaining

    if action == "list-all":
        limit = getattr(args, "limit", None)
        tasks = (
            list_tasks(app_dir, limit=limit)
            if limit is not None
            else list_tasks(app_dir)
        )
        _print_tasks_table(tasks, app_name, only_active=False)
        return

    if action == "list":
        limit = getattr(args, "limit", None)
        tasks = [
            t
            for t in list_tasks(app_dir)
            if t.get("status") in ("queued", "running")
        ]
        if limit is not None and limit > 0:
            tasks = tasks[-limit:]
        _print_tasks_table(tasks, app_name, only_active=True)
        return

    if action == "clean":
        removed = clean_completed_tasks(app_dir, keep_last_n=0)
        logger.success(f"Cleaned {removed} completed task(s) for '{app_name}'.")
        return

    if action == "attach":
        code = attach_to_task(
            app_dir,
            app_name,
            attach_id if attach_id and attach_id > 0 else None,
        )
        if code != 0:
            sys.exit(code)
        return

    if action == "kill":
        if kill_id is None:
            logger.error("Task ID required for 'task kill'.")
            sys.exit(1)
        success = cancel_task(app_dir, app_name, kill_id)
        if success:
            logger.success(f"Task #{kill_id} canceled for '{app_name}'.")
        else:
            logger.warn(
                f"Task #{kill_id} not found or already completed for '{app_name}'."
            )
        return

    if action == "kill-all":
        count = cancel_all_tasks(app_dir, app_name)
        if count > 0:
            logger.success(f"Canceled {count} active task(s) for '{app_name}'.")
        else:
            logger.info(f"No active tasks to cancel for '{app_name}'.")
        return

    if action == "reset":
        reset_task_server(app_dir, app_name, extra_docker_args)
        clean_completed_tasks(app_dir)
        logger.success(f"Task server reset complete for '{app_name}'.")
        return

    if action == "stop":
        if is_task_server_running(app_name):
            stop_task_server(app_name, app_dir=app_dir)
            logger.success(f"Task server stopped for '{app_name}'.")
        else:
            logger.info(f"Task server for '{app_name}' is already stopped.")
        return

    if action == "start":
        if not task_cmd:
            logger.error("No command or target file specified for task.")
            sys.exit(1)
        exit_code = schedule_task(
            app_dir=app_dir,
            app_name=app_name,
            command=task_cmd,
            detached=detached,
            docker_args=extra_docker_args,
        )
        if exit_code != 0:
            sys.exit(exit_code)
        return

    # Default action if no flags/subcommands: list active tasks
    limit = getattr(args, "limit", None)
    tasks = [
        t
        for t in list_tasks(app_dir)
        if t.get("status") in ("queued", "running")
    ]
    if limit is not None and limit > 0:
        tasks = tasks[-limit:]
    _print_tasks_table(tasks, app_name, only_active=True)
