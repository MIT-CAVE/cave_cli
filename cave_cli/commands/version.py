import argparse
import re

from cave_cli import __version__
from cave_cli.utils.display import print_key_value, print_section
from cave_cli.utils.env import parse_env
from cave_cli.utils.logger import logger
from cave_cli.utils.validate import get_app


def version(args: argparse.Namespace) -> None:
    """
    Usage:

    - Prints the CLI version and app-specific versions if inside a CAVE app directory
    """
    print_section("CAVE CLI")
    print_key_value("CLI Version", __version__)
    print_app_versions()


def print_app_versions() -> None:
    try:
        app_dir, app_name = get_app()
    except SystemExit:
        return

    from pathlib import Path

    print_section(f"{app_name} Versions")

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

    print_key_value("CAVE App", cave_app_version)
    print_key_value("CAVE Static", cave_static_version)
    print_key_value("CAVE Utils", cave_utils_version)
    print("")
