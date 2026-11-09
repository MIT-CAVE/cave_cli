import os
import subprocess
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from cave_cli.utils.task_queue import (
    TaskQueueCancelledError,
    TaskQueueLock,
    cancel_all_tasks,
    cancel_task,
    clean_completed_tasks,
    get_task,
    get_task_log_path,
    get_task_registry_path,
    is_process_alive,
    list_tasks,
    prune_stale_tasks,
    register_task,
    reset_task_registry,
    update_task_pid,
    update_task_status,
)


@pytest.fixture
def fake_app_dir(tmp_path: Path):
    app_dir = tmp_path / "sample_app"
    app_dir.mkdir()
    path_str = str(app_dir)
    reset_task_registry(path_str)
    return path_str


class TestTaskQueueRegistry:
    def test_register_and_incremental_ids(self, fake_app_dir):
        t1 = register_task(fake_app_dir, "sample_app", "test", ["arg1"])
        t2 = register_task(fake_app_dir, "sample_app", "prettify", [])
        t3 = register_task(fake_app_dir, "sample_app", "test", ["arg2"])

        assert t1["id"] == 1
        assert t2["id"] == 2
        assert t3["id"] == 3
        assert t1["status"] == "queued"
        assert t2["command"] == "prettify"

        tasks = list_tasks(fake_app_dir)
        assert len(tasks) == 3
        assert [t["id"] for t in tasks] == [1, 2, 3]

    def test_update_task_status(self, fake_app_dir):
        t = register_task(fake_app_dir, "sample_app", "test", [])
        update_task_status(fake_app_dir, t["id"], "running")

        retrieved = get_task(fake_app_dir, t["id"])
        assert retrieved is not None
        assert retrieved["status"] == "running"
        assert retrieved["started_at"] is not None

        update_task_status(fake_app_dir, t["id"], "completed", exit_code=0)
        retrieved = get_task(fake_app_dir, t["id"])
        assert retrieved["status"] == "completed"
        assert retrieved["exit_code"] == 0
        assert retrieved["ended_at"] is not None

    def test_cancel_queued_task(self, fake_app_dir):
        t1 = register_task(fake_app_dir, "sample_app", "test", [])
        t2 = register_task(fake_app_dir, "sample_app", "prettify", [])

        success = cancel_task(fake_app_dir, "sample_app", t1["id"])
        assert success is True

        assert get_task(fake_app_dir, t1["id"])["status"] == "cancelled"
        assert get_task(fake_app_dir, t2["id"])["status"] == "queued"

    @patch("cave_cli.utils.task_queue.run")
    def test_cancel_running_task(self, mock_run, fake_app_dir):
        t = register_task(fake_app_dir, "sample_app", "test", [])
        update_task_status(fake_app_dir, t["id"], "running")

        success = cancel_task(fake_app_dir, "sample_app", t["id"])
        assert success is True
        assert get_task(fake_app_dir, t["id"])["status"] == "cancelled"

        # Verifies containers were removed to terminate active process
        assert mock_run.call_count >= 1
        mock_run.assert_any_call(
            ["docker", "rm", "-f", "sample_app_task_django"]
        )

    @patch("cave_cli.utils.task_queue.run")
    def test_cancel_all_tasks(self, mock_run, fake_app_dir):
        register_task(fake_app_dir, "sample_app", "test", [])
        t2 = register_task(fake_app_dir, "sample_app", "prettify", [])
        update_task_status(fake_app_dir, t2["id"], "running")

        count = cancel_all_tasks(fake_app_dir, "sample_app")
        assert count == 2

        tasks = list_tasks(fake_app_dir)
        for t in tasks:
            assert t["status"] == "cancelled"

    def test_prune_stale_tasks(self, fake_app_dir):
        t = register_task(fake_app_dir, "sample_app", "test", [])
        # Assign a non-existent PID
        reg_path = get_task_registry_path(fake_app_dir)
        from cave_cli.utils.task_queue import (
            _read_registry_unlocked,
            _write_registry_unlocked,
        )

        data = _read_registry_unlocked(reg_path)
        data["tasks"][0]["pid"] = 99999999
        _write_registry_unlocked(reg_path, data)

        prune_stale_tasks(fake_app_dir)
        retrieved = get_task(fake_app_dir, t["id"])
        assert retrieved["status"] == "failed"

    def test_reset_task_registry(self, fake_app_dir):
        register_task(fake_app_dir, "sample_app", "test", [])
        reset_task_registry(fake_app_dir)
        tasks = list_tasks(fake_app_dir)
        assert len(tasks) == 0

        # Next registered task starts with ID 1
        new_task = register_task(fake_app_dir, "sample_app", "test", [])
        assert new_task["id"] == 1

    def test_concurrent_task_registration(self, fake_app_dir):
        from concurrent.futures import ThreadPoolExecutor

        num_tasks = 20

        def register_one(idx):
            cmd = "prettify" if idx % 2 == 0 else "test"
            return register_task(fake_app_dir, "sample_app", cmd, [str(idx)])

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(register_one, range(num_tasks)))

        task_ids = [t["id"] for t in results]
        assert len(set(task_ids)) == num_tasks
        assert sorted(task_ids) == list(range(1, num_tasks + 1))

        all_tasks = list_tasks(fake_app_dir)
        assert len(all_tasks) == num_tasks

    def test_register_task_removes_stale_log(self, fake_app_dir):
        log_path = get_task_log_path(fake_app_dir, 1)
        Path(log_path).write_text("old stale output", encoding="utf-8")
        assert os.path.exists(log_path)

        t = register_task(fake_app_dir, "sample_app", "prettify", [])
        assert t["id"] == 1
        # Stale log should have been cleaned upon registration
        assert not os.path.exists(log_path)

    def test_reset_task_registry_cleans_all_logs(self, fake_app_dir):
        log1 = get_task_log_path(fake_app_dir, 1)
        log2 = get_task_log_path(fake_app_dir, 2)
        Path(log1).write_text("log 1", encoding="utf-8")
        Path(log2).write_text("log 2", encoding="utf-8")

        reset_task_registry(fake_app_dir)
        assert not os.path.exists(log1)
        assert not os.path.exists(log2)

    def test_task_registry_lock_reentrancy(self, fake_app_dir):
        from cave_cli.utils.task_queue import TaskRegistryLock

        with TaskRegistryLock(fake_app_dir):
            with TaskRegistryLock(fake_app_dir):
                t = register_task(fake_app_dir, "sample_app", "test", [])
                assert t["id"] == 1


class TestTaskQueueLock:
    def test_task_lock_success(self, fake_app_dir):
        with TaskQueueLock(fake_app_dir, "sample_app", command="test") as lock:
            assert lock.task_id == 1
            retrieved = get_task(fake_app_dir, 1)
            assert retrieved["status"] == "running"

        retrieved = get_task(fake_app_dir, 1)
        assert retrieved["status"] == "completed"

    def test_task_lock_no_register(self, fake_app_dir):
        with TaskQueueLock(fake_app_dir, "sample_app", register=False) as lock:
            assert lock.task_id is None
            assert lock.task is None

        tasks = list_tasks(fake_app_dir)
        assert len(tasks) == 0

    def test_task_lock_cancelled_prior(self, fake_app_dir):
        lock = TaskQueueLock(fake_app_dir, "sample_app", command="test")
        cancel_task(fake_app_dir, "sample_app", lock.task_id)

        with pytest.raises(TaskQueueCancelledError):
            with lock:
                pass

        retrieved = get_task(fake_app_dir, lock.task_id)
        assert retrieved["status"] == "cancelled"

    def test_task_log_path_and_cleanup(self, fake_app_dir):
        t1 = register_task(fake_app_dir, "sample_app", "test", [])
        t2 = register_task(fake_app_dir, "sample_app", "prettify", [])
        log1 = get_task_log_path(fake_app_dir, t1["id"])
        log2 = get_task_log_path(fake_app_dir, t2["id"])

        Path(log1).write_text("log output 1", encoding="utf-8")
        Path(log2).write_text("log output 2", encoding="utf-8")

        update_task_status(fake_app_dir, t1["id"], "completed", exit_code=0)
        # t2 remains queued

        update_task_pid(fake_app_dir, t1["id"], 99999)
        assert get_task(fake_app_dir, t1["id"])["pid"] == 99999

        # Clean completed tasks
        cleaned = clean_completed_tasks(fake_app_dir)
        assert cleaned == 1
        assert not os.path.exists(log1)
        assert os.path.exists(log2)

        tasks = list_tasks(fake_app_dir)
        assert len(tasks) == 1
        assert tasks[0]["id"] == t2["id"]

    def test_task_history_retention(self, fake_app_dir):
        from cave_cli.utils.task_queue import prune_task_history

        log_paths = {}
        for i in range(1, 11):
            t = register_task(fake_app_dir, "sample_app", f"cmd_{i}", [])
            update_task_status(fake_app_dir, t["id"], "completed", exit_code=0)
            lp = get_task_log_path(fake_app_dir, t["id"])
            Path(lp).write_text(f"log {i}", encoding="utf-8")
            log_paths[i] = lp

        pruned = prune_task_history(fake_app_dir, limit=3)
        assert pruned == 7

        remaining = list_tasks(fake_app_dir)
        assert len(remaining) == 3
        assert [t["id"] for t in remaining] == [8, 9, 10]

        # Old logs deleted, recent logs kept
        for i in range(1, 8):
            assert not os.path.exists(log_paths[i])
        for i in range(8, 11):
            assert os.path.exists(log_paths[i])

    def test_get_limits_and_paths(self, fake_app_dir, monkeypatch):
        from cave_cli.utils.task_queue import (
            DEFAULT_RUN_LOG_LIMIT,
            DEFAULT_TASK_HISTORY_LIMIT,
            get_run_log_limit,
            get_run_log_path,
            get_task_history_limit,
        )

        assert (
            get_task_history_limit(fake_app_dir) == DEFAULT_TASK_HISTORY_LIMIT
        )
        assert get_run_log_limit(fake_app_dir) == DEFAULT_RUN_LOG_LIMIT

        monkeypatch.setenv("CAVE_TASK_HISTORY_LIMIT", "25")
        monkeypatch.setenv("CAVE_RUN_LOG_LIMIT", "120")
        assert get_task_history_limit(fake_app_dir) == 25
        assert get_run_log_limit(fake_app_dir) == 120

        run_log = get_run_log_path(fake_app_dir)
        assert run_log.endswith("run.log")
