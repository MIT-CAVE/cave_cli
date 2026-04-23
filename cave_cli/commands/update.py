import argparse
import subprocess
import sys

from cave_cli.utils.logger import logger


def update(args: argparse.Namespace) -> None:
    """
    Usage:

    - Updates the CAVE CLI via pip install --upgrade
    """
    logger.info("Updating CAVE CLI...")
    version = getattr(args, "version", None)
    if version:
        spec = (
            f"cave_cli @ "
            f"git+https://github.com/MIT-CAVE/cave_cli.git@{version}"
        )
    else:
        spec = (
            "cave_cli @ "
            "git+https://github.com/MIT-CAVE/cave_cli.git@main"
        )
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", spec],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode == 0:
        logger.info("Done.")
        logger.info("CAVE CLI updated.")
    else:
        logger.error("Failed to update CAVE CLI.")
        if result.stderr:
            logger.error(result.stderr.strip())
