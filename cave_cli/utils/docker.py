import subprocess
import sys

from cave_cli.utils.logger import logger
from cave_cli.utils.subprocess import run, run_and_log, version_tuple


def check_docker() -> None:
    """
    Usage:

    - Validates that Docker is installed, running, and meets the minimum version

    Notes:

    - Exits with code 1 if Docker is not installed, not running, or too old
    """
    from cave_cli.utils.constants import MIN_DOCKER_VERSION

    try:
        result = run(["docker", "--version"])
    except FileNotFoundError:
        logger.error(
            f"Docker is not installed. "
            f"Please install Docker version {MIN_DOCKER_VERSION} or greater.\n"
            f"For more information see: https://docs.docker.com/get-docker/"
        )
        sys.exit(1)

    if result.returncode != 0 or not result.stdout:
        logger.error(
            f"Could not determine Docker version. "
            f"Please install Docker version {MIN_DOCKER_VERSION} or greater."
        )
        sys.exit(1)

    version_str = result.stdout.strip()
    import re

    match = re.search(r"(\d+\.\d+\.\d+)", version_str)
    if not match:
        logger.error(f"Could not parse Docker version from: {version_str}")
        sys.exit(1)

    current = match.group(1)
    if version_tuple(current) < version_tuple(MIN_DOCKER_VERSION):
        logger.error(
            f"Your current Docker version ({current}) is too old.\n"
            f"Please install Docker version {MIN_DOCKER_VERSION} or greater.\n"
            f"For more information see: https://docs.docker.com/get-docker/"
        )
        sys.exit(1)

    info_result = run(["docker", "info"])
    if info_result.returncode != 0:
        logger.error(
            "Docker not running... Please start Docker and try again!"
        )
        sys.exit(1)

    logger.debug("Docker Check Passed!")


def build_image(app_name: str, path: str) -> None:
    """
    Usage:

    - Builds a Docker image for the CAVE app

    Requires:

    - ``app_name``:
        - Type: str
        - What: The app name used for tagging the image

    - ``path``:
        - Type: str
        - What: The build context directory

    Notes:

    - Streams build output and checks for ERROR lines
    - Exits with code 1 if an error is detected during the build
    """
    from cave_cli.utils.display import step_done, step_fail, step_start

    remove_containers(app_name)
    step_start("Building Docker image")
    has_error = False
    error_lines: list[str] = []
    process = subprocess.Popen(
        ["docker", "build", ".", "--tag", f"cave-app:{app_name}"],
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
        logger.error(
            "Consider running your command again in verbose mode "
            "to get more information."
        )
        logger.error("EG: 'cave reset --verbose' or 'cave run --verbose'")
        sys.exit(1)
    step_done("Building Docker image")


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
) -> None:
    """
    Usage:

    - Streams logs from a running container into a queue.

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

    Notes:

    - Designed to run as a daemon thread.
    - Always puts a None sentinel into the queue before returning so the
      display loop can detect container exit.
    """
    import queue as _queue
    import threading as _threading

    process = subprocess.Popen(
        ["docker", "logs", "-f", "--since", "0s", container_name],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        for line in process.stdout:
            if stop_event.is_set():
                break
            log_queue.put(line.rstrip())
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
        log_queue.put(None)


def save_redis(app_name: str) -> None:
    """
    Usage:

    - Persists Redis data before container termination

    Requires:

    - ``app_name``:
        - Type: str
        - What: The app name
    """
    logger.debug(
        "Persisting Redis Data prior to Redis Container Termination..."
    )
    run_and_log(
        ["docker", "exec", f"{app_name}_redis_host", "redis-cli", "save"]
    )


def remove_containers(app_name: str) -> None:
    """
    Usage:

    - Removes all Docker containers for a CAVE app

    Requires:

    - ``app_name``:
        - Type: str
        - What: The app name
    """
    save_redis(app_name)
    logger.debug(f"Killing Running App ({app_name})...")
    containers = [
        f"{app_name}_django",
        f"{app_name}_nginx_host",
        f"{app_name}_db_host",
        f"{app_name}_redis_host",
    ]
    run_and_log(["docker", "rm", "--force"] + containers)
    remove_network(app_name)


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
    result = run(
        ["docker", "ps", "--format", "{{.Names}}"]
    )
    apps: list[str] = []
    if result.returncode != 0 or not result.stdout:
        return apps
    for line in result.stdout.strip().splitlines():
        if line.endswith("_django"):
            apps.append(line.replace("_django", ""))
    return apps


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
            "{{(index (index .NetworkSettings.Ports \"8000/tcp\") 0).HostPort}}",
            container,
        ]
    )
    if result.returncode != 0 or not result.stdout:
        return ""
    return result.stdout.strip()


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
    result = run(
        ["docker", "ps", "-a", "--format", "{{.Names}}"]
    )
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
