import argparse
import os
import shlex
import signal
import sys
import threading

from cave_cli.utils.display import (
    MODE_ALL,
    MODE_LIFECYCLE,
    MODE_STANDARD,
    MODE_VERBOSE,
    READY,
    STOPPING,
    RunDashboard,
    StackComponent,
    print_section,
    step_done,
    step_fail,
    step_start,
)
from cave_cli.utils.docker import (
    build_image,
    create_network,
    remove_containers,
    run_and_log,
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
    detached = getattr(args, "detached", False)
    attach = getattr(args, "attach", False)
    no_tui = (
        getattr(args, "no_tui", False)
        or getattr(args, "raw", False)
        or getattr(args, "verbose", False)
        or (getattr(args, "loglevel", None) or "INFO").upper() == "DEBUG"
        or os.environ.get("CAVE_NO_TUI", "").lower() in ("1", "true", "yes")
    )
    ip_port_arg = getattr(args, "ip_port", None)
    if ip_port_arg == "attach":
        attach = True
        ip_port_arg = None
    elif ip_port_arg in ("detach", "detached"):
        detached = True
        ip_port_arg = None

    if attach and detached:
        logger.error("Cannot use --attach and --detached together.")
        sys.exit(1)

    show_all = (
        getattr(args, "show_all", False)
        or getattr(args, "verbose", False)
        or (getattr(args, "loglevel", None) or "INFO").upper() == "DEBUG"
    )
    entrypoint = getattr(args, "entrypoint", None) or "./utils/run_server.sh"
    docker_args_str = getattr(args, "docker_args", "") or ""
    extra_docker_args = shlex.split(docker_args_str) if docker_args_str else []
    command_args = getattr(args, "command_args", []) or []
    extra_env = getattr(args, "extra_env", {}) or {}
    quiet = (
        getattr(args, "quiet", False)
        or (getattr(args, "loglevel", None) or "INFO").upper() == "SILENT"
    )

    is_server_run = entrypoint == "./utils/run_server.sh" and not interactive
    if not attach and not detached and is_server_run:
        from cave_cli.utils.docker import get_running_apps

        if app_name in get_running_apps():
            attach = True

    initial_mode = (
        MODE_VERBOSE
        if (
            getattr(args, "verbose", False)
            or (getattr(args, "loglevel", None) or "INFO").upper() == "DEBUG"
        )
        else (
            MODE_ALL
            if getattr(args, "show_all", False)
            else (
                MODE_LIFECYCLE
                if (not attach and not detached)
                else MODE_STANDARD
            )
        )
    )

    if attach:
        from cave_cli.utils.docker import (
            get_all_containers,
            get_container_env,
            get_container_host_port,
            get_running_apps,
        )

        running_apps = get_running_apps()
        if app_name not in running_apps:
            logger.error(
                f"No running CAVE app found for '{app_name}'. "
                "Run 'cave run' to start it."
            )
            sys.exit(1)

        nginx_containers = get_all_containers("_nginx_host")
        nginx_name = f"{app_name}_nginx_host"
        if nginx_name in nginx_containers:
            ip = get_container_env(nginx_name, "CAVE_IP")
            port = get_container_env(nginx_name, "CAVE_PORT")
            url = f"https://{ip}:{port}"
        else:
            port = get_container_host_port(f"{app_name}_django")
            url = (
                f"http://localhost:{port}" if port else "http://localhost:8000"
            )

        django_container = f"{app_name}_django"
        from cave_cli.utils.task_queue import (
            get_run_log_limit,
            get_run_log_path,
        )

        log_lines_arg = getattr(args, "log_lines", None)
        log_history_arg = getattr(args, "log_history", None)
        if log_history_arg is False or log_lines_arg == 0:
            run_log_limit = 0
        elif log_lines_arg is not None and log_lines_arg > 0:
            run_log_limit = log_lines_arg
        else:
            run_log_limit = get_run_log_limit(app_dir)

        run_log_path = get_run_log_path(app_dir) if run_log_limit > 0 else None

        if no_tui:
            logger.header("CAVE App (CLI)")
            logger.info(
                f"Streaming logs for '{app_name}'... (Press CTRL+C to quit)"
            )
            _stream_raw(
                django_container=django_container,
                log_file_path=run_log_path,
                max_log_lines=run_log_limit,
            )
            return

        logger.header("CAVE App")
        _run_tui(
            app_name=app_name,
            django_container=django_container,
            image=f"cave-app:{app_name}",
            network=f"cave-net:{app_name}",
            ports=[],
            volumes=[],
            env_vars={},
            extra_args=None,
            command=[],
            url=url,
            log_file_path=run_log_path,
            max_log_lines=run_log_limit,
            already_running=True,
            initial_mode=initial_mode,
        )
        return

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

    parsed = parse_ip_port(ip_port_arg) if ip_port_arg else None
    if parsed:
        ip, port = parsed
        if not is_port_available(port):
            logger.error("The specified port is in use. Please try another.")
            sys.exit(1)
        django_ports = ["8000"]
        django_env = {
            "DATABASE_HOST": f"{app_name}_db_host",
            "DATABASE_USER": f"{app_name}_user",
            "DATABASE_PASSWORD": db_password,
            "DATABASE_NAME": f"{app_name}_name",
            "DATABASE_PORT": "5432",
            "REDIS_HOST": f"{app_name}_redis_host",
            "REDIS_PORT": "6379",
            "CSRF_TRUSTED_ORIGIN": f"{ip}:{port}",
            **extra_env,
        }
        url = f"https://{ip}:{port}"
    else:
        port = find_open_port(8000)
        django_ports = [f"{port}:8000"]
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
        url = f"http://localhost:{port}"

    django_volumes = [f"{app_dir}:/app"]
    django_container = f"{app_name}_django"

    from cave_cli.utils.task_queue import (
        get_run_log_limit,
        get_run_log_path,
    )

    log_lines_arg = getattr(args, "log_lines", None)
    log_history_arg = getattr(args, "log_history", None)
    if log_history_arg is False or log_lines_arg == 0:
        run_log_limit = 0
    elif log_lines_arg is not None and log_lines_arg > 0:
        run_log_limit = log_lines_arg
    else:
        run_log_limit = get_run_log_limit(app_dir)

    run_log_path = get_run_log_path(app_dir) if run_log_limit > 0 else None

    # ── Non-TUI Execution (detached / interactive / no-tui) ───────────────
    if detached or interactive or no_tui:
        if not skip_header:
            print_section(f"Starting {app_name}")
        remove_containers(app_name, skip_header=True)
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

        if is_server_run and "postgres" in db_image.lower():
            from cave_cli.utils.docker import (
                is_container_ready,
                is_db_initialized,
            )
            from cave_cli.utils.validate import confirm_action
            import time

            db_container = f"{app_name}_db_host"
            db_user = f"{app_name}_user"
            db_name = f"{app_name}_name"

            step_start("Checking database")
            ready = False
            for _ in range(30):
                if is_container_ready(db_container, db_user):
                    ready = True
                    break
                time.sleep(1)

            if ready:
                if not is_db_initialized(db_container, db_user, db_name):
                    step_done("Checking database")
                    confirm_action(
                        "The database for this app is not set up. "
                        "Would you like to set it up now?",
                        auto_yes=getattr(args, "yes", False),
                    )
                    step_start("Initializing database")
                    run_interactive(
                        name=f"{app_name}_django_setup",
                        image=f"cave-app:{app_name}",
                        network=network,
                        volumes=django_volumes,
                        env_vars=django_env,
                        command=["./utils/reset_db.sh"],
                    )
                    run_and_log(["docker", "rm", f"{app_name}_django_setup"])
                    step_done("Initializing database")
                else:
                    step_done("Checking database")
            else:
                step_fail(
                    "Checking database",
                    "Database container failed to become ready.",
                )
                remove_containers(app_name)
                sys.exit(1)

        if parsed:
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

        if detached:
            step_start("Starting Django")
            result = run_detached_logged(
                name=django_container,
                image=f"cave-app:{app_name}",
                network=network,
                ports=django_ports,
                volumes=django_volumes,
                env_vars=django_env,
                extra_args=extra_docker_args or None,
                command=server_command,
            )
            if result.returncode != 0:
                step_done("Starting Django")
                logger.error("Failed to start Django container.")
                remove_containers(app_name)
                sys.exit(1)
            step_done("Starting Django")
            logger.success(
                f"App '{app_name}' running in detached mode at {url}"
            )
            logger.info("Rejoin with: cave run --attach")
            return

        if interactive:
            logger.header("CAVE App (Interactive)")
            run_interactive(
                name=django_container,
                image=f"cave-app:{app_name}",
                network=network,
                ports=django_ports,
                volumes=django_volumes,
                env_vars=django_env,
                extra_args=extra_docker_args or None,
                command=server_command,
            )
            remove_containers(app_name)
            return

        if no_tui:
            step_start("Starting Django")
            result = run_detached_logged(
                name=django_container,
                image=f"cave-app:{app_name}",
                network=network,
                ports=django_ports,
                volumes=django_volumes,
                env_vars=django_env,
                extra_args=extra_docker_args or None,
                command=server_command,
            )
            if result.returncode != 0:
                step_fail(
                    "Starting Django", "Failed to start Django container."
                )
                logger.error("Failed to start Django container.")
                remove_containers(app_name)
                sys.exit(1)
            step_done("Starting Django")
            logger.header("CAVE App (CLI)")
            if is_server_run:
                logger.info(
                    f"Watching for changes and running at {url}... "
                    "(Press CTRL+C to quit)"
                )
            _stream_raw(
                django_container=django_container,
                log_file_path=run_log_path,
                max_log_lines=run_log_limit,
            )
            remove_containers(app_name)
            return

    # ── TUI Server Execution (with Lifecycle Start & Fallback) ────────────
    stop_event = threading.Event()
    dashboard = RunDashboard(
        app_name=app_name,
        url=url,
        stop_event=stop_event,
        initial_mode=initial_mode,
    )
    components = [
        StackComponent(
            "App Server",
            f"cave-app:{app_name}",
            django_container,
            "Pending",
        ),
        StackComponent(
            "Database",
            db_image,
            f"{app_name}_db_host",
            "Pending",
        ),
        StackComponent(
            "Cache",
            cache_image,
            f"{app_name}_redis_host",
            "Pending",
        ),
        StackComponent("Network", "bridge", network, "Pending"),
    ]
    if parsed:
        components.append(
            StackComponent(
                "Proxy", "nginx", f"{app_name}_nginx_host", "Pending"
            )
        )
    dashboard.set_components(components)
    dashboard.start()

    try:
        remove_containers(app_name, skip_header=True)
        if not skip_build:
            dashboard.update_component("App Server", "Building")
            build_image(app_name, app_dir)
            dashboard.update_component("App Server", "Built")

        dashboard.update_component("Network", "Creating")
        create_network(app_name)
        dashboard.update_component("Network", "Active")

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

        if is_server_run and "postgres" in db_image.lower():
            from cave_cli.utils.docker import (
                is_container_ready,
                is_db_initialized,
            )
            from cave_cli.utils.validate import confirm_action
            import time

            db_container = f"{app_name}_db_host"
            db_user = f"{app_name}_user"
            db_name = f"{app_name}_name"

            step_start("Checking database")
            ready = False
            for _ in range(30):
                if is_container_ready(db_container, db_user):
                    ready = True
                    break
                time.sleep(1)

            if not ready:
                step_fail(
                    "Checking database",
                    "Database container failed to become ready.",
                )
                raise RuntimeError("Database container failed to become ready.")

            if not is_db_initialized(db_container, db_user, db_name):
                step_done("Checking database")
                confirm_action(
                    "The database for this app is not set up. "
                    "Would you like to set it up now?",
                    auto_yes=getattr(args, "yes", False),
                )
                step_start("Initializing database")
                run_and_log(
                    [
                        "docker",
                        "run",
                        "--rm",
                        "--network",
                        network,
                        *sum([["--volume", v] for v in django_volumes], []),
                        *sum(
                            [["-e", f"{k}={v}"] for k, v in django_env.items()],
                            [],
                        ),
                        "--name",
                        f"{app_name}_django_setup",
                        f"cave-app:{app_name}",
                        "./utils/reset_db.sh",
                    ]
                )
                step_done("Initializing database")
            else:
                step_done("Checking database")

        if parsed:
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

        _run_tui(
            app_name=app_name,
            django_container=django_container,
            image=f"cave-app:{app_name}",
            network=network,
            ports=django_ports,
            volumes=django_volumes,
            env_vars=django_env,
            extra_args=extra_docker_args or None,
            command=server_command,
            url=url,
            log_file_path=run_log_path,
            max_log_lines=run_log_limit,
            initial_mode=initial_mode,
            dashboard=dashboard,
            is_server_run=is_server_run,
        )

    except Exception as exc:
        dashboard.stop()
        logger.error(f"Startup error: {exc}")
        if dashboard.startup_logs:
            logger.info("\n--- Recent Startup Logs ---")
            for line in dashboard.startup_logs[-20:]:
                sys.stderr.write(f"  {line}\n")
        remove_containers(app_name, skip_header=True)
        sys.exit(1)
    except BaseException:
        dashboard.stop()
        raise


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
    log_file_path: str | None = None,
    max_log_lines: int = 1000,
    already_running: bool = False,
    initial_mode: str = MODE_STANDARD,
    dashboard: RunDashboard | None = None,
    is_server_run: bool = True,
) -> None:
    """
    Usage:

    - Runs or attaches to the Django container and manages a live TUI dashboard.

    Requires:

    - ``app_name``:
        - Type: str
        - What: Name of the CAVE application.

    - ``django_container``:
        - Type: str
        - What: Name of the Django Docker container.

    - ``image``:
        - Type: str
        - What: Docker image name for the container.

    - ``network``:
        - Type: str
        - What: Docker network name.

    - ``ports``:
        - Type: list[str]
        - What: Port mapping list.

    - ``volumes``:
        - Type: list[str]
        - What: Volume mounting list.

    - ``env_vars``:
        - Type: dict[str, str]
        - What: Environment variable dictionary.

    - ``extra_args``:
        - Type: list[str] | None
        - What: Additional Docker arguments.

    - ``command``:
        - Type: list[str]
        - What: Command to execute in the container.

    - ``url``:
        - Type: str
        - What: App URL to display in the dashboard.

    Optional:

    - ``log_file_path``:
        - Type: str | None
        - What: Path to save rotating server logs.
        - Default: None

    - ``max_log_lines``:
        - Type: int
        - What: Maximum log lines to store in the log file.
        - Default: 1000

    - ``already_running``:
        - Type: bool
        - What: Whether the Django container is already running and being attached to.
        - Default: False

    - ``initial_mode``:
        - Type: str
        - What: Initial display mode ("standard", "all", or "verbose").
        - Default: MODE_STANDARD

    - ``dashboard``:
        - Type: RunDashboard | None
        - What: Existing RunDashboard instance to reuse.
        - Default: None

    - ``is_server_run``:
        - Type: bool
        - What: Whether this run is an interactive web server run.
        - Default: True

    Notes:

    - Installs a SIGINT handler so Ctrl+C sets the stop event cleanly.
    - Always restores the terminal in its finally block.
    - If detached via Esc, leaves containers running; otherwise removes containers.
    """
    if dashboard is None:
        stop_event = threading.Event()
        dashboard = RunDashboard(
            app_name=app_name,
            url=url,
            stop_event=stop_event,
            initial_mode=initial_mode,
        )
        if already_running:
            dashboard.set_status(READY)
            components = [
                StackComponent(
                    "App Server",
                    image,
                    django_container,
                    "Ready",
                ),
                StackComponent(
                    "Database",
                    "postgres",
                    f"{app_name}_db_host",
                    "Ready",
                ),
                StackComponent(
                    "Cache",
                    "valkey",
                    f"{app_name}_redis_host",
                    "Ready",
                ),
                StackComponent(
                    "Network",
                    "bridge",
                    network,
                    "Active",
                ),
            ]
            dashboard.set_components(components)
            dashboard.add_lifecycle_event(
                f"Attached to running app at {url}", status="ok"
            )
    else:
        stop_event = dashboard._stop_event

    original_sigint = signal.getsignal(signal.SIGINT)

    def handle_sigint(sig: int, frame: object) -> None:
        dashboard.set_status(STOPPING)
        stop_event.set()

    signal.signal(signal.SIGINT, handle_sigint)

    if not already_running:
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
            step_fail("Starting Django", "Failed to start Django container.")
            signal.signal(signal.SIGINT, original_sigint)
            logger.error("Failed to start Django container.")
            remove_containers(app_name)
            sys.exit(1)

        step_done("Starting Django")
        if is_server_run:
            step_start("Loading App")
        else:
            task_name = os.path.basename(command[0]) if command else "task"
            step_start(f"Running {task_name}")

    tail = 200 if already_running else None
    log_thread = threading.Thread(
        target=stream_container_logs,
        args=(
            django_container,
            dashboard.get_queue(),
            stop_event,
            log_file_path,
            max_log_lines,
            tail,
        ),
        daemon=True,
    )

    if not dashboard.is_active_tui:
        dashboard.start()
    log_thread.start()

    try:
        stop_event.wait()
    finally:
        signal.signal(signal.SIGINT, original_sigint)
        if not is_server_run and dashboard.container_exited:
            task_name = os.path.basename(command[0]) if command else "task"
            step_done(f"Running {task_name}")
            dashboard.update_component("App Server", "Done")
        if not dashboard.is_detached:
            dashboard.set_status(STOPPING)
            if dashboard.mode != MODE_VERBOSE:
                dashboard.set_mode(MODE_LIFECYCLE)
            remove_containers(app_name)
        dashboard.stop()
        log_thread.join(timeout=2.0)
        if dashboard.is_detached:
            print(f"\nDetached from '{app_name}'. Rejoin with: cave run\n")


def _stream_raw(
    django_container: str,
    log_file_path: str | None = None,
    max_log_lines: int = 1000,
) -> None:
    """
    Usage:

    - Streams logs from a running container directly to stdout in CLI mode.

    Requires:

    - ``django_container``:
        - Type: str
        - What: Name of the Django container to follow.

    Optional:

    - ``log_file_path``:
        - Type: str | None
        - What: Path to save rotating server logs.
        - Default: None

    - ``max_log_lines``:
        - Type: int
        - What: Maximum log lines to store in the log file.
        - Default: 1000
    """
    import queue

    stop_event = threading.Event()
    q: queue.Queue[str | None] = queue.Queue()
    thread = threading.Thread(
        target=stream_container_logs,
        args=(
            django_container,
            q,
            stop_event,
            log_file_path,
            max_log_lines,
            200,
        ),
        daemon=True,
    )
    thread.start()
    try:
        while not stop_event.is_set():
            try:
                line = q.get(timeout=0.1)
                if line is None:
                    break
                print(line)
            except queue.Empty:
                pass
    except KeyboardInterrupt:
        stop_event.set()
        print("\nDetached from container logs.")
