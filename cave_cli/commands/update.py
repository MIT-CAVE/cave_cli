import argparse
import subprocess
import sys
import tempfile

from cave_cli.utils.display import step_done, step_start
from cave_cli.utils.logger import logger
from cave_cli.commands.doctor import check_uv

UV_DOCS_URL = "https://docs.astral.sh/uv/"
CLI_REPO_URL = "https://github.com/MIT-CAVE/cave_cli.git"


def update(args: argparse.Namespace) -> None:
    """
    Usage:

    - Updates the CAVE CLI via uv.

    Notes:

    - Without ``--version``, upgrades to the latest version from PyPI via
      ``uv tool upgrade cave_cli``.
    - With ``--version``, reinstalls via ``uv tool install --reinstall`` from
      the specified git tag or branch.
    - On Windows, the update runs in a new console window because Windows
      locks running executables and cave.exe cannot replace itself.
    """
    has_uv, uv_message, uv_path= check_uv()
    if not has_uv:
        logger.error(uv_message)
        logger.error(f"The cave_cli package may need to be updated manually based on how it was installed.")
        sys.exit(1)

    version = getattr(args, "version", None)
    if version:
        label = f"Reinstalling CAVE CLI ({version})"
        cmd = [uv_path, "tool", "install", "--reinstall", f"cave_cli @ git+{CLI_REPO_URL}@{version}"]
    else:
        label = "Updating CAVE CLI"
        cmd = [uv_path, "tool", "upgrade", "cave_cli"]

    step_start(label)

    if sys.platform == "win32":
        # Windows locks running executables, so cave.exe cannot be replaced
        # while this process is alive. Write a temp batch file and spawn a
        # new console window that waits for this process to exit first.
        # A batch file avoids quoting issues with paths containing spaces.
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".bat", delete=False
        ) as f:
            f.write("@echo off\r\n")
            f.write("timeout /t 1 /nobreak >nul\r\n")
            f.write(" ".join(f'"{c}"' for c in cmd) + "\r\n")
            f.write('del "%~f0"\r\n')
            bat_path = f.name
        subprocess.Popen(
            ["cmd", "/k", bat_path],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        step_done(label)
        logger.success("CAVE CLI update started in a new window.")
        return

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
