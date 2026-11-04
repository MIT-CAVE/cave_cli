import argparse
import shlex
import sys
from pathlib import Path

from cave_cli.commands.task import schedule_task
from cave_cli.utils.display import print_section
from cave_cli.utils.validate import get_app


def prettify(args: argparse.Namespace) -> None:
    """
    Usage:

    - Runs code formatting on the CAVE app as a task in the warm task runner

    Requires:

    - ``args``:
        - Type: argparse.Namespace
        - What: Parsed command-line arguments for prettify
    """
    app_dir, app_name = get_app()
    print_section("Prettify")

    remaining = getattr(args, "remaining", []) or []
    docker_args_str = getattr(args, "docker_args", "") or ""
    extra_docker_args = shlex.split(docker_args_str) if docker_args_str else []
    detached = getattr(args, "detached", False)

    # Target script: prefer utils/prettify.py, fallback to ./utils/prettify.sh
    if (Path(app_dir) / "utils" / "prettify.py").exists():
        target = "utils/prettify.py"
    elif (Path(app_dir) / "utils" / "prettify.sh").exists():
        target = "./utils/prettify.sh"
    else:
        target = "utils/prettify.py"

    exit_code = schedule_task(
        app_dir=app_dir,
        app_name=app_name,
        command=[target] + remaining,
        detached=detached,
        docker_args=extra_docker_args,
        display_command="prettify",
    )
    if exit_code != 0:
        sys.exit(exit_code)
