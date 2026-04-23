import subprocess
import sys

from cave_cli.utils.logger import logger


def run(
    args: list[str],
    capture: bool = True,
    check: bool = False,
    cwd: str | None = None,
    inherit_io: bool = False,
) -> subprocess.CompletedProcess:
    """
    Usage:

    - Runs a subprocess command with standardized handling

    Requires:

    - ``args``:
        - Type: list[str]
        - What: The command and arguments to run

    Optional:

    - ``capture``:
        - Type: bool
        - What: Whether to capture stdout/stderr
        - Default: True

    - ``check``:
        - Type: bool
        - What: Whether to raise on non-zero exit
        - Default: False

    - ``cwd``:
        - Type: str | None
        - What: Working directory for the command
        - Default: None

    - ``inherit_io``:
        - Type: bool
        - What: Whether to pass through stdin/stdout/stderr for
          interactive processes
        - Default: False

    Returns:

    - ``result``:
        - Type: subprocess.CompletedProcess
        - What: The completed process result
    """
    kwargs: dict = {"cwd": cwd}
    if inherit_io:
        kwargs["stdin"] = sys.stdin
        kwargs["stdout"] = sys.stdout
        kwargs["stderr"] = sys.stderr
    elif capture:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
        kwargs["text"] = True
    return subprocess.run(args, check=check, **kwargs)


def run_and_log(
    args: list[str],
    level: str = "DEBUG",
    cwd: str | None = None,
) -> subprocess.CompletedProcess:
    """
    Usage:

    - Runs a subprocess and pipes each output line through the logger

    Requires:

    - ``args``:
        - Type: list[str]
        - What: The command and arguments to run

    Optional:

    - ``level``:
        - Type: str
        - What: Log level for output lines
        - Default: "DEBUG"

    - ``cwd``:
        - Type: str | None
        - What: Working directory for the command
        - Default: None

    Returns:

    - ``result``:
        - Type: subprocess.CompletedProcess
        - What: The completed process result
    """
    result = run(args, cwd=cwd, capture=True)
    log_fn = getattr(logger, level.lower(), logger.debug)
    if result.stdout:
        for line in result.stdout.strip().splitlines():
            log_fn(line)
    if result.stderr:
        for line in result.stderr.strip().splitlines():
            log_fn(line)
    return result


def version_tuple(v: str) -> tuple[int, ...]:
    """
    Usage:

    - Parses a version string into a comparable tuple of integers

    Requires:

    - ``v``:
        - Type: str
        - What: A version string like "23.0.6"

    Returns:

    - ``parts``:
        - Type: tuple[int, ...]
        - What: A tuple of integers for comparison
    """
    return tuple(int(x) for x in v.split(".") if x.isdigit())
