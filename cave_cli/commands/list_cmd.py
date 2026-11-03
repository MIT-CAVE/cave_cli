import argparse

from cave_cli.utils.display import print_key_value, print_section
from cave_cli.utils.docker import (
    get_container_env,
    get_container_host_port,
    get_all_containers,
    get_running_apps,
    get_running_test_servers,
)
from cave_cli.utils.logger import logger


def list_cmd(args: argparse.Namespace) -> None:
    """
    Usage:

    - Lists running CAVE apps or all CAVE app containers
    """
    show_all = getattr(args, "all", False)

    if show_all:
        print_section("CAVE App Containers (All)")
        from cave_cli.utils.display import _QUIET

        for suffix in (
            "_django",
            "_db_host",
            "_redis_host",
            "_nginx_host",
            "_test_django",
            "_test_db_host",
            "_test_redis_host",
        ):
            for name in get_all_containers(suffix):
                if not _QUIET:
                    print(f"  ● {name}")
    else:
        apps = get_running_apps()
        test_servers = get_running_test_servers()
        if not apps and not test_servers:
            logger.info("No CAVE apps are currently running.")
            return

        if apps:
            print_section("CAVE Apps (Running)")
            for app_name in apps:
                nginx_containers = get_all_containers("_nginx_host")
                nginx_name = f"{app_name}_nginx_host"
                if nginx_name in nginx_containers:
                    ip = get_container_env(nginx_name, "CAVE_IP")
                    port = get_container_env(nginx_name, "CAVE_PORT")
                    print_key_value(app_name, f"https://{ip}:{port}")
                else:
                    port = get_container_host_port(f"{app_name}_django")
                    print_key_value(app_name, f"http://localhost:{port}")

        if test_servers:
            print_section("CAVE Test Servers (Warm)")
            for app_name in test_servers:
                print_key_value(app_name, "Running (idle / testing)")

    from cave_cli.utils.display import _QUIET

    if not _QUIET:
        print("")
