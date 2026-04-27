import argparse
import shutil
import subprocess
import sys

from cave_cli.utils.logger import logger

PIPX_DOCS_URL = "https://pipx.pypa.io/stable/installation/"


def uninstall(args: argparse.Namespace) -> None:
    """
    Usage:

    - Removes the CAVE CLI package via pipx.
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

    pipx = shutil.which("pipx")
    if not pipx:
        logger.error(
            "pipx not found. Please uninstall cave_cli manually."
        )
        logger.error(f"See: {PIPX_DOCS_URL}")
        sys.exit(1)

    logger.info("Removing installation...")
    result = subprocess.run(
        [pipx, "uninstall", "cave_cli"],
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
