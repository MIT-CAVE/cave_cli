import argparse
import sys

from cave_cli.utils.docker import (
    build_image,
    create_network,
    remove_containers,
    run_detached,
    run_interactive,
)
from cave_cli.utils.env import parse_env
from cave_cli.utils.logger import logger
from cave_cli.utils.net import find_open_port, is_port_available, parse_ip_port


def run(args: argparse.Namespace) -> None:
    """
    Usage:

    - Builds and runs the CAVE app's Docker containers
    """
    from cave_cli.utils.validate import get_app

    app_dir, app_name = get_app()
    run_cave(app_dir, app_name, args)


def run_cave(
    app_dir: str,
    app_name: str,
    args: argparse.Namespace,
) -> None:
    build_image(app_name, app_dir)

    interactive = getattr(args, "interactive", False) or getattr(
        args, "it", False
    )
    entrypoint = getattr(args, "entrypoint", None) or "./utils/run_server.sh"
    docker_args_str = getattr(args, "docker_args", "") or ""
    extra_docker_args = docker_args_str.split() if docker_args_str else []
    ip_port_arg = getattr(args, "ip_port", None)

    command_args = getattr(args, "command_args", []) or []
    extra_env = getattr(args, "extra_env", {}) or {}

    if interactive:
        server_command = ["bash"]
        logger.header("CAVE App: (Interactive)")
    else:
        server_command = [entrypoint] + command_args
        logger.header(f"CAVE App: ({entrypoint})")

    if extra_docker_args:
        logger.info(f"docker-args: {docker_args_str}")

    env_vars = parse_env(f"{app_dir}/.env")
    db_password = env_vars.get("DATABASE_PASSWORD", "")
    db_image = env_vars.get("DATABASE_IMAGE", "postgres:latest")
    db_command_str = env_vars.get(
        "DATABASE_COMMAND", "postgres -c listen_addresses=*"
    )
    cache_image = env_vars.get("CACHE_IMAGE", "")

    if not db_command_str:
        db_command_str = "postgres -c listen_addresses=*"
        logger.debug(
            "DATABASE_COMMAND not set in '.env' file. "
            "Using 'postgres -c listen_addresses=*' as default."
        )

    if not cache_image:
        logger.warn(
            "CACHE_IMAGE not set in '.env' file. "
            "Using valkey/valkey:7 as default."
        )
        cache_image = "valkey/valkey:7"

    network = f"cave-net:{app_name}"
    create_network(app_name)

    run_detached(
        name=f"{app_name}_db_host",
        image=db_image,
        network=network,
        volumes=[f"{app_name}_pg_volume:/var/lib/postgresql/data"],
        env_vars={
            "POSTGRES_PASSWORD": db_password,
            "POSTGRES_USER": f"{app_name}_user",
            "POSTGRES_DB": f"{app_name}_name",
        },
        extra_args=extra_docker_args or None,
        command=db_command_str.split(),
    )

    run_detached(
        name=f"{app_name}_redis_host",
        image=cache_image,
        network=network,
        volumes=[f"{app_name}_redis_volume:/data"],
        extra_args=extra_docker_args or None,
        command=["--save", "7200", "1"],
    )

    django_env = {
        "DATABASE_HOST": f"{app_name}_db_host",
        "DATABASE_USER": f"{app_name}_user",
        "DATABASE_PASSWORD": db_password,
        "DATABASE_NAME": f"{app_name}_name",
        "DATABASE_PORT": "5432",
        "REDIS_HOST": f"{app_name}_redis_host",
        "REDIS_PORT": "6379",
        **extra_env,
    }

    django_volumes = [
        f"{app_dir}:/app"
    ]

    parsed = parse_ip_port(ip_port_arg) if ip_port_arg else None

    if parsed:
        ip, port = parsed
        if not is_port_available(port):
            logger.error(
                "The specified port is in use. Please try another."
            )
            sys.exit(1)

        if entrypoint == "./utils/run_server.sh" and not interactive:
            logger.info(
                f"Your Cave App can be accessed from Chrome at:\n"
                f"https://{ip}:{port}\n"
            )

        run_detached(
            name=f"{app_name}_nginx_host",
            image="nginx",
            network=network,
            extra_args=[
                "--restart",
                "unless-stopped",
                "-p",
                f"{ip}:{port}:8000",
            ]
            + (extra_docker_args or []),
            volumes=[
                f"{app_dir}/utils/lan_hosting:/certs",
                f"{app_dir}/utils/nginx_ssl.conf.template:"
                "/etc/nginx/templates/default.conf.template:ro",
            ],
            env_vars={
                "CAVE_HOST": f"{app_name}_django",
                "CAVE_PORT": str(port),
                "CAVE_IP": ip,
            },
        )

        django_env["CSRF_TRUSTED_ORIGIN"] = f"{ip}:{port}"
        run_interactive(
            name=f"{app_name}_django",
            image=f"cave-app:{app_name}",
            network=network,
            ports=["8000"],
            volumes=django_volumes,
            env_vars=django_env,
            extra_args=extra_docker_args or None,
            command=server_command,
        )
    else:
        port = find_open_port(8000)
        if entrypoint == "./utils/run_server.sh" and not interactive:
            logger.info(
                f"Your Cave App can be accessed from Chrome at:\n"
                f"http://localhost:{port}\n"
            )

        run_interactive(
            name=f"{app_name}_django",
            image=f"cave-app:{app_name}",
            network=network,
            ports=[f"{port}:8000"],
            volumes=django_volumes,
            env_vars=django_env,
            extra_args=extra_docker_args or None,
            command=server_command,
        )

    logger.debug("Stopping Running Containers...")
    remove_containers(app_name)
