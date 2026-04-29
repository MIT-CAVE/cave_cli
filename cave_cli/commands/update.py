import argparse
import shutil
import subprocess
import sys

from cave_cli.utils.display import step_done, step_start
from cave_cli.utils.logger import logger

PIPX_DOCS_URL = "https://pipx.pypa.io/stable/installation/"
CLI_REPO_URL = "https://github.com/MIT-CAVE/cave_cli.git"


def _force_install(pipx: str, version: str) -> subprocess.CompletedProcess:
    spec = f"cave_cli @ git+{CLI_REPO_URL}@{version}"
    return subprocess.run(
        [pipx, "install", "--force", spec],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def update(args: argparse.Namespace) -> None:
    """
    Usage:

    - Updates the CAVE CLI via pipx.

    Notes:

    - Without ``--version``, runs ``pipx upgrade cave_cli``.  If that fails
      (e.g. the original install branch no longer exists), falls back to
      ``pipx install --force`` from the ``main`` branch.
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
        label = f"Reinstalling CAVE CLI ({version})"
        step_start(label)
        result = _force_install(pipx, version)
    else:
        label = "Updating CAVE CLI"
        step_start(label)
        result = subprocess.run(
            [pipx, "upgrade", "cave_cli"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            # The original install spec may point to a branch that no longer
            # exists (e.g. a feature branch that was merged and deleted).
            # Fall back to a fresh install from main.
            result = _force_install(pipx, "main")

    if result.returncode == 0:
        step_done(label)
        logger.success("CAVE CLI updated.")
    else:
        logger.error("Failed to update CAVE CLI.")
        if result.stderr:
            logger.error(result.stderr.strip())
