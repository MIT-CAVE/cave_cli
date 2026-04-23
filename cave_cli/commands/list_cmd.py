import argparse

from cave_cli.utils.docker import (
    get_container_env,
    get_container_host_port,
    get_all_containers,
    get_running_apps,
)
from cave_cli.utils.logger import logger


def list_cmd(args: argparse.Namespace) -> None:
    """
    Usage:

    - Lists running CAVE apps or all CAVE app containers
    """
    show_all = getattr(args, "all", False)

    if show_all:
        logger.header("CAVE App Containers (All):")
        for suffix in ("_django", "_db_host", "_redis_host", "_nginx_host"):
            for name in get_all_containers(suffix):
                logger.info(name)
    else:
        logger.header("CAVE Apps (Running):")
        apps = get_running_apps()
        for app_name in apps:
            nginx_containers = get_all_containers("_nginx_host")
            nginx_name = f"{app_name}_nginx_host"
            if nginx_name in nginx_containers:
                ip = get_container_env(nginx_name, "CAVE_IP")
                port = get_container_env(nginx_name, "CAVE_PORT")
                logger.info(f"{app_name} (https://{ip}:{port})")
            else:
                port = get_container_host_port(f"{app_name}_django")
                logger.info(f"{app_name} (http://localhost:{port})")
