import argparse
import shutil
import subprocess
import sys

from cave_cli.utils.display import RED, RESET, step_done, step_start
from cave_cli.utils.logger import logger
from cave_cli.commands.doctor import check_uv


def uninstall(args: argparse.Namespace) -> None:
    """
    Usage:

    - Removes the CAVE CLI package via uv.
    """
    try:
        response = input(
            f"\n  {RED}⚠{RESET}  Are you sure you want to uninstall CAVE CLI? [y/N] "
        )
    except (EOFError, KeyboardInterrupt):
        print()
        logger.error("Uninstall canceled")
        return

    if response.strip().lower() not in ("y", "yes"):
        logger.error("Uninstall canceled")
        return

    has_uv, uv_message, uv_path = check_uv()
    if not has_uv:
        logger.error(uv_message)
        logger.error(
            f"You may need to uninstall CAVE CLI manually based on how it was installed."
        )
        sys.exit(1)

    step_start("Removing installation")
    result = subprocess.run(
        [uv_path, "tool", "uninstall", "cave_cli"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode == 0:
        step_done("Removing installation")
        logger.success("Uninstall complete.")
    else:
        logger.error("Failed to uninstall CAVE CLI.")
        if result.stderr:
            logger.error(result.stderr.strip())
