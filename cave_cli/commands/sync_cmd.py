import argparse
import os
import shutil
import tempfile

from cave_cli.commands.reset import reset
from cave_cli.utils.constants import HTTPS_URL
from cave_cli.utils.git import clone
from cave_cli.utils.logger import logger
from cave_cli.utils.sync import sync_files
from cave_cli.utils.validate import confirm_action, find_app_dir


def sync_cmd(args: argparse.Namespace) -> None:
    """
    Usage:

    - Merges files from another git repository into the current CAVE app
    """
    app_dir = find_app_dir()
    auto_yes = getattr(args, "yes", False)

    if not auto_yes:
        confirm_action(
            "This will reset your docker containers and database. "
            "It will also potentially update your local files"
        )

    logger.header("Sync:")

    url = getattr(args, "url", None)
    if not url:
        logger.error("--url is required for sync")
        return

    branch = getattr(args, "branch", None)
    includes = getattr(args, "include", None) or []
    excludes = getattr(args, "exclude", None) or []

    logger.info("Syncing files with the following parameters:\n")
    logger.info(f"App Location: {app_dir}")
    logger.info(f"Using Repo: {url}")
    logger.info(f"Using Branch: {branch or 'default'}\n")
    logger.info("Downloading repo to sync...")

    temp_dir = tempfile.mkdtemp()
    success = clone(url, temp_dir, branch=branch)

    if not success or not os.listdir(temp_dir):
        logger.error(
            f"Failed!\n"
            f"Ensure you have access rights to the repository: {url}\n"
            f"Ensure you specified a valid branch: {branch}."
        )
        shutil.rmtree(temp_dir, ignore_errors=True)
        return

    logger.info("Done")
    logger.info("Syncing files...")

    sync_files(
        source=temp_dir,
        dest=app_dir,
        includes=includes,
        excludes=excludes,
    )

    logger.info("Done")

    shutil.rmtree(temp_dir, ignore_errors=True)

    reset_args = argparse.Namespace(
        yes=True,
        verbose=getattr(args, "verbose", False),
        loglevel=getattr(args, "loglevel", "INFO"),
    )
    reset(reset_args)

    logger.info("Sync complete.")
