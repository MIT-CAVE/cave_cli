import argparse

from cave_cli.utils.complete import get_completion_script, install_completion
from cave_cli.utils.logger import logger


def completion_cmd(args: argparse.Namespace) -> None:
    """
    Usage:

    - Outputs shell completion script or installs it to the user's shell rc file
    """
    should_install = getattr(args, "install", False)
    if should_install:
        target = install_completion()
        if target:
            logger.info(
                f"Shell completion successfully added to {target}.\n"
                f"Restart your shell or run: source {target}"
            )
        else:
            logger.warn(
                "Unable to detect shell rc file for completion install."
            )
        return

    print(get_completion_script(), end="")
