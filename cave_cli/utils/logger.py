import sys


class CaveLogger:
    """
    Usage:

    - Multi-level logger matching the bash CLI's DEBUG/INFO/WARN/ERROR/SILENT behavior

    Notes:

    - Output goes to stderr in the format ``LEVEL: message``
    - Module-level singleton ``logger`` is used throughout the package
    """

    LEVELS: dict[str, int] = {
        "DEBUG": 0,
        "INFO": 1,
        "WARN": 2,
        "ERROR": 3,
        "SILENT": 4,
    }

    def __init__(self, level: str = "INFO") -> None:
        self.set_level(level)

    def set_level(self, level: str) -> None:
        """
        Usage:

        - Sets the minimum log level for output

        Requires:

        - ``level``:
            - Type: str
            - What: One of DEBUG, INFO, WARN, ERROR, SILENT
        """
        level = level.upper()
        if level not in self.LEVELS:
            raise ValueError(
                f"Invalid log level {level!r}. "
                f"Must be one of: {list(self.LEVELS.keys())}"
            )
        self._level = self.LEVELS[level]

    def log(self, message: str, level: str) -> None:
        if self.LEVELS.get(level, 0) >= self._level:
            sys.stderr.write(f"{level}: {message}\n")
            sys.stderr.flush()

    def debug(self, message: str) -> None:
        self.log(message, "DEBUG")

    def info(self, message: str) -> None:
        self.log(message, "INFO")

    def warn(self, message: str) -> None:
        self.log(message, "WARN")

    def error(self, message: str) -> None:
        self.log(message, "ERROR")

    def header(self, text: str) -> None:
        """
        Usage:

        - Prints a header block with separator lines at INFO level
        """
        from cave_cli.utils.constants import CHAR_LINE

        self.info(CHAR_LINE)
        self.info(text)
        self.info(CHAR_LINE)


logger = CaveLogger()
