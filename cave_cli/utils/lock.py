import hashlib
import json
import os
import sys
import time
from pathlib import Path
from types import TracebackType
from typing import IO

if sys.platform != "win32":
    import fcntl
else:
    import msvcrt

from cave_cli.utils.cache import get_cache_dir
from cave_cli.utils.display import step_done, step_fail, step_start
from cave_cli.utils.git import get_git_common_dir, get_project_name
from cave_cli.utils.logger import logger
from cave_cli.utils.subprocess import run


class TestQueueCancelledError(Exception):
    """
    Usage:

    - Raised when a queued test is canceled prior to execution
    """

    __test__ = False


def get_test_lock_path(app_dir: str) -> str:
    """
    Usage:

    - Resolves the lock file path used to serialize tests for a CAVE project

    Requires:

    - ``app_dir``:
        - Type: str
        - What: The root directory of the CAVE application

    Returns:

    - ``lock_path``:
        - Type: str
        - What: The absolute path to the lock file

    Notes:

    - For git repositories (including all worktrees), uses ``cave_test.lock``
      inside the shared common git directory.
    - If the common git directory is not writable or if the app is not a git
      repository, falls back to a lock file in the cave_cli cache directory.
    """
    common_dir = get_git_common_dir(app_dir)
    if (
        common_dir
        and os.path.isdir(common_dir)
        and os.access(common_dir, os.W_OK)
    ):
        return os.path.join(common_dir, "cave_test.lock")

    if common_dir:
        project_root = str(Path(common_dir).parent.resolve())
    else:
        project_root = str(Path(app_dir).resolve())

    project_hash = hashlib.sha256(project_root.encode("utf-8")).hexdigest()[:16]
    return os.path.join(get_cache_dir(), f"test_queue_{project_hash}.lock")


def get_test_cancel_path(app_dir: str) -> str:
    """
    Usage:

    - Resolves the cancellation file path used to signal test queue cancellation

    Requires:

    - ``app_dir``:
        - Type: str
        - What: The root directory of the CAVE application

    Returns:

    - ``cancel_path``:
        - Type: str
        - What: The absolute path to the cancellation marker file
    """
    lock_path = get_test_lock_path(app_dir)
    if lock_path.endswith("cave_test.lock"):
        return os.path.join(os.path.dirname(lock_path), "cave_test_cancel.json")
    return lock_path.replace(".lock", "_cancel.json")


def cancel_test_queue(
    app_dir: str, app_name: str, kill_server: bool = False
) -> None:
    """
    Usage:

    - Cancels running and queued tests, and optionally kills the test server

    Requires:

    - ``app_dir``:
        - Type: str
        - What: The root directory of the CAVE application

    - ``app_name``:
        - Type: str
        - What: The name of the CAVE application

    Optional:

    - ``kill_server``:
        - Type: bool
        - What: Whether to also stop the persistent test server containers
        - Default: False
    """
    cancel_path = get_test_cancel_path(app_dir)
    os.makedirs(os.path.dirname(cancel_path), exist_ok=True)
    payload = {"cancelled_at": time.time(), "kill_server": kill_server}
    try:
        with open(cancel_path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
    except Exception as exc:
        logger.debug(f"Failed to write cancellation marker: {exc}")

    # Stop active test running inside test django container
    run(["docker", "stop", "-t", "1", f"{app_name}_test_django"])

    if kill_server:
        from cave_cli.utils.test_server import stop_test_server

        stop_test_server(app_name)


class TestQueueLock:
    """
    Usage:

    - Context manager to serialize and queue tests across processes and git worktrees

    Requires:

    - ``app_dir``:
        - Type: str
        - What: The root directory of the CAVE application

    - ``app_name``:
        - Type: str
        - What: The name of the CAVE application

    Optional:

    - ``timeout``:
        - Type: float | None
        - What: Maximum seconds to wait for lock acquisition before raising TimeoutError
        - Default: None (waits indefinitely)

    Notes:

    - Uses kernel-level advisory file locks (fcntl on Unix, msvcrt on Windows).
    - Locks are automatically released by the operating system if the process terminates or is killed.
    - If another test is currently running for the project, displays a step progress indicator
      while waiting in the queue.
    - Checks for test queue cancellation events and aborts cleanly.
    - For git repositories, locks against the shared common git directory so all worktrees
      queue behind each other.
    """

    __test__ = False

    def __init__(
        self, app_dir: str, app_name: str, timeout: float | None = None
    ) -> None:
        self.app_dir = app_dir
        self.app_name = app_name
        self.timeout = timeout
        self.lock_path = get_test_lock_path(app_dir)
        self.cancel_path = get_test_cancel_path(app_dir)
        self.enqueue_time = time.time()
        self.file_obj: IO[str] | None = None
        self._acquired: bool = False
        self._was_queued: bool = False

    def _is_cancelled(self) -> bool:
        """
        Usage:

        - Checks if a cancellation event occurred after this test was enqueued

        Returns:

        - ``cancelled``:
            - Type: bool
            - What: True if cancelled, False otherwise
        """
        if not os.path.exists(self.cancel_path):
            return False
        try:
            with open(self.cancel_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                cancelled_at = data.get("cancelled_at", 0)
                return cancelled_at >= self.enqueue_time
        except Exception:
            return False

    def _try_acquire_nonblocking(self) -> bool:
        """
        Usage:

        - Attempts to acquire the lock immediately without blocking

        Returns:

        - ``success``:
            - Type: bool
            - What: True if acquired, False otherwise
        """
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

        - Acquires the exclusive test queue lock, waiting if necessary
        """
        if self._is_cancelled():
            raise TestQueueCancelledError("Test was canceled before starting")

        os.makedirs(os.path.dirname(self.lock_path), exist_ok=True)
        self.file_obj = open(self.lock_path, "a+", encoding="utf-8")

        if self._try_acquire_nonblocking():
            if self._is_cancelled():
                self.release()
                raise TestQueueCancelledError("Test was canceled")
            self._acquired = True
            return

        self._was_queued = True
        project_name = get_project_name(self.app_dir) or self.app_name
        label = f"Waiting for running test to finish ({project_name})"
        step_start(label)
        logger.debug(
            f"Test for '{self.app_name}' queued on lock {self.lock_path}"
        )

        start_time = time.time()
        try:
            while not self._acquired:
                if self._try_acquire_nonblocking():
                    if self._is_cancelled():
                        step_fail(label, "Canceled by user")
                        self.release()
                        raise TestQueueCancelledError("Test was canceled")
                    self._acquired = True
                    break

                if self._is_cancelled():
                    step_fail(label, "Canceled by user")
                    self.release()
                    raise TestQueueCancelledError("Test was canceled")

                if (
                    self.timeout is not None
                    and (time.time() - start_time) >= self.timeout
                ):
                    step_fail(label, "Timed out waiting for test slot")
                    self.release()
                    raise TimeoutError(
                        f"Timed out waiting for test lock on {self.lock_path}"
                    )

                time.sleep(0.2)
        except KeyboardInterrupt:
            step_fail(label, "Canceled by user")
            self.release()
            sys.exit(130)

        step_done(label)

    def release(self) -> None:
        """
        Usage:

        - Releases the test queue lock and closes the lock file
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

    def __enter__(self) -> "TestQueueLock":
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.release()
