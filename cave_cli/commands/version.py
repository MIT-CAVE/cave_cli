import argparse
import re

from cave_cli import __version__
from cave_cli.utils.display import print_key_value, print_section
from cave_cli.utils.env import parse_env
from cave_cli.utils.logger import logger
from cave_cli.utils.validate import get_app
from cave_cli.utils.version import get_app_version, get_version_from_req_list


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

    pyproject_file = Path(app_dir) / "pyproject.toml"
    req_file = Path(app_dir) / "requirements.txt"

    cave_app_version = get_app_version(app_dir)
    cave_static_version = "Unknown"
    cave_utils_version = "Unknown"

    if pyproject_file.is_file():
        try:
            import tomllib

            with open(pyproject_file, "rb") as f:
                pyproject_data = tomllib.load(f)
            deps = pyproject_data.get("project", {}).get("dependencies", [])
            cave_utils_version = get_version_from_req_list("cave_utils", deps)
        except Exception:
            pass
    if req_file.is_file() and cave_utils_version == "Unknown":
        try:
            req_strings = req_file.read_text().splitlines()
            cave_utils_version = get_version_from_req_list(
                "cave_utils", req_strings
            )
        except Exception:
            pass

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
