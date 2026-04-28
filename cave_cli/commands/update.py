import argparse
import shutil
import subprocess
import sys

from cave_cli.utils.display import step_done, step_start
from cave_cli.utils.logger import logger

PIPX_DOCS_URL = "https://pipx.pypa.io/stable/installation/"


def update(args: argparse.Namespace) -> None:
    """
    Usage:

    - Updates the CAVE CLI via pipx.

    Notes:

    - Without ``--version``, runs ``pipx upgrade cave_cli``.
    - With ``--version``, reinstalls via ``pipx install --force`` from the
      specified git tag or branch.
    """
    pipx = shutil.which("pipx")
    if not pipx:
        logger.error(
            "pipx not found. Please install pipx and reinstall cave_cli."
        )
        logger.error(f"See: {PIPX_DOCS_URL}")
        sys.exit(1)

    version = getattr(args, "version", None)
    if version:
        spec = (
            f"cave_cli @ "
            f"git+https://github.com/MIT-CAVE/cave_cli.git@{version}"
        )
        cmd = [pipx, "install", "--force", spec]
        label = f"Reinstalling CAVE CLI ({version})"
    else:
        cmd = [pipx, "upgrade", "cave_cli"]
        label = "Updating CAVE CLI"

    step_start(label)
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode == 0:
        step_done(label)
        logger.success("CAVE CLI updated.")
    else:
        logger.error("Failed to update CAVE CLI.")
        if result.stderr:
            logger.error(result.stderr.strip())
