import argparse
import os
import re
import shutil
import tempfile

from cave_cli.commands.create import remove_licence_info
from cave_cli.commands.run import run_cave
from cave_cli.commands.sync_cmd import sync_cmd
from cave_cli.utils.constants import HTTPS_URL
from cave_cli.utils.display import print_section, step_done, step_start
from cave_cli.utils.env import upgrade_env
from cave_cli.utils.git import clone
from cave_cli.utils.logger import logger
from cave_cli.utils.validate import confirm_action, find_app_dir, get_app
from cave_cli.utils.version import get_app_version, is_breaking_change, version_tuple


def upgrade(args: argparse.Namespace) -> None:
    """
    Usage:

    - Upgrades the CAVE app in the current directory from the template repository
    """
    auto_yes = getattr(args, "yes", False)
    app_dir, app_name = get_app()
    url = getattr(args, "url", None) or HTTPS_URL
    version = getattr(args, "version", None)
    skip_env_upgrade = getattr(args, "skip_env_upgrade", False)

    current_v = get_app_version(app_dir)
    target_v = version or "main"

    temp_dir = None
    # If target version is not a clear version tag, or if we need it for env upgrade anyway, clone it
    if not version_tuple(target_v) or not skip_env_upgrade:
        step_start(f"Fetching target version ({target_v})")
        temp_dir = tempfile.mkdtemp()
        clone(url, temp_dir, branch=version or "main")
        if not version_tuple(target_v):
            target_v = get_app_version(temp_dir)
        step_done(f"Target version identified as {target_v}")

    msg = "This will potentially update all files not in 'cave_api/' or '.env' and reset your database"
    if is_breaking_change(current_v, target_v):
        msg = f"Upgrading from {current_v} to {target_v} is a BREAKING CHANGE. {msg}"

    confirm_action(msg, auto_yes=auto_yes)

    print_section("Upgrade")
    logger.info("Upgrading CAVE App via a Sync operation...")

    sync_args = argparse.Namespace(
        url=url,
        branch=version or "main",
        include=["cave_api/docs"],
        exclude=[".env", ".gitignore", "cave_api/*"],
        yes=True,
        verbose=getattr(args, "verbose", False),
        loglevel=getattr(args, "loglevel", "INFO"),
    )
    sync_cmd(sync_args)

    if not skip_env_upgrade:
        step_start("Upgrading environment file")
        # temp_dir should already be created and cloned if not skipped
        if not temp_dir:
            temp_dir = tempfile.mkdtemp()
            clone(url, temp_dir, branch=version or "main")
        env_path = os.path.join(app_dir, ".env")
        upgrade_env(env_path, temp_dir)
        step_done("Upgrading environment file")

    if temp_dir:
        shutil.rmtree(temp_dir, ignore_errors=True)

    remove_licence_info(app_dir)

    step_start("Updating LLM docs")
    docs_args = argparse.Namespace(
        entrypoint="./utils/generate_docs.sh",
        interactive=False,
        it=False,
        docker_args="",
        ip_port=None,
        yes=True,
        verbose=getattr(args, "verbose", False),
        loglevel=getattr(args, "loglevel", "INFO"),
    )
    run_cave(app_dir, app_name, docs_args)
    step_done("Updating LLM docs")

    logger.success("Upgrade complete.")
