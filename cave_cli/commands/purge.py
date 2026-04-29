import argparse
import os
import shutil
import sys

from cave_cli.utils.display import print_section, step_done, step_start
from cave_cli.utils.docker import (
    remove_containers,
    remove_image,
    remove_volume,
)
from cave_cli.utils.logger import logger
from cave_cli.utils.subprocess import run_and_log
from cave_cli.utils.validate import confirm_action, validate_app_dir


def purge(args: argparse.Namespace) -> None:
    """
    Usage:

    - Removes a CAVE app and all its Docker resources
    """
    app_path = args.path
    if not os.path.isdir(app_path):
        logger.error(f"No directory {app_path}")
        sys.exit(1)

    abs_path = os.path.abspath(app_path)
    errors = validate_app_dir(abs_path)
    if errors:
        logger.error("Ensure you specified a valid CAVE app directory")
        sys.exit(1)

    app_name = os.path.basename(abs_path)

    auto_yes = getattr(args, "yes", False)
    if not auto_yes:
        confirm_action(
            "This will permanently remove all data associated "
            f"with your CAVE App ({app_name})"
        )

    print_section(f"Purging {app_name}")

    remove_containers(app_name, skip_header=True)

    step_start("Removing database volume")
    remove_volume(app_name)
    step_done("Removing database volume")

    step_start("Removing Redis volume")
    remove_volume(app_name, "redis_volume")
    step_done("Removing Redis volume")

    step_start("Removing image")
    remove_image(app_name)
    step_done("Removing image")

    step_start("Removing files")
    try:
        shutil.rmtree(abs_path)
    except PermissionError:
        logger.debug(
            "Some files are owned by root (created by Docker). "
            "Removing via Docker..."
        )
        run_and_log([
            "docker", "run", "--rm",
            "-v", f"{abs_path}:/purge",
            "alpine", "rm", "-rf", "/purge",
        ])
        if os.path.isdir(abs_path):
            try:
                shutil.rmtree(abs_path)
            except PermissionError:
                step_done("Removing files")
                logger.error(
                    "Couldn't remove files. "
                    "You may need elevated permissions."
                )
                sys.exit(1)
    step_done("Removing files")
    logger.success("Purge complete.")
