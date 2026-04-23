import getpass
import re
import secrets
import string
from pathlib import Path

from cave_cli.utils.cache import prompt_cached_entry, load_entries, save_entry
from cave_cli.utils.constants import (
    CURRENT_ENV_VARIABLES,
    RETIRED_ENV_VARIABLES,
)
from cave_cli.utils.logger import logger


def parse_env(path: str) -> dict[str, str]:
    """
    Usage:

    - Parses a .env file into a dictionary of key-value pairs

    Requires:

    - ``path``:
        - Type: str
        - What: The path to the .env file

    Returns:

    - ``env_vars``:
        - Type: dict[str, str]
        - What: A dictionary mapping variable names to their values

    Notes:

    - Handles ``KEY=VALUE``, ``KEY='VALUE'``, and ``KEY="VALUE"`` formats
    - Ignores blank lines and lines starting with ``#``
    """
    env_vars: dict[str, str] = {}
    p = Path(path)
    if not p.is_file():
        return env_vars
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if (value.startswith("'") and value.endswith("'")) or (
            value.startswith('"') and value.endswith('"')
        ):
            value = value[1:-1]
        env_vars[key] = value
    return env_vars


def set_env_value(path: str, key: str, value: str) -> None:
    """
    Usage:

    - Sets or replaces a variable's value in a .env file

    Requires:

    - ``path``:
        - Type: str
        - What: The path to the .env file

    - ``key``:
        - Type: str
        - What: The variable name to set

    - ``value``:
        - Type: str
        - What: The value to assign
    """
    p = Path(path)
    lines = p.read_text().replace("\r\n", "\n").replace("\r", "\n").splitlines()
    pattern = re.compile(rf"^{re.escape(key)}\s*=")
    replaced = False
    for i, line in enumerate(lines):
        if pattern.match(line):
            lines[i] = f"{key}='{value}'"
            replaced = True
            break
    if not replaced:
        lines.append(f"{key}='{value}'")
    p.write_text("\n".join(lines) + "\n", newline="\n")


def validate_env(path: str) -> list[str]:
    """
    Usage:

    - Validates a .env file has all required variables and no retired ones

    Requires:

    - ``path``:
        - Type: str
        - What: The path to the .env file

    Returns:

    - ``errors``:
        - Type: list[str]
        - What: A list of error messages. Empty if valid.
    """
    errors: list[str] = []
    env_vars = parse_env(path)
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
    return errors


def upgrade_env(env_path: str, template_path: str) -> None:
    """
    Usage:

    - Upgrades the STATIC_APP_URL_PATH in .env from a template's example.env

    Requires:

    - ``env_path``:
        - Type: str
        - What: The path to the app's .env file

    - ``template_path``:
        - Type: str
        - What: The path to the cloned template directory
    """
    logger.info("Upgrading .env...")
    example_env = parse_env(str(Path(template_path) / "example.env"))
    new_url_path = example_env.get("STATIC_APP_URL_PATH", "")
    if new_url_path:
        set_env_value(env_path, "STATIC_APP_URL_PATH", new_url_path)
    logger.info("Done")


def generate_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def prompt_password(prompt: str) -> str:
    while True:
        password = getpass.getpass(prompt)
        if not password:
            password = generate_password()
            return password
        confirm = getpass.getpass("Retype password to confirm: ")
        if password == confirm:
            return password
        print("Passwords didn't match. Please try again")


def create_env_interactive(
    app_name: str,
    env_path: str,
    template_path: str,
    docker_secret_key: str | None = None,
) -> None:
    """
    Usage:

    - Interactively creates a .env file for a new CAVE app

    Requires:

    - ``app_name``:
        - Type: str
        - What: The name of the app being created

    - ``env_path``:
        - Type: str
        - What: The path where the .env file will be written

    - ``template_path``:
        - Type: str
        - What: The path to the example.env template

    Optional:

    - ``docker_secret_key``:
        - Type: str | None
        - What: A Django secret key generated via Docker
        - Default: None (generates locally with secrets module)
    """
    p = Path(env_path)
    template = Path(template_path)
    if template.is_file():
        content = template.read_text().replace("\r\n", "\n").replace("\r", "\n")
        p.write_text(content, newline="\n")
    elif p.is_file():
        pass
    else:
        p.touch()

    secret_key = docker_secret_key or secrets.token_urlsafe(50)
    set_env_value(env_path, "SECRET_KEY", secret_key)

    logger.header("Set up your new app environment (.env) variables:")

    logger.info(
        "If you want to use a globe view or mapbox maps, "
        "you will need a valid Mapbox Token."
    )
    logger.info(
        "This is not required, but will allow you to use "
        "the full functionality of the app."
    )
    logger.info(
        "Mapbox tokens can be created by making an account "
        "on 'https://mapbox.com'"
    )

    try:
        use_mapbox = input("Would you like to use Mapbox? [y/N] ")
    except (EOFError, KeyboardInterrupt):
        use_mapbox = "n"

    if use_mapbox.strip().lower() in ("y", "yes"):
        token = prompt_cached_entry(
            name="mapbox_tokens",
            prompt_new="Enter your Mapbox Public Token: ",
            prompt_label="Label for this token (e.g. work, personal): ",
            mask=True,
        )
        if token:
            set_env_value(env_path, "MAPBOX_TOKEN", token)
    else:
        logger.info("Mapbox skipped")

    default_email = f"{app_name}@example.com"
    print()
    email = prompt_cached_entry(
        name="admin_emails",
        prompt_new="Enter an admin email",
        prompt_label="Label for this email (e.g. work, personal): ",
        default=default_email,
    )
    if not email:
        email = default_email
    set_env_value(env_path, "DJANGO_ADMIN_EMAIL", email)

    print()
    admin_password = prompt_password(
        "Please input an admin password. "
        "Leave blank to randomly generate one: "
    )
    set_env_value(env_path, "DJANGO_ADMIN_PASSWORD", admin_password)

    db_password = generate_password()
    set_env_value(env_path, "DATABASE_PASSWORD", db_password)
    print()
