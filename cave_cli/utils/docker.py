import subprocess
import sys

from cave_cli.utils.display import (
    print_section,
    step_done,
    step_fail,
    step_start,
)
from cave_cli.utils.logger import logger
from cave_cli.utils.subprocess import run, run_and_log, version_tuple


def build_image(
    app_name: str,
    path: str,
    tag: str | None = None,
    exit_on_error: bool = True,
) -> bool:
    """
    Usage:

    - Builds a Docker image for the CAVE app

    Requires:

    - ``app_name``:
        - Type: str
        - What: The app name

    - ``path``:
        - Type: str
        - What: The build context directory

    Optional:

    - ``tag``:
        - Type: str | None
        - What: Custom Docker image tag
        - Default: None (defaults to f"cave-app:{app_name}")

    - ``exit_on_error``:
        - Type: bool
        - What: Whether to call sys.exit(1) on build failure
        - Default: True

    Returns:

    - ``success``:
        - Type: bool
        - What: True if the image built successfully, False otherwise

    Notes:

    - Streams build output and checks for ERROR lines
    - Exits with code 1 if an error is detected during the build (when exit_on_error=True)
    """
    image_tag = tag or f"cave-app:{app_name}"
    step_start("Building Docker image")
    has_error = False
    error_lines: list[str] = []
    process = subprocess.Popen(
        ["docker", "build", ".", "--tag", image_tag],
        cwd=path,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    for line in process.stdout:
        line = line.rstrip()
        if "ERROR" in line:
            has_error = True
            error_lines.append(line)
        logger.debug(line)
    process.wait()
    if has_error or process.returncode != 0:
        step_fail("Building Docker image", "\n".join(error_lines[-8:]))
        logger.error(
            "An ERROR was returned during the Docker container build process."
        )
        if exit_on_error:
            logger.error(
                "Consider running your command again in verbose mode "
                "to get more information."
            )
            logger.error("EG: 'cave reset --verbose' or 'cave run --verbose'")
            sys.exit(1)
        return False
    step_done("Building Docker image")
    return True


def create_network(app_name: str) -> None:
    """
    Usage:

    - Creates a Docker network for the CAVE app

    Requires:

    - ``app_name``:
        - Type: str
        - What: The app name used in the network name
    """
    run_and_log(["docker", "network", "create", f"cave-net:{app_name}"])


def remove_network(app_name: str) -> None:
    """
    Usage:

    - Removes the Docker network for the CAVE app

    Requires:

    - ``app_name``:
        - Type: str
        - What: The app name used in the network name
    """
    run_and_log(["docker", "network", "rm", f"cave-net:{app_name}"])


def run_detached(
    name: str,
    image: str,
    network: str | None = None,
    volumes: list[str] | None = None,
    env_vars: dict[str, str] | None = None,
    extra_args: list[str] | None = None,
    command: list[str] | None = None,
) -> None:
    """
    Usage:

    - Runs a Docker container in detached mode

    Requires:

    - ``name``:
        - Type: str
        - What: The container name

    - ``image``:
        - Type: str
        - What: The Docker image to run

    Optional:

    - ``network``:
        - Type: str | None
        - What: Docker network to attach to
        - Default: None

    - ``volumes``:
        - Type: list[str] | None
        - What: Volume mount specifications
        - Default: None

    - ``env_vars``:
        - Type: dict[str, str] | None
        - What: Environment variables to set
        - Default: None

    - ``extra_args``:
        - Type: list[str] | None
        - What: Additional docker run arguments
        - Default: None

    - ``command``:
        - Type: list[str] | None
        - What: Command to run in the container
        - Default: None
    """
    cmd = ["docker", "run", "-d"]
    if extra_args:
        cmd.extend(extra_args)
    if network:
        cmd.extend(["--network", network])
    for vol in volumes or []:
        cmd.extend(["--volume", vol])
    for key, val in (env_vars or {}).items():
        cmd.extend(["-e", f"{key}={val}"])
    cmd.extend(["--name", name])
    cmd.append(image)
    if command:
        cmd.extend(command)
    run_and_log(cmd)


def run_interactive(
    name: str,
    image: str,
    network: str | None = None,
    ports: list[str] | None = None,
    volumes: list[str] | None = None,
    env_vars: dict[str, str] | None = None,
    extra_args: list[str] | None = None,
    command: list[str] | None = None,
) -> None:
    """
    Usage:

    - Runs a Docker container interactively with TTY passthrough

    Requires:

    - ``name``:
        - Type: str
        - What: The container name

    - ``image``:
        - Type: str
        - What: The Docker image to run

    Optional:

    - ``network``:
        - Type: str | None
        - What: Docker network to attach to
        - Default: None

    - ``ports``:
        - Type: list[str] | None
        - What: Port mapping specifications
        - Default: None

    - ``volumes``:
        - Type: list[str] | None
        - What: Volume mount specifications
        - Default: None

    - ``env_vars``:
        - Type: dict[str, str] | None
        - What: Environment variables to set
        - Default: None

    - ``extra_args``:
        - Type: list[str] | None
        - What: Additional docker run arguments
        - Default: None

    - ``command``:
        - Type: list[str] | None
        - What: Command to run in the container
        - Default: None
    """
    cmd = ["docker", "run", "-it"]
    if extra_args:
        cmd.extend(extra_args)
    for port in ports or []:
        cmd.extend(["-p", port])
    if network:
        cmd.extend(["--network", network])
    for vol in volumes or []:
        cmd.extend(["--volume", vol])
    for key, val in (env_vars or {}).items():
        cmd.extend(["-e", f"{key}={val}"])
    cmd.extend(["--name", name])
    cmd.append(image)
    if command:
        cmd.extend(command)
    run(cmd, inherit_io=True)


def run_detached_logged(
    name: str,
    image: str,
    network: str | None = None,
    ports: list[str] | None = None,
    volumes: list[str] | None = None,
    env_vars: dict[str, str] | None = None,
    extra_args: list[str] | None = None,
    command: list[str] | None = None,
) -> subprocess.CompletedProcess:
    """
    Usage:

    - Runs a Docker container in detached mode with optional port mappings.

    Requires:

    - ``name``:
        - Type: str
        - What: The container name

    - ``image``:
        - Type: str
        - What: The Docker image to run

    Optional:

    - ``network``:
        - Type: str | None
        - What: Docker network to attach to
        - Default: None

    - ``ports``:
        - Type: list[str] | None
        - What: Port mapping specifications (e.g. ["8000:8000"])
        - Default: None

    - ``volumes``:
        - Type: list[str] | None
        - What: Volume mount specifications
        - Default: None

    - ``env_vars``:
        - Type: dict[str, str] | None
        - What: Environment variables to set
        - Default: None

    - ``extra_args``:
        - Type: list[str] | None
        - What: Additional docker run arguments
        - Default: None

    - ``command``:
        - Type: list[str] | None
        - What: Command to run in the container
        - Default: None

    Returns:

    - ``result``:
        - Type: subprocess.CompletedProcess
        - What: The completed process result so callers can check returncode

    Notes:

    - Used for the Django container in TUI mode so logs can be streamed
      via ``docker logs -f`` while the terminal remains under dashboard control.
    """
    cmd = ["docker", "run", "-d"]
    if extra_args:
        cmd.extend(extra_args)
    for port in ports or []:
        cmd.extend(["-p", port])
    if network:
        cmd.extend(["--network", network])
    for vol in volumes or []:
        cmd.extend(["--volume", vol])
    for key, val in (env_vars or {}).items():
        cmd.extend(["-e", f"{key}={val}"])
    cmd.extend(["--name", name])
    cmd.append(image)
    if command:
        cmd.extend(command)
    return run_and_log(cmd)


def stream_container_logs(
    container_name: str,
    log_queue: "queue.Queue[str | None]",
    stop_event: "threading.Event",
    log_file_path: str | None = None,
    max_log_lines: int = 500,
    tail: int | str | None = None,
) -> None:
    """
    Usage:

    - Streams logs from a running container into a queue and optional rotating file.

    Requires:

    - ``container_name``:
        - Type: str
        - What: The name of the Docker container to follow.

    - ``log_queue``:
        - Type: queue.Queue[str | None]
        - What: Queue to push raw log lines into; None sentinel on exit.

    - ``stop_event``:
        - Type: threading.Event
        - What: When set, causes the streamer to terminate promptly.

    Optional:

    - ``log_file_path``:
        - Type: str | None
        - What: File path to save the rotating tail of container log lines
        - Default: None

    - ``max_log_lines``:
        - Type: int
        - What: Maximum number of recent log lines to maintain in log_file_path
        - Default: 500

    - ``tail``:
        - Type: int | str | None
        - What: Number of recent log lines to show initially, or None to stream from now
        - Default: None

    Notes:

    - Designed to run as a daemon thread.
    - Always puts a None sentinel into the queue before returning so the
      display loop can detect container exit.
    """
    import os
    import queue as _queue
    import subprocess
    import threading as _threading

    log_file = None
    lines_since_trim = 0
    if log_file_path and max_log_lines > 0:
        try:
            os.makedirs(
                os.path.dirname(os.path.abspath(log_file_path)), exist_ok=True
            )
            # Prune previous session's logs if they exceed max_log_lines
            if os.path.exists(log_file_path):
                try:
                    with open(
                        log_file_path, "r", encoding="utf-8", errors="replace"
                    ) as f:
                        prior_lines = f.readlines()
                    if len(prior_lines) > max_log_lines:
                        with open(log_file_path, "w", encoding="utf-8") as f:
                            f.writelines(prior_lines[-max_log_lines:])
                except Exception:
                    pass
            log_file = open(log_file_path, "a", encoding="utf-8", buffering=1)
        except Exception:
            log_file = None

    from cave_cli.utils.log_parser import LogParser

    log_parser = LogParser()

    cmd = ["docker", "logs", "-f"]
    if tail is not None:
        cmd.extend(["--tail", str(tail)])
    else:
        cmd.extend(["--since", "0s"])
    cmd.append(container_name)

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    def _watch_stop() -> None:
        stop_event.wait()
        try:
            process.terminate()
        except Exception:
            pass

    watcher = _threading.Thread(target=_watch_stop, daemon=True)
    watcher.start()

    try:
        for line in process.stdout:
            if stop_event.is_set():
                break
            stripped = line.rstrip()
            log_queue.put(stripped)
            if log_file is not None:
                try:
                    parsed = log_parser.parse_line(stripped)
                    formatted = log_parser.format_line(parsed, color=False)
                    log_file.write(formatted + "\n")
                    log_file.flush()
                    lines_since_trim += 1
                    # Trim periodically if the file grows significantly beyond max_log_lines
                    if lines_since_trim >= max_log_lines * 2:
                        log_file.close()
                        try:
                            with open(
                                log_file_path,
                                "r",
                                encoding="utf-8",
                                errors="replace",
                            ) as f:
                                all_lines = f.readlines()
                            if len(all_lines) > max_log_lines:
                                tmp_p = f"{log_file_path}.tmp"
                                with open(tmp_p, "w", encoding="utf-8") as f:
                                    f.writelines(all_lines[-max_log_lines:])
                                os.replace(tmp_p, log_file_path)
                        except Exception:
                            pass
                        log_file = open(
                            log_file_path, "a", encoding="utf-8", buffering=1
                        )
                        lines_since_trim = 0
                except Exception:
                    pass
    finally:
        if log_file is not None:
            try:
                log_file.flush()
                log_file.close()
            except Exception:
                pass
        if (
            log_file_path
            and max_log_lines > 0
            and os.path.exists(log_file_path)
        ):
            try:
                with open(
                    log_file_path, "r", encoding="utf-8", errors="replace"
                ) as f:
                    final_lines = f.readlines()
                if len(final_lines) > max_log_lines:
                    tmp_p = f"{log_file_path}.tmp"
                    with open(tmp_p, "w", encoding="utf-8") as f:
                        f.writelines(final_lines[-max_log_lines:])
                    os.replace(tmp_p, log_file_path)
            except Exception:
                pass
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
        log_queue.put(None)


def is_container_ready(name: str, user: str) -> bool:
    """
    Usage:

    - Checks if a Postgres container is ready to accept connections

    Requires:

    - ``name``:
        - Type: str
        - What: The container name

    - ``user``:
        - Type: str
        - What: The database user to check with

    Returns:

    - ``ready``:
        - Type: bool
        - What: True if ready, False otherwise
    """
    result = run(
        ["docker", "exec", name, "pg_isready", "-U", user],
        capture=True,
    )
    return result.returncode == 0


def is_db_initialized(name: str, user: str, db: str) -> bool:
    """
    Usage:

    - Checks if the Django migrations table exists in the database

    Requires:

    - ``name``:
        - Type: str
        - What: The container name

    - ``user``:
        - Type: str
        - What: The database user

    - ``db``:
        - Type: str
        - What: The database name

    Returns:

    - ``initialized``:
        - Type: bool
        - What: True if initialized, False otherwise
    """
    result = run(
        [
            "docker",
            "exec",
            name,
            "psql",
            "-U",
            user,
            "-d",
            db,
            "-c",
            "SELECT 1 FROM django_migrations LIMIT 1;",
        ],
        capture=True,
    )
    return result.returncode == 0


def save_redis(app_name: str) -> None:
    """
    Usage:

    - Persists Redis data before container termination

    Requires:

    - ``app_name``:
        - Type: str
        - What: The app name
    """
    run_and_log(
        ["docker", "exec", f"{app_name}_redis_host", "redis-cli", "save"]
    )


def remove_containers(app_name: str, skip_header: bool = False) -> None:
    """
    Usage:

    - Removes all Docker containers for a CAVE app

    Requires:

    - ``app_name``:
        - Type: str
        - What: The app name

    Optional:

    - ``skip_header``:
        - Type: bool
        - What: Whether to skip the "Shutting Down" section header
        - Default: False
    """
    if not skip_header:
        print_section(f"Shutting Down {app_name}")

    step_start("Persisting cache")
    save_redis(app_name)
    step_done("Persisting cache")

    step_start("Removing containers")
    containers = [
        f"{app_name}_django",
        f"{app_name}_nginx_host",
        f"{app_name}_db_host",
        f"{app_name}_redis_host",
    ]
    run_and_log(["docker", "rm", "--force"] + containers)
    step_done("Removing containers")

    step_start("Removing network")
    remove_network(app_name)
    step_done("Removing network")


def remove_volume(app_name: str, suffix: str = "pg_volume") -> None:
    """
    Usage:

    - Removes a Docker volume for a CAVE app

    Requires:

    - ``app_name``:
        - Type: str
        - What: The app name

    Optional:

    - ``suffix``:
        - Type: str
        - What: The volume name suffix
        - Default: "pg_volume"
    """
    logger.debug(f"Removing Docker DB Volume for App ({app_name})...")
    run_and_log(["docker", "volume", "rm", f"{app_name}_{suffix}"])


def remove_image(app_name: str) -> None:
    """
    Usage:

    - Removes the Docker image for a CAVE app

    Requires:

    - ``app_name``:
        - Type: str
        - What: The app name
    """
    logger.debug(f"Removing Docker Images for App ({app_name})...")
    run_and_log(["docker", "rmi", f"cave-app:{app_name}"])


def get_running_apps() -> list[str]:
    """
    Usage:

    - Lists all running CAVE app names

    Returns:

    - ``apps``:
        - Type: list[str]
        - What: A list of app names derived from container names
    """
    result = run(["docker", "ps", "--format", "{{.Names}}"])
    apps: list[str] = []
    if result.returncode != 0 or not result.stdout:
        return apps
    for line in result.stdout.strip().splitlines():
        if (
            line.endswith("_django")
            and not line.endswith("_test_django")
            and not line.endswith("_task_django")
        ):
            apps.append(line.replace("_django", ""))
    return apps


def get_running_task_servers() -> list[str]:
    """
    Usage:

    - Lists all CAVE apps with running task servers

    Returns:

    - ``apps``:
        - Type: list[str]
        - What: App names that have an active task server
    """
    result = run(["docker", "ps", "--format", "{{.Names}}"])
    apps: list[str] = []
    if result.returncode != 0 or not result.stdout:
        return apps
    for line in result.stdout.strip().splitlines():
        if line.endswith("_task_django"):
            apps.append(line.replace("_task_django", ""))
        elif line.endswith("_test_django"):
            apps.append(line.replace("_test_django", ""))
    return apps


get_running_test_servers = get_running_task_servers


def get_container_env(container: str, var: str) -> str:
    """
    Usage:

    - Gets an environment variable value from a running container

    Requires:

    - ``container``:
        - Type: str
        - What: The container name

    - ``var``:
        - Type: str
        - What: The environment variable name

    Returns:

    - ``value``:
        - Type: str
        - What: The variable value, or empty string if not found
    """
    import re

    result = run(
        [
            "docker",
            "inspect",
            "-f",
            "{{.Config.Env}}",
            container,
        ]
    )
    if result.returncode != 0 or not result.stdout:
        return ""
    match = re.search(rf"{var}=([^\s\]]*)", result.stdout)
    return match.group(1) if match else ""


def get_container_host_port(container: str) -> str:
    """
    Usage:

    - Gets the host port mapping for a container's port 8000

    Requires:

    - ``container``:
        - Type: str
        - What: The container name

    Returns:

    - ``port``:
        - Type: str
        - What: The host port, or empty string if not found
    """
    result = run(
        [
            "docker",
            "inspect",
            "-f",
            '{{(index (index .NetworkSettings.Ports "8000/tcp") 0).HostPort}}',
            container,
        ]
    )
    if result.returncode != 0 or not result.stdout:
        return ""
    return result.stdout.strip()


def get_container_exit_code(container: str) -> int | None:
    """
    Usage:

    - Retrieves the exit code of a stopped Docker container.

    Requires:

    - ``container``:
        - Type: str
        - What: Name or ID of the Docker container.

    Returns:

    - ``exit_code``:
        - Type: int | None
        - What: The exit code of the container, or None if it could not be determined.
    """
    result = run(
        [
            "docker",
            "inspect",
            "-f",
            "{{.State.ExitCode}}",
            container,
        ]
    )
    if result.returncode != 0 or not result.stdout:
        return None
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def get_all_containers(pattern: str) -> list[str]:
    """
    Usage:

    - Lists all container names matching a pattern suffix

    Requires:

    - ``pattern``:
        - Type: str
        - What: The suffix pattern to match (e.g. "_django")

    Returns:

    - ``containers``:
        - Type: list[str]
        - What: A list of matching container names
    """
    result = run(["docker", "ps", "-a", "--format", "{{.Names}}"])
    containers: list[str] = []
    if result.returncode != 0 or not result.stdout:
        return containers
    for line in result.stdout.strip().splitlines():
        if line.endswith(pattern):
            containers.append(line)
    return containers


def generate_secret_key(app_name: str) -> str | None:
    """
    Usage:

    - Generates a Django secret key using the app's Docker image

    Requires:

    - ``app_name``:
        - Type: str
        - What: The app name (used as the image tag)

    Returns:

    - ``key``:
        - Type: str | None
        - What: The generated secret key, or None if generation failed
    """
    result = run(
        [
            "docker",
            "run",
            "--rm",
            f"cave-app:{app_name}",
            "python",
            "-c",
            "from django.core.management.utils import get_random_secret_key; "
            "print(get_random_secret_key())",
        ]
    )
    if result.returncode != 0 or not result.stdout:
        return None
    return result.stdout.strip()
