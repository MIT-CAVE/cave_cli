import argparse

from cave_cli.commands.run import run_cave
from cave_cli.utils.logger import logger
from cave_cli.utils.validate import get_app


def test(args: argparse.Namespace) -> None:
    """
    Usage:

    - Runs tests for the CAVE app in the current directory
    """
    app_dir, app_name = get_app()
    logger.info("Testing cave_api...")

    remaining = getattr(args, "remaining", []) or []

    run_args = argparse.Namespace(
        entrypoint="./utils/run_test.sh",
        interactive=False,
        it=False,
        docker_args="",
        ip_port=None,
        yes=True,
        verbose=getattr(args, "verbose", False),
        loglevel=getattr(args, "loglevel", "INFO"),
    )
    run_cave(app_dir, app_name, run_args)
