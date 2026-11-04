import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from cave_cli.utils.cache import get_cache_dir
from cave_cli.utils.display import step_done, step_fail, step_start
from cave_cli.utils.docker import (
    build_image,
    is_container_ready,
    is_db_initialized,
    run_and_log,
    run_detached,
)
from cave_cli.utils.env import parse_env
from cave_cli.utils.logger import logger
from cave_cli.utils.subprocess import run
from cave_cli.utils.task_queue import is_process_alive


def get_task_django_name(app_name: str) -> str:
    """
    Usage:

    - Resolves the container name for the task Django application

    Requires:

    - ``app_name``:
        - Type: str
        - What: The name of the CAVE application

    Returns:

    - ``name``:
        - Type: str
        - What: The task Django container name
    """
    return f"{app_name}_task_django"


def get_task_db_name(app_name: str) -> str:
    """
    Usage:

    - Resolves the container name for the task database

    Requires:

    - ``app_name``:
        - Type: str
        - What: The name of the CAVE application

    Returns:

    - ``name``:
        - Type: str
        - What: The task database container name
    """
    return f"{app_name}_task_db_host"


def get_task_redis_name(app_name: str) -> str:
    """
    Usage:

    - Resolves the container name for the task cache

    Requires:

    - ``app_name``:
        - Type: str
        - What: The name of the CAVE application

    Returns:

    - ``name``:
        - Type: str
        - What: The task cache container name
    """
    return f"{app_name}_task_redis_host"


def get_task_network(app_name: str) -> str:
    """
    Usage:

    - Resolves the Docker network name for the task environment

    Requires:

    - ``app_name``:
        - Type: str
        - What: The name of the CAVE application

    Returns:

    - ``name``:
        - Type: str
        - What: The task Docker network name
    """
    return f"cave-net-task:{app_name}"


def get_task_image(app_name: str) -> str:
    """
    Usage:

    - Resolves the Docker image tag for the task environment

    Requires:

    - ``app_name``:
        - Type: str
        - What: The name of the CAVE application

    Returns:

    - ``tag``:
        - Type: str
        - What: The task Docker image tag
    """
    return f"cave-app-task:{app_name}"


def get_task_activity_path(app_dir: str, app_name: str) -> str:
    """
    Usage:

    - Resolves the file path used to store task runner activity timestamps

    Requires:

    - ``app_dir``:
        - Type: str
        - What: The root directory of the CAVE application

    - ``app_name``:
        - Type: str
        - What: The name of the CAVE application

    Returns:

    - ``path``:
        - Type: str
        - What: Absolute path to the activity json file
    """
    project_root = str(Path(app_dir).resolve())
    project_hash = hashlib.sha256(project_root.encode("utf-8")).hexdigest()[:16]
    return os.path.join(
        get_cache_dir(), f"task_server_{app_name}_{project_hash}_activity.json"
    )


def touch_task_activity(app_dir: str, app_name: str) -> None:
    """
    Usage:

    - Updates the last active timestamp for the persistent task server

    Requires:

    - ``app_dir``:
        - Type: str
        - What: The root directory of the CAVE application

    - ``app_name``:
        - Type: str
        - What: The name of the CAVE application
    """
    path = get_task_activity_path(app_dir, app_name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"last_active": time.time()}, f)
    except Exception as exc:
        logger.debug(f"Failed to touch task activity: {exc}")


def get_last_task_activity(app_dir: str, app_name: str) -> float:
    """
    Usage:

    - Retrieves the last active timestamp for the persistent task server

    Requires:

    - ``app_dir``:
        - Type: str
        - What: The root directory of the CAVE application

    - ``app_name``:
        - Type: str
        - What: The name of the CAVE application

    Returns:

    - ``timestamp``:
        - Type: float
        - What: Epoch seconds of last activity or 0.0 if not found
    """
    path = get_task_activity_path(app_dir, app_name)
    if not os.path.exists(path):
        return 0.0
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return float(data.get("last_active", 0.0))
    except Exception:
        return 0.0


def is_container_running(name: str) -> bool:
    """
    Usage:

    - Checks if a specific Docker container is currently running

    Requires:

    - ``name``:
        - Type: str
        - What: Container name to inspect

    Returns:

    - ``running``:
        - Type: bool
        - What: True if container exists and is running, False otherwise
    """
    res = run(
        ["docker", "inspect", "-f", "{{.State.Running}}", name],
        capture=True,
    )
    return res.returncode == 0 and res.stdout.strip() == "true"


def is_task_server_running(app_name: str) -> bool:
    """
    Usage:

    - Checks if the isolated task server stack is actively running

    Requires:

    - ``app_name``:
        - Type: str
        - What: The name of the CAVE application

    Returns:

    - ``running``:
        - Type: bool
        - What: True if task db, redis, and django containers are running
    """
    expected = [
        get_task_django_name(app_name),
        get_task_db_name(app_name),
        get_task_redis_name(app_name),
    ]
    return all(is_container_running(name) for name in expected)


def start_task_server(
    app_dir: str,
    app_name: str,
    extra_docker_args: list[str] | None = None,
) -> None:
    """
    Usage:

    - Starts the isolated task runner stack (network, database, cache, Django)

    Requires:

    - ``app_dir``:
        - Type: str
        - What: The root directory of the CAVE application

    - ``app_name``:
        - Type: str
        - What: The name of the CAVE application

    Optional:

    - ``extra_docker_args``:
        - Type: list[str] | None
        - What: Additional Docker arguments
        - Default: None
    """
    # Clean up any legacy test containers if found
    legacy_containers = [
        f"{app_name}_test_django",
        f"{app_name}_test_db_host",
        f"{app_name}_test_redis_host",
    ]
    for c in legacy_containers:
        if is_container_running(c):
            run(["docker", "rm", "-f", c])

    task_image = get_task_image(app_name)
    task_network = get_task_network(app_name)
    db_container = get_task_db_name(app_name)
    redis_container = get_task_redis_name(app_name)
    django_container = get_task_django_name(app_name)
    pg_volume = f"{app_name}_task_pg_volume"
    redis_volume = f"{app_name}_task_redis_volume"

    # Build task image if it does not exist
    img_check = run(["docker", "image", "inspect", task_image], capture=True)
    if img_check.returncode != 0:
        build_image(app_name, app_dir, tag=task_image)

    env_vars = parse_env(f"{app_dir}/.env")
    db_password = env_vars.get("DATABASE_PASSWORD", "")
    db_image = env_vars.get("DATABASE_IMAGE", "postgres:latest")
    db_command_str = env_vars.get(
        "DATABASE_COMMAND", "postgres -c listen_addresses=*"
    )
    if not db_command_str:
        db_command_str = "postgres -c listen_addresses=*"
    cache_image = env_vars.get("CACHE_IMAGE", "valkey/valkey:7")
    if not cache_image:
        cache_image = "valkey/valkey:7"

    # Ensure task network exists
    run_and_log(["docker", "network", "create", task_network])

    # Start task database (no host port binding)
    if not is_container_running(db_container):
        step_start("Starting task database")
        run(["docker", "rm", "-f", db_container])
        run_detached(
            name=db_container,
            image=db_image,
            network=task_network,
            volumes=[f"{pg_volume}:/var/lib/postgresql/data"],
            env_vars={
                "POSTGRES_PASSWORD": db_password,
                "POSTGRES_USER": f"{app_name}_user",
                "POSTGRES_DB": f"{app_name}_name",
            },
            extra_args=extra_docker_args or None,
            command=db_command_str.split(),
        )
        step_done("Starting task database")

    # Start task cache (no host port binding)
    if not is_container_running(redis_container):
        step_start("Starting task cache")
        run(["docker", "rm", "-f", redis_container])
        run_detached(
            name=redis_container,
            image=cache_image,
            network=task_network,
            volumes=[f"{redis_volume}:/data"],
            extra_args=extra_docker_args or None,
            command=["--save", "7200", "1"],
        )
        step_done("Starting task cache")

    # Wait for task database readiness
    db_user = f"{app_name}_user"
    db_name = f"{app_name}_name"
    step_start("Checking task database")
    ready = False
    for _ in range(30):
        if is_container_ready(db_container, db_user):
            ready = True
            break
        time.sleep(1)

    if not ready:
        step_fail("Checking task database", "Database failed to become ready.")
        stop_task_server(app_name)
        sys.exit(1)

    django_env = {
        "DATABASE_HOST": db_container,
        "DATABASE_USER": db_user,
        "DATABASE_PASSWORD": db_password,
        "DATABASE_NAME": db_name,
        "DATABASE_PORT": "5432",
        "REDIS_HOST": redis_container,
        "REDIS_PORT": "6379",
    }
    django_volumes = [f"{app_dir}:/app"]

    if not is_db_initialized(db_container, db_user, db_name):
        step_done("Checking task database")
        step_start("Initializing task database")
        setup_container = f"{app_name}_task_setup"
        cmd = [
            "docker",
            "run",
            "--rm",
            "--name",
            setup_container,
            "--network",
            task_network,
            "--volume",
            f"{app_dir}:/app",
        ]
        for k, v in django_env.items():
            cmd.extend(["-e", f"{k}={v}"])
        cmd.extend([task_image, "./utils/reset_db.sh"])
        res = run_and_log(cmd)
        if res.returncode != 0:
            step_fail("Initializing task database")
            stop_task_server(app_name)
            sys.exit(1)
        step_done("Initializing task database")
    else:
        step_done("Checking task database")

    # Start idle Django container
    if not is_container_running(django_container):
        step_start("Starting task Django container")
        run(["docker", "rm", "-f", django_container])
        run_detached(
            name=django_container,
            image=task_image,
            network=task_network,
            volumes=django_volumes,
            env_vars=django_env,
            extra_args=extra_docker_args or None,
            command=["tail", "-f", "/dev/null"],
        )
        if not is_container_running(django_container):
            step_fail(
                "Starting task Django container",
                "Failed to start task container.",
            )
            stop_task_server(app_name)
            sys.exit(1)
        step_done("Starting task Django container")


def stop_task_server(app_name: str, app_dir: str | None = None) -> None:
    """
    Usage:

    - Stops and removes all containers and network for the isolated task server

    Requires:

    - ``app_name``:
        - Type: str
        - What: The name of the CAVE application

    Optional:

    - ``app_dir``:
        - Type: str | None
        - What: The root directory of the CAVE application
        - Default: None
    """
    containers = [
        get_task_django_name(app_name),
        get_task_db_name(app_name),
        get_task_redis_name(app_name),
        # Also clean up any legacy test containers
        f"{app_name}_test_django",
        f"{app_name}_test_db_host",
        f"{app_name}_test_redis_host",
    ]
    run_and_log(["docker", "rm", "--force"] + containers)
    task_network = get_task_network(app_name)
    run_and_log(["docker", "network", "rm", task_network])
    # Also clean up legacy test network
    run_and_log(["docker", "network", "rm", f"cave-net-test:{app_name}"])

    if app_dir:
        from cave_cli.utils.task_queue import clean_completed_tasks

        clean_completed_tasks(app_dir)


def reset_task_server(
    app_dir: str,
    app_name: str,
    extra_docker_args: list[str] | None = None,
) -> None:
    """
    Usage:

    - Tears down the task server, removes database volume, rebuilds image, and restarts

    Requires:

    - ``app_dir``:
        - Type: str
        - What: The root directory of the CAVE application

    - ``app_name``:
        - Type: str
        - What: The name of the CAVE application

    Optional:

    - ``extra_docker_args``:
        - Type: list[str] | None
        - What: Additional Docker arguments
        - Default: None
    """
    step_start("Resetting task server")
    stop_task_server(app_name, app_dir=app_dir)

    from cave_cli.utils.task_queue import reset_task_registry

    reset_task_registry(app_dir)

    pg_volume = f"{app_name}_task_pg_volume"
    redis_volume = f"{app_name}_task_redis_volume"
    run_and_log(
        [
            "docker",
            "volume",
            "rm",
            "-f",
            pg_volume,
            redis_volume,
            f"{app_name}_test_pg_volume",
            f"{app_name}_test_redis_volume",
        ]
    )
    step_done("Resetting task server")

    task_image = get_task_image(app_name)
    build_image(app_name, app_dir, tag=task_image)
    start_task_server(app_dir, app_name, extra_docker_args)


def run_command_in_task_server(
    app_name: str,
    command: list[str] | str,
    command_args: list[str] | None = None,
    extra_env: dict[str, str] | None = None,
    log_file: Any | None = None,
) -> int:
    """
    Usage:

    - Executes a command inside the warm task Django container

    Requires:

    - ``app_name``:
        - Type: str
        - What: The name of the CAVE application

    - ``command``:
        - Type: list[str] | str
        - What: Command or script to execute in the container (e.g. "./utils/prettify.sh")

    Optional:

    - ``command_args``:
        - Type: list[str] | None
        - What: Additional arguments to pass to the command
        - Default: None

    - ``extra_env``:
        - Type: dict[str, str] | None
        - What: Extra environment variables for the process
        - Default: None

    - ``log_file``:
        - Type: Any | None
        - What: Open file object to redirect process output to
        - Default: None

    Returns:

    - ``exit_code``:
        - Type: int
        - What: The return code of the command
    """
    django_container = get_task_django_name(app_name)

    if log_file is not None:
        cmd = ["docker", "exec", "-i"]
        if extra_env:
            for k, v in extra_env.items():
                cmd.extend(["-e", f"{k}={v}"])
        cmd.append(django_container)
        if isinstance(command, list):
            cmd.extend(command)
        else:
            cmd.append(command)
        if command_args:
            cmd.extend(command_args)

        proc = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
        )
        proc.wait()
        return proc.returncode

    cmd = ["docker", "exec"]
    if sys.stdin.isatty():
        cmd.append("-it")
    else:
        cmd.append("-i")

    if extra_env:
        for k, v in extra_env.items():
            cmd.extend(["-e", f"{k}={v}"])

    cmd.append(django_container)
    if isinstance(command, list):
        cmd.extend(command)
    else:
        cmd.append(command)
    if command_args:
        cmd.extend(command_args)

    result = run(cmd, inherit_io=True)
    return result.returncode


def run_test_in_task_server(
    app_name: str,
    command_args: list[str],
    extra_env: dict[str, str],
) -> int:
    """
    Usage:

    - Executes the test suite inside the warm task Django container

    Requires:

    - ``app_name``:
        - Type: str
        - What: The name of the CAVE application

    - ``command_args``:
        - Type: list[str]
        - What: Arguments to pass to ./utils/run_test.sh

    - ``extra_env``:
        - Type: dict[str, str]
        - What: Extra environment variables for the test process

    Returns:

    - ``exit_code``:
        - Type: int
        - What: The return code of the test command
    """
    return run_command_in_task_server(
        app_name=app_name,
        command="./utils/run_test.sh",
        command_args=command_args,
        extra_env=extra_env,
    )


def get_task_watcher_pid_path(app_dir: str, app_name: str) -> str:
    """
    Usage:

    - Resolves the pid file path for the background idle watcher

    Requires:

    - ``app_dir``:
        - Type: str
        - What: The root directory of the CAVE application

    - ``app_name``:
        - Type: str
        - What: The name of the CAVE application

    Returns:

    - ``path``:
        - Type: str
        - What: Absolute path to the watcher pid file
    """
    project_root = str(Path(app_dir).resolve())
    project_hash = hashlib.sha256(project_root.encode("utf-8")).hexdigest()[:16]
    return os.path.join(
        get_cache_dir(), f"task_server_{app_name}_{project_hash}_watcher.pid"
    )


def ensure_task_idle_watcher(
    app_dir: str, app_name: str, keep_alive_minutes: int
) -> None:
    """
    Usage:

    - Ensures a background idle watcher is running for the persistent task server

    Requires:

    - ``app_dir``:
        - Type: str
        - What: The root directory of the CAVE application

    - ``app_name``:
        - Type: str
        - What: The name of the CAVE application

    - ``keep_alive_minutes``:
        - Type: int
        - What: Minutes to wait before stopping idle task server
    """
    if keep_alive_minutes <= 0:
        return

    pid_path = get_task_watcher_pid_path(app_dir, app_name)
    if os.path.exists(pid_path):
        try:
            with open(pid_path, "r", encoding="utf-8") as f:
                pid = int(f.read().strip())
            if is_process_alive(pid):
                return
        except Exception:
            pass

    cmd = [
        sys.executable,
        "-m",
        "cave_cli.cli",
        "_task-watcher",
        app_dir,
        app_name,
        str(keep_alive_minutes),
    ]
    kwargs: dict = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }
    if sys.platform != "win32":
        kwargs["start_new_session"] = True
    else:
        kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        )

    try:
        proc = subprocess.Popen(cmd, **kwargs)
        os.makedirs(os.path.dirname(pid_path), exist_ok=True)
        with open(pid_path, "w", encoding="utf-8") as f:
            f.write(str(proc.pid))
    except Exception as exc:
        logger.debug(f"Failed to spawn idle watcher: {exc}")


def run_task_idle_watcher(
    app_dir: str, app_name: str, keep_alive_minutes: int
) -> None:
    """
    Usage:

    - Loops in the background and shuts down task server after idle timeout

    Requires:

    - ``app_dir``:
        - Type: str
        - What: The root directory of the CAVE application

    - ``app_name``:
        - Type: str
        - What: The name of the CAVE application

    - ``keep_alive_minutes``:
        - Type: int
        - What: Minutes of inactivity before teardown
    """
    from cave_cli.utils.task_queue import TaskQueueLock, is_process_alive

    timeout_seconds = keep_alive_minutes * 60
    while True:
        time.sleep(15)
        if not is_task_server_running(app_name):
            break

        last_active = get_last_task_activity(app_dir, app_name)
        if last_active > 0 and (time.time() - last_active) >= timeout_seconds:
            # Check if a task is currently queued or executing
            lock = TaskQueueLock(app_dir, app_name, timeout=1.0)
            try:
                lock.acquire()
                last_active_locked = get_last_task_activity(app_dir, app_name)
                if (
                    last_active_locked > 0
                    and (time.time() - last_active_locked) >= timeout_seconds
                ):
                    stop_task_server(app_name, app_dir=app_dir)
                    break
            except Exception:
                pass
            finally:
                lock.release()

    pid_path = get_task_watcher_pid_path(app_dir, app_name)
    try:
        if os.path.exists(pid_path):
            os.remove(pid_path)
    except Exception:
        pass


# ============================================================================ #
# Backward Compatibility Aliases                                              #
# ============================================================================ #
get_test_django_name = get_task_django_name
get_test_db_name = get_task_db_name
get_test_redis_name = get_task_redis_name
get_test_network = get_task_network
get_test_image = get_task_image
get_test_activity_path = get_task_activity_path
touch_test_activity = touch_task_activity
get_last_test_activity = get_last_task_activity
is_test_server_running = is_task_server_running
start_test_server = start_task_server
stop_test_server = stop_task_server
reset_test_server = reset_task_server
run_command_in_server = run_command_in_task_server
run_test_in_server = run_test_in_task_server
get_test_watcher_pid_path = get_task_watcher_pid_path
ensure_idle_watcher = ensure_task_idle_watcher
run_idle_watcher = run_task_idle_watcher
