import argparse
import sys

from cave_cli.commands.run import run_cave
from cave_cli.utils.display import (
    print_section,
    step_done,
    step_fail,
    step_start,
)
from cave_cli.utils.docker import remove_containers, remove_volume
from cave_cli.utils.logger import logger
from cave_cli.utils.subprocess import run_and_log
from cave_cli.utils.task_queue import reset_task_registry
from cave_cli.utils.task_server import stop_task_server
from cave_cli.utils.validate import confirm_action, get_app


def reset(
    args: argparse.Namespace,
    app_dir: str | None = None,
    app_name: str | None = None,
    skip_build: bool = False,
) -> int:
    """
    Usage:

    - Removes Docker containers and volumes, then rebuilds from scratch

    Requires:

    - ``args``:
        - Type: argparse.Namespace
        - What: Parsed CLI arguments

    Optional:

    - ``app_dir``:
        - Type: str | None
        - What: Path to CAVE application directory
        - Default: None

    - ``app_name``:
        - Type: str | None
        - What: Name of CAVE application
        - Default: None

    - ``skip_build``:
        - Type: bool
        - What: Whether to skip rebuilding the Docker image
        - Default: False

    Returns:

    - ``exit_code``:
        - Type: int
        - What: 0 on success, non-zero exit code on failure
    """
    auto_yes = getattr(args, "yes", False)
    if not auto_yes:
        confirm_action(
            "This will remove the Docker containers "
            "(deleted and recreated from scratch) for this app. "
            "All data in your database will be lost"
        )

    if app_dir is None or app_name is None:
        app_dir, app_name = get_app()

    print_section("Reset")

    remove_containers(app_name, skip_header=True)
    stop_task_server(app_name)
    reset_task_registry(app_dir)

    step_start("Removing database volume")
    remove_volume(app_name)
    step_done("Removing database volume")

    step_start("Removing task volumes")
    remove_volume(app_name, "task_pg_volume")
    remove_volume(app_name, "task_redis_volume")
    remove_volume(app_name, "test_pg_volume")
    remove_volume(app_name, "test_redis_volume")
    step_done("Removing task volumes")

    run_and_log(["docker", "image", "rm", "-f", f"cave-app-task:{app_name}"])
    run_and_log(["docker", "image", "rm", "-f", f"cave-app-test:{app_name}"])

    exit_on_error = getattr(args, "exit_on_error", True)
    reset_args = argparse.Namespace(
        entrypoint="./utils/reset_db.sh",
        interactive=False,
        it=False,
        docker_args=getattr(args, "docker_args", "") or "",
        ip_port=None,
        yes=True,
        no_tui=getattr(args, "no_tui", False),
        raw=getattr(args, "raw", False),
        verbose=getattr(args, "verbose", False),
        loglevel=getattr(args, "loglevel", "INFO"),
        exit_on_error=exit_on_error,
    )
    exit_code = run_cave(
        app_dir, app_name, reset_args, skip_header=True, skip_build=skip_build
    )
    if isinstance(exit_code, int) and exit_code != 0:
        step_fail("Reset", f"Reset failed with exit code {exit_code}")
        logger.error(f"Reset failed with exit code {exit_code}.")
        if exit_on_error:
            sys.exit(exit_code)
        return exit_code
    step_done("Reset complete")
    return 0
