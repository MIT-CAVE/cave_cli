import re
from pathlib import Path

HTTPS_URL: str = "https://github.com/MIT-CAVE/cave_app.git"
MIN_DOCKER_VERSION: str = "23.0.6"
CAVE_PATH: Path = Path.home() / ".cave_cli"
CHAR_LINE: str = "============================="

VALID_NAME_RE: re.Pattern = re.compile(r"^[a-z0-9_-]+$")
INVALID_NAME_START_RE: re.Pattern = re.compile(r"^[-_]+.*$")
INVALID_NAME_END_RE: re.Pattern = re.compile(r"^.*[-_]+$")
INVALID_NAME_HYPHEN_UNDER_RE: re.Pattern = re.compile(r"(-_)+")
INVALID_NAME_UNDER_HYPHEN_RE: re.Pattern = re.compile(r"(_-)+")

IP_PORT_RE: re.Pattern = re.compile(
    r"([0-9]{1,3}\.)+([0-9]{1,3}):[0-9][0-9][0-9][0-9]+"
)

CURRENT_ENV_VARIABLES: tuple[str, ...] = (
    "DATABASE_IMAGE",
    "DATABASE_PASSWORD",
    "DJANGO_ADMIN_EMAIL",
    "DJANGO_ADMIN_FIRST_NAME",
    "DJANGO_ADMIN_LAST_NAME",
    "DJANGO_ADMIN_PASSWORD",
    "DJANGO_ADMIN_USERNAME",
    "SECRET_KEY",
    "STATIC_APP_URL",
    "STATIC_APP_URL_PATH",
)

RETIRED_ENV_VARIABLES: tuple[str, ...] = (
    "DATABASE_HOST",
    "DATABASE_PORT",
    "DATABASE_NAME",
    "DATABASE_USER",
)

VALID_REPOS: tuple[str, ...] = (
    "cave_app",
    "cave_static",
    "cave_cli",
    "cave_utils",
)
