import argparse
import subprocess
import sys

from cave_cli.utils.logger import logger


def uninstall(args: argparse.Namespace) -> None:
    """
    Usage:

    - Removes the CAVE CLI package
    """
    try:
        response = input(
            "Are you sure you want to uninstall CAVE CLI? [y/N] "
        )
    except (EOFError, KeyboardInterrupt):
        print()
        logger.error("Uninstall canceled")
        return

    if response.strip().lower() not in ("y", "yes"):
        logger.error("Uninstall canceled")
        return

    logger.info("Removing installation...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "uninstall", "cave_cli", "-y"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode == 0:
        logger.info("Done.")
    else:
        logger.error("Failed to uninstall CAVE CLI.")
        if result.stderr:
            logger.error(result.stderr.strip())
