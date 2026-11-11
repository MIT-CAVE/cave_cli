import argparse
import shlex
import sys

from cave_cli.commands.task import schedule_task
from cave_cli.utils.display import print_section
from cave_cli.utils.validate import get_app


def test(args: argparse.Namespace) -> None:
    """
    Usage:

    - Runs tests for the CAVE app in the current directory against a persistent task server

    Requires:

    - ``args``:
        - Type: argparse.Namespace
        - What: Parsed command-line arguments for test
    """
    app_dir, app_name = get_app()
    print_section("Test")

    remaining = getattr(args, "remaining", []) or []
    if not remaining:
        command_args = []
        extra_env = {"ALL_FLAG": "true"}
    else:
        command_args = [remaining[0]]
        extra_env = {}

    docker_args_str = getattr(args, "docker_args", "") or ""
    extra_docker_args = shlex.split(docker_args_str) if docker_args_str else []
    detached = getattr(args, "detached", False)

    exit_code = schedule_task(
        app_dir=app_dir,
        app_name=app_name,
        command=["./utils/run_test.sh"] + command_args,
        detached=detached,
        docker_args=extra_docker_args,
        display_command="test",
        extra_env=extra_env,
    )
    if exit_code != 0:
        sys.exit(exit_code)
