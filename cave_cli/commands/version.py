import argparse
import re

from cave_cli import __version__
from cave_cli.utils.constants import CHAR_LINE
from cave_cli.utils.env import parse_env
from cave_cli.utils.logger import logger
from cave_cli.utils.validate import find_app_dir, get_app


def version(args: argparse.Namespace) -> None:
    """
    Usage:

    - Prints the CLI version and app-specific versions if inside a CAVE app directory
    """
    logger.info(f"CAVE_CLI={__version__}")
    print_app_versions()


def print_app_versions() -> None:
    try:
        app_dir, app_name = get_app()
    except SystemExit:
        return

    from pathlib import Path

    logger.header(f"{app_name} versions:")

    version_file = Path(app_dir) / "VERSION"
    cave_app_version = (
        version_file.read_text().strip()
        if version_file.is_file()
        else "Unknown"
    )

    req_file = Path(app_dir) / "requirements.txt"
    cave_utils_version = "Unknown"
    if req_file.is_file():
        for line in req_file.read_text().splitlines():
            if "cave_utils" in line:
                parts = line.split("==")
                if len(parts) == 2:
                    cave_utils_version = f"v{parts[1].strip()}"
                break

    env_file = Path(app_dir) / ".env"
    cave_static_version = "Unknown"
    if env_file.is_file():
        env_vars = parse_env(str(env_file))
        static_url = env_vars.get("STATIC_APP_URL", "")
        if "localhost" in static_url:
            cave_static_version = "Local"
        else:
            static_path = env_vars.get("STATIC_APP_URL_PATH", "")
            if static_path:
                match = re.search(r"[0-9]+\.[0-9]+\.[0-9]+", static_path)
                if match:
                    cave_static_version = f"v{match.group(0)}"

    logger.info(f"CAVE_APP={cave_app_version}")
    logger.info(f"CAVE_STATIC={cave_static_version}")
    logger.info(f"CAVE_UTILS={cave_utils_version}")
