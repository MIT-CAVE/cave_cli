import hashlib
import json
import os
import sys
import threading
import time
from pathlib import Path
from types import TracebackType
from typing import IO, Any

if sys.platform != "win32":
    import fcntl
else:
    import msvcrt

from cave_cli.utils.cache import get_cache_dir
from cave_cli.utils.display import step_done, step_fail, step_start
from cave_cli.utils.git import get_git_common_dir, get_project_name
from cave_cli.utils.logger import logger
from cave_cli.utils.subprocess import run


class TaskQueueCancelledError(Exception):
    """
    Usage:

    - Raised when a queued task is canceled prior to or during execution
    """

    __test__ = False


def is_process_alive(pid: int) -> bool:
    """
    Usage:

    - Checks if a process with the given PID is currently alive

    Requires:

    - ``pid``:
        - Type: int
        - What: Process ID to check

    Returns:

    - ``alive``:
        - Type: bool
        - What: True if process is running, False otherwise
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def get_task_lock_path(app_dir: str) -> str:
    """
    Usage:

    - Resolves the lock file path used to serialize tasks for a CAVE project

    Requires:

    - ``app_dir``:
        - Type: str
        - What: The root directory of the CAVE application

    Returns:

    - ``lock_path``:
        - Type: str
        - What: The absolute path to the lock file
    """
    common_dir = get_git_common_dir(app_dir)
    if (
        common_dir
        and os.path.isdir(common_dir)
        and os.access(common_dir, os.W_OK)
    ):
        return os.path.join(common_dir, "cave_task.lock")

    if common_dir:
        project_root = str(Path(common_dir).parent.resolve())
    else:
        project_root = str(Path(app_dir).resolve())

    project_hash = hashlib.sha256(project_root.encode("utf-8")).hexdigest()[:16]
    return os.path.join(get_cache_dir(), f"task_queue_{project_hash}.lock")


def get_task_cancel_path(app_dir: str) -> str:
    """
    Usage:

    - Resolves the cancellation file path used to signal task queue cancellation

    Requires:

    - ``app_dir``:
        - Type: str
        - What: The root directory of the CAVE application

    Returns:

    - ``cancel_path``:
        - Type: str
        - What: The absolute path to the cancellation marker file
    """
    lock_path = get_task_lock_path(app_dir)
    if lock_path.endswith("cave_task.lock"):
        return os.path.join(os.path.dirname(lock_path), "cave_task_cancel.json")
    return lock_path.replace(".lock", "_cancel.json")


def get_task_registry_lock_path(app_dir: str) -> str:
    """
    Usage:

    - Resolves the lock file path used to serialize task registry access

    Requires:

    - ``app_dir``:
        - Type: str
        - What: The root directory of the CAVE application

    Returns:

    - ``lock_path``:
        - Type: str
        - What: The absolute path to the task registry lock file
    """
    lock_path = get_task_lock_path(app_dir)
    if lock_path.endswith("cave_task.lock"):
        return os.path.join(
            os.path.dirname(lock_path), "cave_task_registry.lock"
        )
    return lock_path.replace(".lock", "_registry.lock")


class TaskRegistryLock:
    """
    Usage:

    - Re-entrant context manager providing synchronization for task registry operations

    Requires:

    - ``app_dir``:
        - Type: str
        - What: The root directory of the CAVE application

    Optional:

    - ``timeout``:
        - Type: float
        - What: Maximum seconds to wait for registry lock acquisition before proceeding
        - Default: 10.0
    """

    _thread_locks: dict[str, threading.RLock] = {}
    _file_depths: dict[str, int] = {}
    _file_objs: dict[str, IO[str]] = {}
    _meta_lock = threading.Lock()

    def __init__(self, app_dir: str, timeout: float = 10.0) -> None:
        self.lock_path = get_task_registry_lock_path(app_dir)
        self.timeout = timeout
        with TaskRegistryLock._meta_lock:
            if self.lock_path not in TaskRegistryLock._thread_locks:
                TaskRegistryLock._thread_locks[self.lock_path] = (
                    threading.RLock()
                )
            self._rlock = TaskRegistryLock._thread_locks[self.lock_path]

    def acquire(self) -> None:
        acquired = self._rlock.acquire(timeout=self.timeout)
        if not acquired:
            logger.debug(f"Thread lock timed out on {self.lock_path}")
            return

        with TaskRegistryLock._meta_lock:
            depth = TaskRegistryLock._file_depths.get(self.lock_path, 0)
            if depth > 0:
                TaskRegistryLock._file_depths[self.lock_path] = depth + 1
                return

            os.makedirs(os.path.dirname(self.lock_path), exist_ok=True)
            file_obj = open(self.lock_path, "a+", encoding="utf-8")
            start = time.time()
            while True:
                try:
                    if sys.platform == "win32":
                        file_obj.seek(0)
                        if os.fstat(file_obj.fileno()).st_size == 0:
                            file_obj.write(" ")
                            file_obj.flush()
                        file_obj.seek(0)
                        msvcrt.locking(file_obj.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    else:
                        fcntl.flock(
                            file_obj.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB
                        )
                        break
                except (BlockingIOError, OSError):
                    if (time.time() - start) >= self.timeout:
                        logger.debug(
                            f"Registry lock timed out on {self.lock_path}, proceeding"
                        )
                        break
                    time.sleep(0.01)

            TaskRegistryLock._file_objs[self.lock_path] = file_obj
            TaskRegistryLock._file_depths[self.lock_path] = 1

    def release(self) -> None:
        with TaskRegistryLock._meta_lock:
            depth = TaskRegistryLock._file_depths.get(self.lock_path, 0)
            if depth > 1:
                TaskRegistryLock._file_depths[self.lock_path] = depth - 1
            elif depth == 1:
                file_obj = TaskRegistryLock._file_objs.pop(self.lock_path, None)
                TaskRegistryLock._file_depths.pop(self.lock_path, None)
                if file_obj:
                    try:
                        if sys.platform == "win32":
                            file_obj.seek(0)
                            msvcrt.locking(
                                file_obj.fileno(), msvcrt.LK_UNLCK, 1
                            )
                        else:
                            fcntl.flock(file_obj.fileno(), fcntl.LOCK_UN)
                    except Exception:
                        pass
                    try:
                        file_obj.close()
                    except Exception:
                        pass

        try:
            self._rlock.release()
        except RuntimeError:
            pass

    def __enter__(self) -> "TaskRegistryLock":
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.release()


def get_task_registry_path(app_dir: str) -> str:
    """
    Usage:

    - Resolves the JSON registry path used to track tasks for a CAVE project

    Requires:

    - ``app_dir``:
        - Type: str
        - What: The root directory of the CAVE application

    Returns:

    - ``path``:
        - Type: str
        - What: The absolute path to the task registry JSON file
    """
    lock_path = get_task_lock_path(app_dir)
    if lock_path.endswith("cave_task.lock"):
        return os.path.join(os.path.dirname(lock_path), "cave_tasks.json")
    return lock_path.replace(".lock", "_tasks.json")


def _read_registry_unlocked(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        return {"next_id": 1, "tasks": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return {"next_id": 1, "tasks": []}
            data.setdefault("next_id", 1)
            data.setdefault("tasks", [])
            return data
    except Exception:
        return {"next_id": 1, "tasks": []}


def _write_registry_unlocked(path: str, data: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp_path = f"{path}.tmp.{os.getpid()}"
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(temp_path, path)
    except Exception as exc:
        logger.debug(f"Failed to write task registry: {exc}")
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


DEFAULT_TASK_HISTORY_LIMIT: int = 50
DEFAULT_RUN_LOG_LIMIT: int = 500


def get_task_history_limit(app_dir: str | None = None) -> int:
    """
    Usage:

    - Resolves the task history retention limit from environment or configuration

    Optional:

    - ``app_dir``:
        - Type: str | None
        - What: Root directory of CAVE app
        - Default: None

    Returns:

    - ``limit``:
        - Type: int
        - What: Maximum number of task history records and logs to retain
    """
    env_val = os.environ.get("CAVE_TASK_HISTORY_LIMIT") or os.environ.get(
        "TASK_HISTORY_LIMIT"
    )
    if env_val and env_val.isdigit():
        return max(1, int(env_val))

    if app_dir:
        env_file = os.path.join(app_dir, ".env")
        if os.path.isfile(env_file):
            try:
                from cave_cli.utils.env import parse_env

                parsed = parse_env(env_file)
                val = parsed.get("CAVE_TASK_HISTORY_LIMIT") or parsed.get(
                    "TASK_HISTORY_LIMIT"
                )
                if val and str(val).isdigit():
                    return max(1, int(val))
            except Exception:
                pass

    try:
        from cave_cli.utils.cache import get_setting

        setting_val = get_setting("task_history_limit")
        if setting_val and str(setting_val).isdigit():
            return max(1, int(setting_val))
    except Exception:
        pass

    return DEFAULT_TASK_HISTORY_LIMIT


def get_run_log_limit(app_dir: str | None = None) -> int:
    """
    Usage:

    - Resolves the live server run log line limit from environment or configuration

    Optional:

    - ``app_dir``:
        - Type: str | None
        - What: Root directory of CAVE app
        - Default: None

    Returns:

    - ``limit``:
        - Type: int
        - What: Maximum number of server log lines to maintain in run.log
    """
    env_val = os.environ.get("CAVE_RUN_LOG_LIMIT") or os.environ.get(
        "RUN_LOG_LIMIT"
    )
    if env_val and env_val.isdigit():
        return max(1, int(env_val))

    if app_dir:
        env_file = os.path.join(app_dir, ".env")
        if os.path.isfile(env_file):
            try:
                from cave_cli.utils.env import parse_env

                parsed = parse_env(env_file)
                val = parsed.get("CAVE_RUN_LOG_LIMIT") or parsed.get(
                    "RUN_LOG_LIMIT"
                )
                if val and str(val).isdigit():
                    return max(1, int(val))
            except Exception:
                pass

    try:
        from cave_cli.utils.cache import get_setting

        setting_val = get_setting("run_log_limit")
        if setting_val and str(setting_val).isdigit():
            return max(1, int(setting_val))
    except Exception:
        pass

    return DEFAULT_RUN_LOG_LIMIT


def get_run_log_path(app_dir: str) -> str:
    """
    Usage:

    - Resolves the log file path for live cave run server logs

    Requires:

    - ``app_dir``:
        - Type: str
        - What: The root directory of the CAVE application

    Returns:

    - ``path``:
        - Type: str
        - What: Absolute path to the run.log file
    """
    log_dir = get_task_log_dir(app_dir)
    return os.path.join(log_dir, "run.log")


def prune_stale_tasks(app_dir: str, locked: bool = False) -> None:
    """
    Usage:

    - Scans active tasks and marks dead processes as failed

    Requires:

    - ``app_dir``:
        - Type: str
        - What: The root directory of the CAVE application

    Optional:

    - ``locked``:
        - Type: bool
        - What: Whether the registry lock is already held
        - Default: False
    """
    registry_path = get_task_registry_path(app_dir)
    data = _read_registry_unlocked(registry_path)
    has_active = any(
        t.get("status") in ("queued", "running") for t in data.get("tasks", [])
    )
    if not has_active:
        return

    def _do_prune() -> None:
        data = _read_registry_unlocked(registry_path)
        modified = False
        now = time.time()
        for task in data.get("tasks", []):
            if task.get("status") in ("queued", "running"):
                pid = task.get("pid", 0)
                if pid > 0 and not is_process_alive(pid):
                    task["status"] = "failed"
                    task["ended_at"] = now
                    modified = True
                elif pid <= 0 and (now - (task.get("created_at") or 0)) >= 30.0:
                    task["status"] = "failed"
                    task["ended_at"] = now
                    modified = True
        if modified:
            _write_registry_unlocked(registry_path, data)

    if locked:
        _do_prune()
    else:
        with TaskRegistryLock(app_dir):
            _do_prune()


def prune_task_history(
    app_dir: str, limit: int | None = None, locked: bool = False
) -> int:
    """
    Usage:

    - Prunes completed tasks exceeding the retention limit and deletes their log files

    Requires:

    - ``app_dir``:
        - Type: str
        - What: The root directory of the CAVE application

    Optional:

    - ``limit``:
        - Type: int | None
        - What: Maximum completed tasks to keep (defaults to configured history limit)
        - Default: None

    - ``locked``:
        - Type: bool
        - What: Whether the registry lock is already held
        - Default: False

    Returns:

    - ``removed_count``:
        - Type: int
        - What: Number of tasks pruned
    """
    max_history = (
        limit if limit is not None else get_task_history_limit(app_dir)
    )

    def _do_prune() -> int:
        registry_path = get_task_registry_path(app_dir)
        data = _read_registry_unlocked(registry_path)
        tasks = data.get("tasks", [])
        if not tasks:
            return 0

        active_tasks = [
            t for t in tasks if t.get("status") in ("queued", "running")
        ]
        completed_tasks = [
            t for t in tasks if t.get("status") not in ("queued", "running")
        ]

        if len(completed_tasks) <= max_history:
            return 0

        to_prune = (
            completed_tasks[:-max_history]
            if max_history > 0
            else completed_tasks
        )
        to_keep_completed = (
            completed_tasks[-max_history:] if max_history > 0 else []
        )

        for t in to_prune:
            log_path = get_task_log_path(app_dir, t.get("id", 0))
            try:
                if os.path.exists(log_path):
                    os.remove(log_path)
            except Exception:
                pass

        keep_ids = {t["id"] for t in active_tasks} | {
            t["id"] for t in to_keep_completed
        }
        retained = [t for t in tasks if t.get("id") in keep_ids]
        data["tasks"] = retained
        _write_registry_unlocked(registry_path, data)
        return len(to_prune)

    if locked:
        return _do_prune()
    with TaskRegistryLock(app_dir):
        return _do_prune()


def register_task(
    app_dir: str,
    app_name: str,
    command: str,
    args: list[str] | None = None,
    extra_env: dict[str, str] | None = None,
    exec_command: list[str] | None = None,
) -> dict[str, Any]:
    """
    Usage:

    - Registers a new task in the project registry with an incremental ID

    Requires:

    - ``app_dir``:
        - Type: str
        - What: The root directory of the CAVE application

    - ``app_name``:
        - Type: str
        - What: The name of the CAVE application

    - ``command``:
        - Type: str
        - What: Task command name (e.g. "test", "prettify")

    Optional:

    - ``args``:
        - Type: list[str] | None
        - What: Arguments passed to the command
        - Default: None

    - ``extra_env``:
        - Type: dict[str, str] | None
        - What: Extra environment variables for the process
        - Default: None

    - ``exec_command``:
        - Type: list[str] | None
        - What: Raw command to execute if different from command + args
        - Default: None

    Returns:

    - ``task``:
        - Type: dict[str, Any]
        - What: The registered task dictionary
    """
    with TaskRegistryLock(app_dir):
        registry_path = get_task_registry_path(app_dir)
        prune_stale_tasks(app_dir, locked=True)
        data = _read_registry_unlocked(registry_path)

        task_id = data.get("next_id", 1)
        data["next_id"] = task_id + 1

        # Remove any stale log file for this task ID
        log_path = get_task_log_path(app_dir, task_id)
        if os.path.exists(log_path):
            try:
                os.remove(log_path)
            except Exception:
                pass

        task = {
            "id": task_id,
            "app_name": app_name,
            "command": command,
            "args": args or [],
            "extra_env": extra_env or {},
            "exec_command": exec_command or ([command] + (args or [])),
            "pid": 0,
            "status": "queued",
            "created_at": time.time(),
            "started_at": None,
            "ended_at": None,
            "exit_code": None,
        }

        tasks = data.get("tasks", [])
        tasks.append(task)
        data["tasks"] = tasks

        _write_registry_unlocked(registry_path, data)
        prune_task_history(app_dir, locked=True)
        return task


def update_task_pid(app_dir: str, task_id: int, pid: int) -> None:
    """
    Usage:

    - Updates the process ID for a task record

    Requires:

    - ``app_dir``:
        - Type: str
        - What: The root directory of the CAVE application

    - ``task_id``:
        - Type: int
        - What: Incremental ID of the task

    - ``pid``:
        - Type: int
        - What: OS process ID of the task runner
    """
    with TaskRegistryLock(app_dir):
        registry_path = get_task_registry_path(app_dir)
        data = _read_registry_unlocked(registry_path)
        for task in data.get("tasks", []):
            if task.get("id") == task_id:
                task["pid"] = pid
                break
        _write_registry_unlocked(registry_path, data)


def get_task_log_dir(app_dir: str) -> str:
    """
    Usage:

    - Resolves the directory path used to store task log files

    Requires:

    - ``app_dir``:
        - Type: str
        - What: The root directory of the CAVE application

    Returns:

    - ``log_dir``:
        - Type: str
        - What: Absolute path to the directory containing task log files
    """
    common_dir = get_git_common_dir(app_dir)
    if (
        common_dir
        and os.path.isdir(common_dir)
        and os.access(common_dir, os.W_OK)
    ):
        log_dir = os.path.join(common_dir, "cave_tasks")
    elif common_dir:
        project_root = str(Path(common_dir).parent.resolve())
        project_hash = hashlib.sha256(project_root.encode("utf-8")).hexdigest()[
            :16
        ]
        log_dir = os.path.join(get_cache_dir(), "tasks", project_hash)
    else:
        project_root = str(Path(app_dir).resolve())
        project_hash = hashlib.sha256(project_root.encode("utf-8")).hexdigest()[
            :16
        ]
        log_dir = os.path.join(get_cache_dir(), "tasks", project_hash)
    os.makedirs(log_dir, exist_ok=True)
    return log_dir


def clean_all_task_logs(app_dir: str) -> int:
    """
    Usage:

    - Removes all task log files from disk for a CAVE project

    Requires:

    - ``app_dir``:
        - Type: str
        - What: The root directory of the CAVE application

    Returns:

    - ``count``:
        - Type: int
        - What: Number of log files deleted
    """
    log_dir = get_task_log_dir(app_dir)
    if not os.path.isdir(log_dir):
        return 0
    count = 0
    for entry in os.listdir(log_dir):
        if entry.startswith("task_") and entry.endswith(".log"):
            try:
                os.remove(os.path.join(log_dir, entry))
                count += 1
            except Exception:
                pass
    return count


def get_task_log_path(app_dir: str, task_id: int) -> str:
    """
    Usage:

    - Resolves the log file path for a specific task

    Requires:

    - ``app_dir``:
        - Type: str
        - What: The root directory of the CAVE application

    - ``task_id``:
        - Type: int
        - What: Incremental ID of the task

    Returns:

    - ``path``:
        - Type: str
        - What: Absolute path to the task log file
    """
    log_dir = get_task_log_dir(app_dir)
    return os.path.join(log_dir, f"task_{task_id}.log")


def clean_completed_tasks(app_dir: str, keep_last_n: int = 0) -> int:
    """
    Usage:

    - Removes completed tasks and their log files, optionally retaining the last N

    Requires:

    - ``app_dir``:
        - Type: str
        - What: The root directory of the CAVE application

    Optional:

    - ``keep_last_n``:
        - Type: int
        - What: Number of recent completed tasks to retain (default: 0 to clean all)
        - Default: 0

    Returns:

    - ``removed_count``:
        - Type: int
        - What: Number of cleaned tasks
    """
    return prune_task_history(app_dir, limit=keep_last_n)


def update_task_status(
    app_dir: str,
    task_id: int,
    status: str,
    exit_code: int | None = None,
) -> None:
    """
    Usage:

    - Updates the status and timestamps of a task in the registry

    Requires:

    - ``app_dir``:
        - Type: str
        - What: The root directory of the CAVE application

    - ``task_id``:
        - Type: int
        - What: Incremental ID of the task

    - ``status``:
        - Type: str
        - What: New status ("queued", "running", "completed", "cancelled", "failed")

    Optional:

    - ``exit_code``:
        - Type: int | None
        - What: Process exit code if completed or failed
        - Default: None
    """
    with TaskRegistryLock(app_dir):
        registry_path = get_task_registry_path(app_dir)
        data = _read_registry_unlocked(registry_path)
        for task in data.get("tasks", []):
            if task.get("id") == task_id:
                task["status"] = status
                if status == "running" and not task.get("started_at"):
                    task["started_at"] = time.time()
                elif status in ("completed", "cancelled", "failed"):
                    task["ended_at"] = time.time()
                    if exit_code is not None:
                        task["exit_code"] = exit_code
                break
        _write_registry_unlocked(registry_path, data)


def get_task(app_dir: str, task_id: int) -> dict[str, Any] | None:
    """
    Usage:

    - Retrieves a task record by its incremental ID

    Requires:

    - ``app_dir``:
        - Type: str
        - What: The root directory of the CAVE application

    - ``task_id``:
        - Type: int
        - What: Incremental ID of the task

    Returns:

    - ``task``:
        - Type: dict[str, Any] | None
        - What: The task dictionary or None if not found
    """
    registry_path = get_task_registry_path(app_dir)
    data = _read_registry_unlocked(registry_path)
    for task in data.get("tasks", []):
        if task.get("id") == task_id:
            return task
    return None


def list_tasks(app_dir: str, limit: int | None = None) -> list[dict[str, Any]]:
    """
    Usage:

    - Lists recorded tasks for a CAVE project, optionally limited to the most recent N

    Requires:

    - ``app_dir``:
        - Type: str
        - What: The root directory of the CAVE application

    Optional:

    - ``limit``:
        - Type: int | None
        - What: Maximum number of recent tasks to return
        - Default: None (returns all recorded tasks up to history limit)

    Returns:

    - ``tasks``:
        - Type: list[dict[str, Any]]
        - What: List of task records
    """
    prune_stale_tasks(app_dir)
    registry_path = get_task_registry_path(app_dir)
    data = _read_registry_unlocked(registry_path)
    tasks = data.get("tasks", [])
    if limit is not None and limit > 0:
        return tasks[-limit:]
    return tasks


def cancel_task(app_dir: str, app_name: str, task_id: int) -> bool:
    """
    Usage:

    - Cancels a specific task by its incremental ID

    Requires:

    - ``app_dir``:
        - Type: str
        - What: The root directory of the CAVE application

    - ``app_name``:
        - Type: str
        - What: The name of the CAVE application

    - ``task_id``:
        - Type: int
        - What: Incremental ID of the task to cancel

    Returns:

    - ``cancelled``:
        - Type: bool
        - What: True if task was found and marked cancelled, False otherwise
    """
    with TaskRegistryLock(app_dir):
        task = get_task(app_dir, task_id)
        if not task:
            return False

        status = task.get("status")
        if status in ("completed", "cancelled", "failed"):
            return False

        update_task_status(app_dir, task_id, "cancelled", exit_code=130)

        # Terminate background runner process if alive
        pid = task.get("pid", 0)
        if pid > 0 and pid != os.getpid() and is_process_alive(pid):
            try:
                os.kill(pid, 15)
            except OSError:
                pass

        # If the task was actively running, terminate container execution cleanly
        if status == "running":
            run(["docker", "rm", "-f", f"{app_name}_task_django"])
            run(["docker", "rm", "-f", f"{app_name}_test_django"])

        return True


def cancel_all_tasks(app_dir: str, app_name: str) -> int:
    """
    Usage:

    - Cancels all running and queued tasks for a CAVE application

    Requires:

    - ``app_dir``:
        - Type: str
        - What: The root directory of the CAVE application

    - ``app_name``:
        - Type: str
        - What: The name of the CAVE application

    Returns:

    - ``count``:
        - Type: int
        - What: Number of tasks that were cancelled
    """
    with TaskRegistryLock(app_dir):
        tasks = list_tasks(app_dir)
        cancelled_count = 0
        had_running = False

        for task in tasks:
            if task.get("status") in ("queued", "running"):
                if task.get("status") == "running":
                    had_running = True
                update_task_status(
                    app_dir, task.get("id"), "cancelled", exit_code=130
                )
                cancelled_count += 1

        cancel_path = get_task_cancel_path(app_dir)
        os.makedirs(os.path.dirname(cancel_path), exist_ok=True)
        try:
            with open(cancel_path, "w", encoding="utf-8") as f:
                json.dump({"cancelled_at": time.time()}, f)
        except Exception:
            pass

        if had_running or cancelled_count > 0:
            run(["docker", "rm", "-f", f"{app_name}_task_django"])
            run(["docker", "rm", "-f", f"{app_name}_test_django"])

        return cancelled_count


def reset_task_registry(app_dir: str) -> None:
    """
    Usage:

    - Resets the task registry and ID counter back to 1 and cleans all logs

    Requires:

    - ``app_dir``:
        - Type: str
        - What: The root directory of the CAVE application
    """
    with TaskRegistryLock(app_dir):
        clean_all_task_logs(app_dir)
        registry_path = get_task_registry_path(app_dir)
        _write_registry_unlocked(registry_path, {"next_id": 1, "tasks": []})


class TaskQueueLock:
    """
    Usage:

    - Context manager to serialize and track tasks across processes and worktrees

    Requires:

    - ``app_dir``:
        - Type: str
        - What: The root directory of the CAVE application

    - ``app_name``:
        - Type: str
        - What: The name of the CAVE application

    Optional:

    - ``command``:
        - Type: str
        - What: Name of task command (e.g. "test", "prettify")
        - Default: "task"

    - ``command_args``:
        - Type: list[str] | None
        - What: Arguments passed to the command
        - Default: None

    - ``timeout``:
        - Type: float | None
        - What: Maximum seconds to wait for lock acquisition before raising TimeoutError
        - Default: None (waits indefinitely)
    """

    __test__ = False

    def __init__(
        self,
        app_dir: str,
        app_name: str,
        command: str = "task",
        command_args: list[str] | None = None,
        timeout: float | None = None,
        task_id: int | None = None,
        register: bool = True,
    ) -> None:
        self.app_dir = app_dir
        self.app_name = app_name
        self.command = command
        self.command_args = command_args or []
        self.timeout = timeout
        self.lock_path = get_task_lock_path(app_dir)
        self.cancel_path = get_task_cancel_path(app_dir)
        self.enqueue_time = time.time()
        self.file_obj: IO[str] | None = None
        self._acquired: bool = False
        self._was_queued: bool = False
        if task_id is not None:
            self.task_id = task_id
            self.task = get_task(app_dir, task_id) or {}
        elif register:
            self.task = register_task(
                app_dir, app_name, command, self.command_args
            )
            self.task_id = self.task["id"]
        else:
            self.task = None
            self.task_id = None

    def _is_cancelled(self) -> bool:
        if self.task_id is None:
            return False
        task = get_task(self.app_dir, self.task_id)
        if task and task.get("status") == "cancelled":
            return True
        if os.path.exists(self.cancel_path):
            try:
                with open(self.cancel_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    cancelled_at = data.get("cancelled_at", 0)
                    return cancelled_at >= self.enqueue_time
            except Exception:
                pass
        return False

    def _try_acquire_nonblocking(self) -> bool:
        if not self.file_obj:
            return False

        if sys.platform == "win32":
            self.file_obj.seek(0)
            if os.fstat(self.file_obj.fileno()).st_size == 0:
                self.file_obj.write(" ")
                self.file_obj.flush()
            self.file_obj.seek(0)
            try:
                msvcrt.locking(self.file_obj.fileno(), msvcrt.LK_NBLCK, 1)
                return True
            except OSError:
                return False
        else:
            try:
                fcntl.flock(
                    self.file_obj.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB
                )
                return True
            except (BlockingIOError, OSError):
                return False

    def acquire(self) -> None:
        """
        Usage:

        - Acquires the exclusive task lock, waiting in the queue if necessary
        """
        if self._is_cancelled():
            raise TaskQueueCancelledError(
                f"Task #{self.task_id} was canceled before starting"
            )

        os.makedirs(os.path.dirname(self.lock_path), exist_ok=True)
        self.file_obj = open(self.lock_path, "a+", encoding="utf-8")

        if self._try_acquire_nonblocking():
            if self._is_cancelled():
                self.release()
                raise TaskQueueCancelledError(
                    f"Task #{self.task_id} was canceled"
                )
            self._acquired = True
            if self.task_id is not None:
                update_task_status(self.app_dir, self.task_id, "running")
            return

        self._was_queued = True
        project_name = get_project_name(self.app_dir) or self.app_name
        if self.task_id is not None:
            label = (
                f"Waiting for running task to finish [Task #{self.task_id}] "
                f"({project_name})"
            )
        else:
            label = f"Waiting for running task to finish ({project_name})"
        step_start(label)
        logger.debug(
            f"Lock request on {self.lock_path} for '{self.app_name}' queued"
        )

        start_time = time.time()
        try:
            while not self._acquired:
                if self._try_acquire_nonblocking():
                    if self._is_cancelled():
                        step_fail(label, "Canceled by user")
                        self.release()
                        raise TaskQueueCancelledError(
                            f"Task #{self.task_id} was canceled"
                        )
                    self._acquired = True
                    if self.task_id is not None:
                        update_task_status(
                            self.app_dir, self.task_id, "running"
                        )
                    break

                if self._is_cancelled():
                    step_fail(label, "Canceled by user")
                    self.release()
                    raise TaskQueueCancelledError(
                        f"Task #{self.task_id} was canceled"
                    )

                if (
                    self.timeout is not None
                    and (time.time() - start_time) >= self.timeout
                ):
                    step_fail(label, "Timed out waiting for task slot")
                    self.release()
                    raise TimeoutError(
                        f"Timed out waiting for task lock on {self.lock_path}"
                    )

                time.sleep(0.2)
        except KeyboardInterrupt:
            step_fail(label, "Canceled by user")
            if self.task_id is not None:
                update_task_status(
                    self.app_dir, self.task_id, "cancelled", exit_code=130
                )
            self.release()
            sys.exit(130)

        step_done(label)

    def release(self) -> None:
        """
        Usage:

        - Releases the task lock and closes the lock file
        """
        if self._acquired and self.file_obj:
            try:
                if sys.platform == "win32":
                    self.file_obj.seek(0)
                    msvcrt.locking(self.file_obj.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(self.file_obj.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            self._acquired = False

        if self.file_obj:
            try:
                self.file_obj.close()
            except Exception:
                pass
            self.file_obj = None

    def __enter__(self) -> "TaskQueueLock":
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        try:
            if self.task_id is None:
                return

            if exc_type is not None:
                if issubclass(exc_type, TaskQueueCancelledError):
                    update_task_status(
                        self.app_dir, self.task_id, "cancelled", exit_code=130
                    )
                elif issubclass(exc_type, SystemExit):
                    code = getattr(exc_val, "code", 1)
                    if code == 0:
                        update_task_status(
                            self.app_dir, self.task_id, "completed", exit_code=0
                        )
                    elif code == 130:
                        update_task_status(
                            self.app_dir,
                            self.task_id,
                            "cancelled",
                            exit_code=130,
                        )
                    else:
                        update_task_status(
                            self.app_dir,
                            self.task_id,
                            "failed",
                            exit_code=int(code) if isinstance(code, int) else 1,
                        )
                else:
                    update_task_status(
                        self.app_dir, self.task_id, "failed", exit_code=1
                    )
            else:
                task = get_task(self.app_dir, self.task_id)
                if not task or task.get("status") not in (
                    "completed",
                    "failed",
                    "cancelled",
                ):
                    update_task_status(
                        self.app_dir, self.task_id, "completed", exit_code=0
                    )
        finally:
            self.release()
