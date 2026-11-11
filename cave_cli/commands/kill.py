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
    kill_task = getattr(args, "task", False) or getattr(args, "test", False)
    app_name = getattr(args, "name", None)

    if kill_task:
        from cave_cli.utils.docker import get_running_task_servers
        from cave_cli.utils.task_server import stop_task_server

        running_task_servers = get_running_task_servers()
        if kill_all:
            if not running_task_servers:
                logger.info("No CAVE task servers are currently running.")
                return
            for name in running_task_servers:
                stop_task_server(name)
        elif app_name:
            if app_name not in running_task_servers:
                logger.error(f"Task server for '{app_name}' is not running.")
                return
            stop_task_server(app_name)
        else:
            _, app_name = get_app()
            if app_name not in running_task_servers:
                logger.info(f"Task server for '{app_name}' is already stopped.")
                return
            stop_task_server(app_name)
        return

    running_apps = get_running_apps()

    if kill_all:
        if not running_apps:
            logger.info("No CAVE apps are currently running.")
            return
        for name in running_apps:
            remove_containers(name)
    elif app_name:
        if app_name not in running_apps:
            logger.error(f"App '{app_name}' is not running.")
            return
        remove_containers(app_name)
    else:
        _, app_name = get_app()
        if app_name not in running_apps:
            logger.info(f"App '{app_name}' is already stopped.")
            return
        remove_containers(app_name)
