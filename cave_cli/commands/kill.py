import argparse

from cave_cli.utils.display import step_done, step_start
from cave_cli.utils.docker import get_running_apps, remove_containers
from cave_cli.utils.logger import logger
from cave_cli.utils.validate import get_app


def kill(args: argparse.Namespace) -> None:
    """
    Usage:

    - Stops Docker containers for CAVE apps
    """
    kill_all = getattr(args, "all", False)
    app_name = getattr(args, "name", None)

    running_apps = get_running_apps()

    if kill_all:
        if not running_apps:
            logger.info("No CAVE apps are currently running.")
            return
        for name in running_apps:
            step_start(f"Stopping {name}")
            remove_containers(name)
            step_done(f"Stopped {name}")
    elif app_name:
        if app_name not in running_apps:
            logger.error(f"App '{app_name}' is not running.")
            return
        step_start(f"Stopping {app_name}")
        remove_containers(app_name)
        step_done(f"Stopped {app_name}")
    else:
        _, app_name = get_app()
        if app_name not in running_apps:
            logger.info(f"App '{app_name}' is already stopped.")
            return
        step_start(f"Stopping {app_name}")
        remove_containers(app_name)
        step_done(f"Stopped {app_name}")
