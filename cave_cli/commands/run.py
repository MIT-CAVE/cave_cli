import argparse
import signal
import sys
import threading

from cave_cli.utils.display import (
    STOPPING,
    RunDashboard,
    print_section,
    step_done,
    step_start,
)
from cave_cli.utils.docker import (
    build_image,
    create_network,
    remove_containers,
    run_detached,
    run_detached_logged,
    run_interactive,
    stream_container_logs,
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
    skip_header: bool = False,
    skip_build: bool = False,
) -> None:
    interactive = getattr(args, "interactive", False) or getattr(
        args, "it", False
    )
    show_all = getattr(args, "show_all", False) or getattr(args, "verbose", False) or getattr(args, "loglevel", "INFO").upper() == "DEBUG"
    entrypoint = getattr(args, "entrypoint", None) or "./utils/run_server.sh"
    docker_args_str = getattr(args, "docker_args", "") or ""
    extra_docker_args = docker_args_str.split() if docker_args_str else []
    ip_port_arg = getattr(args, "ip_port", None)
    command_args = getattr(args, "command_args", []) or []
    extra_env = getattr(args, "extra_env", {}) or {}

    is_server_run = entrypoint == "./utils/run_server.sh" and not interactive
    use_tui = is_server_run and not show_all

    if interactive:
        server_command = ["bash"]
    else:
        server_command = [entrypoint] + command_args

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

    if not skip_header:
        print_section(f"Starting {app_name}")

    if not skip_build:
        build_image(app_name, app_dir)
    create_network(app_name)

    step_start("Starting database")
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
    step_done("Starting database")

    step_start("Starting cache")
    run_detached(
        name=f"{app_name}_redis_host",
        image=cache_image,
        network=network,
        volumes=[f"{app_name}_redis_volume:/data"],
        extra_args=extra_docker_args or None,
        command=["--save", "7200", "1"],
    )
    step_done("Starting cache")

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

    django_volumes = [f"{app_dir}:/app"]

    parsed = parse_ip_port(ip_port_arg) if ip_port_arg else None
    django_container = f"{app_name}_django"

    if parsed:
        ip, port = parsed
        if not is_port_available(port):
            logger.error(
                "The specified port is in use. Please try another."
            )
            sys.exit(1)

        if is_server_run and not interactive:
            step_start("Starting reverse proxy")
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
            step_done("Starting reverse proxy")

        django_env["CSRF_TRUSTED_ORIGIN"] = f"{ip}:{port}"
        url = f"https://{ip}:{port}"

        if interactive:
            logger.header("CAVE App: (Interactive)")
            run_interactive(
                name=django_container,
                image=f"cave-app:{app_name}",
                network=network,
                ports=["8000"],
                volumes=django_volumes,
                env_vars=django_env,
                extra_args=extra_docker_args or None,
                command=server_command,
            )
            remove_containers(app_name)

        elif use_tui:
            _run_tui(
                app_name=app_name,
                django_container=django_container,
                image=f"cave-app:{app_name}",
                network=network,
                ports=["8000"],
                volumes=django_volumes,
                env_vars=django_env,
                extra_args=extra_docker_args or None,
                command=server_command,
                url=url,
            )

        else:
            if is_server_run:
                logger.info(
                    f"Your Cave App can be accessed from Chrome at:\n{url}"
                )
            run_interactive(
                name=django_container,
                image=f"cave-app:{app_name}",
                network=network,
                ports=["8000"],
                volumes=django_volumes,
                env_vars=django_env,
                extra_args=extra_docker_args or None,
                command=server_command,
            )
            remove_containers(app_name)

    else:
        port = find_open_port(8000)
        url = f"http://localhost:{port}"

        if interactive:
            logger.header("CAVE App: (Interactive)")
            run_interactive(
                name=django_container,
                image=f"cave-app:{app_name}",
                network=network,
                ports=[f"{port}:8000"],
                volumes=django_volumes,
                env_vars=django_env,
                extra_args=extra_docker_args or None,
                command=server_command,
            )
            remove_containers(app_name)

        elif use_tui:
            _run_tui(
                app_name=app_name,
                django_container=django_container,
                image=f"cave-app:{app_name}",
                network=network,
                ports=[f"{port}:8000"],
                volumes=django_volumes,
                env_vars=django_env,
                extra_args=extra_docker_args or None,
                command=server_command,
                url=url,
            )

        else:
            if is_server_run:
                logger.info(
                    f"Your Cave App can be accessed from Chrome at:\n{url}"
                )
            run_interactive(
                name=django_container,
                image=f"cave-app:{app_name}",
                network=network,
                ports=[f"{port}:8000"],
                volumes=django_volumes,
                env_vars=django_env,
                extra_args=extra_docker_args or None,
                command=server_command,
            )
            remove_containers(app_name)


def _run_tui(
    app_name: str,
    django_container: str,
    image: str,
    network: str,
    ports: list[str],
    volumes: list[str],
    env_vars: dict[str, str],
    extra_args: list[str] | None,
    command: list[str],
    url: str,
) -> None:
    """
    Usage:

    - Runs the Django container detached and manages a live TUI dashboard.

    Notes:

    - Installs a SIGINT handler so Ctrl+C sets the stop event cleanly.
    - Always restores the terminal and removes containers in its finally block.
    """
    stop_event = threading.Event()
    dashboard = RunDashboard(app_name=app_name, url=url, stop_event=stop_event)

    original_sigint = signal.getsignal(signal.SIGINT)

    def handle_sigint(sig: int, frame: object) -> None:
        dashboard.set_status(STOPPING)
        stop_event.set()

    signal.signal(signal.SIGINT, handle_sigint)

    step_start("Starting Django")
    result = run_detached_logged(
        name=django_container,
        image=image,
        network=network,
        ports=ports,
        volumes=volumes,
        env_vars=env_vars,
        extra_args=extra_args,
        command=command,
    )

    if result.returncode != 0:
        step_done("Starting Django")
        signal.signal(signal.SIGINT, original_sigint)
        logger.error("Failed to start Django container.")
        remove_containers(app_name)
        sys.exit(1)

    step_done("Starting Django")

    log_thread = threading.Thread(
        target=stream_container_logs,
        args=(django_container, dashboard.get_queue(), stop_event),
        daemon=True,
    )

    dashboard.start()
    log_thread.start()

    try:
        stop_event.wait()
    finally:
        dashboard.stop()
        log_thread.join(timeout=5.0)
        signal.signal(signal.SIGINT, original_sigint)
        remove_containers(app_name)
