import argparse

from cave_cli.commands.run import run_cave
from cave_cli.utils.display import print_section
from cave_cli.utils.validate import get_app


def test(args: argparse.Namespace) -> None:
    """
    Usage:

    - Runs tests for the CAVE app in the current directory
    """
    app_dir, app_name = get_app()
    print_section("Test")

    remaining = getattr(args, "remaining", []) or []

    # If no specific test is provided, run all tests
    if not remaining:
        command_args = []
        extra_env = {"ALL_FLAG": "true"}
    else:
        command_args = [remaining[0]]
        extra_env = {}

    run_args = argparse.Namespace(
        entrypoint="./utils/run_test.sh",
        command_args=command_args,
        extra_env=extra_env,
        interactive=False,
        it=False,
        docker_args="",
        ip_port=None,
        yes=True,
        verbose=getattr(args, "verbose", False),
        loglevel=getattr(args, "loglevel", "INFO"),
    )
    run_cave(app_dir, app_name, run_args, skip_header=True)
