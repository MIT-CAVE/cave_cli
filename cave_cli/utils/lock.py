import os
import sys
import time

from cave_cli.utils.task_queue import (
    TaskQueueCancelledError,
    TaskQueueLock,
    cancel_all_tasks,
    get_task_lock_path,
)

# Backward-compatibility aliases
TestQueueCancelledError = TaskQueueCancelledError
TestQueueLock = TaskQueueLock
get_test_lock_path = get_task_lock_path


def get_test_cancel_path(app_dir: str) -> str:
    """
    Usage:

    - Legacy compatibility helper resolving task cancellation path
    """
    lock_path = get_task_lock_path(app_dir)
    if lock_path.endswith("cave_task.lock"):
        return os.path.join(os.path.dirname(lock_path), "cave_task_cancel.json")
    return lock_path.replace(".lock", "_cancel.json")


def cancel_test_queue(
    app_dir: str, app_name: str, kill_server: bool = False
) -> None:
    """
    Usage:

    - Cancels running and queued tasks, and optionally stops the task server
    """
    cancel_all_tasks(app_dir, app_name)
    if kill_server:
        try:
            from cave_cli.utils.task_server import stop_task_server

            stop_task_server(app_name)
        except ImportError:
            from cave_cli.utils.test_server import stop_test_server

            stop_test_server(app_name)
