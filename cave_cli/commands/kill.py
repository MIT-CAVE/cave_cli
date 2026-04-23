import argparse

from cave_cli.utils.docker import get_running_apps, remove_containers
from cave_cli.utils.logger import logger
from cave_cli.utils.validate import get_app


def kill(args: argparse.Namespace) -> None:
    """
    Usage:

    - Stops Docker containers for CAVE apps
    """
    kill_all = getattr(args, "all", False)

    if kill_all:
        for app_name in get_running_apps():
            remove_containers(app_name)
            logger.info(f"Killed: {app_name}")
    else:
        _, app_name = get_app()
        remove_containers(app_name)
        logger.info(f"Killed: {app_name}")
