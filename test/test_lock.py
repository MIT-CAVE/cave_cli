import os
import subprocess
import threading
import time
from pathlib import Path

import pytest

from cave_cli.utils.git import (
    get_git_common_dir,
    get_project_name,
    get_project_root,
)
from cave_cli.utils.lock import TestQueueLock, get_test_lock_path


@pytest.fixture
def git_project_with_worktree(tmp_path: Path):
    """
    Creates a temporary git repository with a linked worktree.
    Returns (main_repo_path, worktree_path).
    """
    main_repo = tmp_path / "main_project"
    main_repo.mkdir()
    subprocess.run(
        ["git", "init"], cwd=main_repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "initial commit"],
        cwd=main_repo,
        check=True,
        capture_output=True,
    )

    worktree = tmp_path / "worktree_project"
    subprocess.run(
        ["git", "worktree", "add", str(worktree), "-b", "feature"],
        cwd=main_repo,
        check=True,
        capture_output=True,
    )

    return main_repo, worktree


class TestGitHelpers:
    def test_git_common_dir_main_repo(self, git_project_with_worktree):
        main_repo, _ = git_project_with_worktree
        common_dir = get_git_common_dir(str(main_repo))
        assert common_dir is not None
        assert Path(common_dir).resolve() == (main_repo / ".git").resolve()

    def test_git_common_dir_worktree(self, git_project_with_worktree):
        main_repo, worktree = git_project_with_worktree
        common_dir = get_git_common_dir(str(worktree))
        assert common_dir is not None
        assert Path(common_dir).resolve() == (main_repo / ".git").resolve()

    def test_git_common_dir_non_git(self, tmp_path: Path):
        non_git = tmp_path / "non_git_dir"
        non_git.mkdir()
        assert get_git_common_dir(str(non_git)) is None

    def test_project_root_and_name_main_repo(self, git_project_with_worktree):
        main_repo, _ = git_project_with_worktree
        root = get_project_root(str(main_repo))
        assert root is not None
        assert Path(root).resolve() == main_repo.resolve()
        assert get_project_name(str(main_repo)) == "main_project"

    def test_project_root_and_name_worktree(self, git_project_with_worktree):
        main_repo, worktree = git_project_with_worktree
        root = get_project_root(str(worktree))
        assert root is not None
        # Worktree resolves to the main repo's root and name
        assert Path(root).resolve() == main_repo.resolve()
        assert get_project_name(str(worktree)) == "main_project"


class TestLockPath:
    def test_lock_path_shares_across_worktrees(self, git_project_with_worktree):
        main_repo, worktree = git_project_with_worktree
        main_lock = get_test_lock_path(str(main_repo))
        worktree_lock = get_test_lock_path(str(worktree))

        assert main_lock == worktree_lock
        assert (
            Path(main_lock).resolve()
            == (main_repo / ".git" / "cave_test.lock").resolve()
        )

    def test_lock_path_non_git(self, tmp_path: Path):
        non_git = tmp_path / "standalone_app"
        non_git.mkdir()
        lock_path = get_test_lock_path(str(non_git))
        assert "test_queue_" in lock_path
        assert lock_path.endswith(".lock")


class TestLockLogic:
    def test_acquire_and_release(self, tmp_path: Path):
        app_dir = tmp_path / "app1"
        app_dir.mkdir()
        lock = TestQueueLock(str(app_dir), "app1")

        with lock:
            assert lock._acquired is True
            assert lock.file_obj is not None

        assert lock._acquired is False
        assert lock.file_obj is None

    def test_contention_timeout(self, git_project_with_worktree):
        main_repo, worktree = git_project_with_worktree

        lock1 = TestQueueLock(str(main_repo), "main_project")
        lock2 = TestQueueLock(str(worktree), "worktree_project", timeout=0.2)

        with lock1:
            with pytest.raises(TimeoutError):
                with lock2:
                    pass

    def test_queueing_across_worktrees(self, git_project_with_worktree):
        main_repo, worktree = git_project_with_worktree

        events = []

        def worker1():
            with TestQueueLock(str(main_repo), "main_project"):
                events.append("worker1_start")
                time.sleep(0.3)
                events.append("worker1_end")

        def worker2():
            time.sleep(0.05)  # Ensure worker1 starts first
            with TestQueueLock(str(worktree), "worktree_project"):
                events.append("worker2_start")
                time.sleep(0.1)
                events.append("worker2_end")

        t1 = threading.Thread(target=worker1)
        t2 = threading.Thread(target=worker2)

        t1.start()
        t2.start()

        t1.join()
        t2.join()

        assert events == [
            "worker1_start",
            "worker1_end",
            "worker2_start",
            "worker2_end",
        ]

    def test_different_projects_do_not_block(self, tmp_path: Path):
        proj1 = tmp_path / "proj1"
        proj1.mkdir()
        proj2 = tmp_path / "proj2"
        proj2.mkdir()

        lock1 = TestQueueLock(str(proj1), "proj1")
        lock2 = TestQueueLock(str(proj2), "proj2", timeout=0.5)

        with lock1:
            with lock2:
                assert lock1._acquired is True
                assert lock2._acquired is True
