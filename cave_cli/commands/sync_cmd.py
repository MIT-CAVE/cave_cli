import argparse
import os
import shutil
import tempfile

from cave_cli.commands.reset import reset
from cave_cli.utils.constants import HTTPS_URL
from cave_cli.utils.display import (
    print_section,
    step_done,
    step_start,
    print_key_value,
)
from cave_cli.utils.git import clone
from cave_cli.utils.logger import logger
from cave_cli.utils.sync import sync_files
from cave_cli.utils.validate import confirm_action, find_app_dir


def sync_cmd(args: argparse.Namespace, do_reset: bool = True) -> bool:
    """
    Usage:

    - Merges files from another git repository into the current CAVE app

    Requires:

    - ``args``:
        - Type: argparse.Namespace
        - What: Parsed CLI arguments

    Optional:

    - ``do_reset``:
        - Type: bool
        - What: Whether to run cave reset after syncing files
        - Default: True

    Returns:

    - ``success``:
        - Type: bool
        - What: True if sync completed successfully, False otherwise
    """
    app_dir = find_app_dir()
    auto_yes = getattr(args, "yes", False)

    if not auto_yes:
        confirm_action(
            "This will reset your docker containers and database. "
            "It will also potentially update your local files"
        )

    print_section("Sync")

    url = getattr(args, "url", None)
    if not url:
        logger.error("--url is required for sync")
        return False

    branch = getattr(args, "branch", None)
    includes = getattr(args, "include", None) or []
    excludes = getattr(args, "exclude", None) or []

    print_key_value("App Location", app_dir)
    print_key_value("Using Repo", url)
    print_key_value("Using Branch", branch or "default")
    print("")

    step_start("Downloading repo to sync")
    temp_dir = tempfile.mkdtemp()
    success = clone(url, temp_dir, branch=branch)

    if not success or not os.listdir(temp_dir):
        step_done("Downloading repo to sync")
        logger.error(
            f"Failed!\n"
            f"Ensure you have access rights to the repository: {url}\n"
            f"Ensure you specified a valid branch: {branch}."
        )
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False
    step_done("Downloading repo to sync")

    step_start("Syncing files")
    sync_files(
        source=temp_dir,
        dest=app_dir,
        includes=includes,
        excludes=excludes,
    )
    step_done("Syncing files")

    shutil.rmtree(temp_dir, ignore_errors=True)

    if do_reset:
        reset_args = argparse.Namespace(
            yes=True,
            verbose=getattr(args, "verbose", False),
            loglevel=getattr(args, "loglevel", "INFO"),
        )
        code = reset(reset_args)
        if isinstance(code, int) and code != 0:
            return False

    logger.success("Sync complete.")
    return True
