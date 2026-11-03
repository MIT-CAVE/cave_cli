import argparse
import shlex
import sys

from cave_cli.utils.display import print_section
from cave_cli.utils.lock import (
    TestQueueCancelledError,
    TestQueueLock,
    cancel_test_queue,
)
from cave_cli.utils.logger import logger
from cave_cli.utils.test_server import (
    ensure_idle_watcher,
    is_test_server_running,
    reset_test_server,
    run_test_in_server,
    start_test_server,
    stop_test_server,
    touch_test_activity,
)
from cave_cli.utils.validate import get_app


def test(args: argparse.Namespace) -> None:
    """
    Usage:

    - Runs tests for the CAVE app in the current directory against a persistent test server
    """
    app_dir, app_name = get_app()

    # Handle cancellation and kill-server actions
    if getattr(args, "kill_server", False):
        cancel_test_queue(app_dir, app_name, kill_server=True)
        logger.info(
            f"Test queue cleared and test server stopped for '{app_name}'."
        )
        return

    if getattr(args, "cancel", False):
        cancel_test_queue(app_dir, app_name, kill_server=False)
        logger.info(f"Test queue cleared for '{app_name}'.")
        return

    print_section("Test")

    remaining = getattr(args, "remaining", []) or []
    if not remaining:
        command_args = []
        extra_env = {"ALL_FLAG": "true"}
    else:
        command_args = [remaining[0]]
        extra_env = {}

    keep_alive = getattr(args, "keep_alive", 10)
    should_reset = getattr(args, "reset", False)
    docker_args_str = getattr(args, "docker_args", "") or ""
    extra_docker_args = shlex.split(docker_args_str) if docker_args_str else []

    try:
        with TestQueueLock(app_dir, app_name):
            if should_reset:
                reset_test_server(app_dir, app_name, extra_docker_args)
            elif not is_test_server_running(app_name):
                start_test_server(app_dir, app_name, extra_docker_args)
            else:
                logger.debug(f"Reusing warm test server for '{app_name}'.")

            exit_code = run_test_in_server(
                app_name=app_name,
                command_args=command_args,
                extra_env=extra_env,
            )
            touch_test_activity(app_dir, app_name)

            if keep_alive == 0:
                stop_test_server(app_name)
            else:
                ensure_idle_watcher(app_dir, app_name, keep_alive)

            if exit_code != 0:
                sys.exit(exit_code)
    except TestQueueCancelledError:
        logger.warn("Test was canceled before execution.")
        sys.exit(130)
