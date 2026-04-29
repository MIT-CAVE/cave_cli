import os
import sys
from pathlib import Path

from cave_cli.utils.constants import (
    CURRENT_ENV_VARIABLES,
    RETIRED_ENV_VARIABLES,
    INVALID_NAME_END_RE,
    INVALID_NAME_HYPHEN_UNDER_RE,
    INVALID_NAME_START_RE,
    INVALID_NAME_UNDER_HYPHEN_RE,
    VALID_NAME_RE,
)
from cave_cli.utils.display import YELLOW, RESET
from cave_cli.utils.logger import logger


def validate_app_name(name: str) -> str | None:
    """
    Usage:

    - Validates a CAVE app name against naming rules

    Requires:

    - ``name``:
        - Type: str
        - What: The app name to validate

    Returns:

    - ``error``:
        - Type: str | None
        - What: An error message if invalid, or None if valid
    """
    if len(name) < 2 or len(name) > 255:
        return "The app name needs to be two to 255 characters"
    if not VALID_NAME_RE.match(name):
        return (
            "The app name can only contain lowercase letters, "
            "numbers, hyphens (-), and underscores (_)"
        )
    if INVALID_NAME_START_RE.match(name):
        return (
            "The app name cannot start with a hyphen (-) "
            "or an underscore (_)"
        )
    if INVALID_NAME_END_RE.match(name):
        return (
            "The app name cannot end with a hyphen (-) "
            "or an underscore (_)"
        )
    if INVALID_NAME_HYPHEN_UNDER_RE.search(name):
        return (
            "The app name cannot contain a hyphen (-) "
            "followed by an underscore (_)"
        )
    if INVALID_NAME_UNDER_HYPHEN_RE.search(name):
        return (
            "The app name cannot contain an underscore (_) "
            "followed by a hyphen (-)"
        )
    return None


def validate_app_dir(path: str) -> list[str]:
    """
    Usage:

    - Checks if a directory is a valid CAVE app directory

    Requires:

    - ``path``:
        - Type: str
        - What: The path to validate

    Returns:

    - ``errors``:
        - Type: list[str]
        - What: A list of error messages. Empty if the directory is valid.
    """
    p = Path(path)
    errors: list[str] = []

    if not (p / "manage.py").is_file() or not (p / "cave_core").is_dir():
        return ["Not a CAVE app directory"]

    for folder in ("cave_api", "cave_app", "cave_core"):
        if not (p / folder).is_dir():
            errors.append(
                f"The folder '{folder}' is missing "
                "in the root project directory."
            )

    for file in (".env", "manage.py", "requirements.txt", "Dockerfile"):
        if not (p / file).is_file():
            errors.append(
                f"The file '{file}' is missing "
                "in the root project directory."
            )

    env_path = p / ".env"
    if env_path.is_file():
        from cave_cli.utils.env import parse_env

        env_vars = parse_env(str(env_path))
        for var in CURRENT_ENV_VARIABLES:
            if var not in env_vars:
                errors.append(
                    f"The env variable '{var}' is missing "
                    "from the '.env' file."
                )
        for var in RETIRED_ENV_VARIABLES:
            if var in env_vars:
                errors.append(
                    f"The env variable '{var}' is retired and "
                    "should be removed from the '.env' file."
                )

    if not (p / "Dockerfile").is_file():
        errors.append("No Dockerfile found in current directory.")

    return errors


def find_app_dir(start: str | None = None) -> str:
    """
    Usage:

    - Walks up the directory tree to find a valid CAVE app directory

    Optional:

    - ``start``:
        - Type: str | None
        - What: The starting directory to search from
        - Default: None (uses current working directory)

    Returns:

    - ``path``:
        - Type: str
        - What: The absolute path to the CAVE app directory
    """
    path = Path(start or os.getcwd()).resolve()
    while True:
        errors = validate_app_dir(str(path))
        if not errors:
            return str(path)
        parent = path.parent
        if parent == path:
            for err in errors:
                logger.error(err)
            logger.error("Ensure you are in a valid CAVE app directory")
            sys.exit(1)
        path = parent


def get_app(start: str | None = None) -> tuple[str, str]:
    """
    Usage:

    - Finds the CAVE app directory and returns its path and name

    Optional:

    - ``start``:
        - Type: str | None
        - What: The starting directory to search from
        - Default: None (uses current working directory)

    Returns:

    - ``app_dir``:
        - Type: str
        - What: The absolute path to the CAVE app directory

    - ``app_name``:
        - Type: str
        - What: The base name of the app directory
    """
    app_dir = find_app_dir(start)
    app_name = Path(app_dir).resolve().name
    return app_dir, app_name


def confirm_action(message: str, auto_yes: bool = False) -> None:
    """
    Usage:

    - Prompts the user for confirmation before proceeding

    Requires:

    - ``message``:
        - Type: str
        - What: The action description to display

    Optional:

    - ``auto_yes``:
        - Type: bool
        - What: If True, bypasses the prompt and continues
        - Default: False
    """
    if auto_yes:
        return
    try:
        response = input(f"\n  {YELLOW}⚠{RESET}  {message}. \n  Continue? [y/N] ")
    except (EOFError, KeyboardInterrupt):
        print()
        logger.error("Operation canceled.")
        sys.exit(1)
    if response.strip().lower() not in ("y", "yes"):
        logger.error("Operation canceled.")
        sys.exit(1)
