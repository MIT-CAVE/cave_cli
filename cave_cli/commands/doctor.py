import argparse
import sys

from cave_cli.utils.display import (
    print_section,
    step_done,
    step_fail,
    step_start,
)
from cave_cli.utils.logger import logger
from cave_cli.utils.subprocess import run, version_tuple


def check_git() -> tuple[bool, str]:
    """
    Usage:

    - Validates that git is installed

    Returns:

    - ``success``: bool
    - ``message``: str remediation or version
    """
    try:
        result = run(["git", "--version"])
        if result.returncode == 0:
            return True, result.stdout.strip()
    except FileNotFoundError:
        pass
    return (
        False,
        "git is not installed. Please install git: https://git-scm.com/",
    )


def check_pipx() -> tuple[bool, str]:
    """
    Usage:

    - Validates that pipx is installed

    Returns:

    - ``success``: bool
    - ``message``: str remediation or version
    """
    import shutil

    pipx = shutil.which("pipx")
    if pipx:
        try:
            result = run([pipx, "--version"])
            if result.returncode == 0:
                return True, f"pipx version {result.stdout.strip()}"
        except Exception:
            pass
    return (
        False,
        "pipx is not installed. Please install pipx: https://pipx.pypa.io/",
    )


def check_docker() -> tuple[bool, str]:
    """
    Usage:

    - Validates that Docker is installed, running, and meets the minimum version

    Returns:

    - ``success``: bool
    - ``message``: str remediation or version
    """
    from cave_cli.utils.constants import MIN_DOCKER_VERSION

    try:
        result = run(["docker", "--version"])
    except FileNotFoundError:
        return (
            False,
            f"Docker is not installed. "
            f"Please install Docker version {MIN_DOCKER_VERSION} or greater: "
            f"https://docs.docker.com/get-docker/",
        )

    if result.returncode != 0 or not result.stdout:
        return (
            False,
            f"Could determine Docker version. "
            f"Please install Docker version {MIN_DOCKER_VERSION} or greater.",
        )

    version_str = result.stdout.strip()
    import re

    match = re.search(r"(\d+\.\d+\.\d+)", version_str)
    if not match:
        return False, f"Could not parse Docker version from: {version_str}"

    current = match.group(1)
    if version_tuple(current) < version_tuple(MIN_DOCKER_VERSION):
        return (
            False,
            f"Your current Docker version ({current}) is too old. "
            f"Please install Docker version {MIN_DOCKER_VERSION} or greater.",
        )

    info_result = run(["docker", "info"])
    if info_result.returncode != 0:
        return False, "Docker is not running... Please start Docker."

    return True, version_str


def check_all(exit_on_fail: bool = True) -> dict[str, tuple[bool, str]]:
    """
    Usage:

    - Runs all environment checks

    Optional:

    - ``exit_on_fail``: bool - Exits the process if any check fails
    """
    results = {
        "Docker": check_docker(),
        "Git": check_git(),
        "Pipx": check_pipx(),
    }

    if exit_on_fail:
        failed = False
        for name, (success, message) in results.items():
            if not success:
                logger.error(message)
                failed = True
        if failed:
            sys.exit(1)

    return results


def doctor(args: argparse.Namespace) -> None:
    """
    Usage:

    - Checks the health of the CAVE environment (Docker, Git, Pipx)
    """
    print_section("CAVE Doctor")

    results = check_all(exit_on_fail=False)

    all_pass = True
    for name, (success, message) in results.items():
        if success:
            step_done(f"{name}: {message}")
        else:
            step_fail(f"{name}: {message}")
            all_pass = False

    print_section("Status")
    if all_pass:
        logger.success("Your environment is healthy and ready to CAVE!")
    else:
        logger.error(
            "Some issues were found in your environment. "
            "Please follow the remediation steps above."
        )
        sys.exit(1)
