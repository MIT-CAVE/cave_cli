import argparse
import shutil
import subprocess
import sys

from cave_cli.utils.display import step_done, step_start
from cave_cli.utils.logger import logger

PIPX_DOCS_URL = "https://pipx.pypa.io/stable/installation/"
CLI_REPO_URL = "https://github.com/MIT-CAVE/cave_cli.git"


def update(args: argparse.Namespace) -> None:
    """
    Usage:

    - Updates the CAVE CLI via pipx.

    Notes:

    - Without ``--version``, installs the latest version from PyPI via
      ``pipx install --force cave_cli``.
    - With ``--version``, reinstalls via ``pipx install --force`` from the
      specified git tag or branch.
    - On Windows, the update runs in a new console window because Windows
      locks running executables and cave.exe cannot replace itself.
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
        spec = f"cave_cli @ git+{CLI_REPO_URL}@{version}"
    else:
        label = "Updating CAVE CLI"
        spec = "cave_cli"

    step_start(label)

    if sys.platform == "win32":
        # Windows locks running executables, so cave.exe cannot be replaced
        # while this process is alive. Spawn a new console window that waits
        # for this process to exit before running the update.
        subprocess.Popen(
            [
                "cmd",
                "/k",
                f'timeout /t 1 /nobreak >nul && "{pipx}" install --force "{spec}"',
            ],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        step_done(label)
        logger.success("CAVE CLI update started in a new window.")
        return

    result = subprocess.run(
        [pipx, "install", "--force", spec],
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
