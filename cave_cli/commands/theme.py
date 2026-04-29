import argparse
import sys

from cave_cli.utils.cache import set_setting
from cave_cli.utils.display import THEMES, print_section, set_theme
from cave_cli.utils.logger import logger


def theme_cmd(args: argparse.Namespace) -> None:
    """
    Usage:

    - Sets the CLI theme preference and applies it immediately
    """
    new_theme = getattr(args, "name", None)
    if not new_theme:
        print_section("CAVE Themes")
        logger.info(f"Available themes: {', '.join(THEMES.keys())}")
        from cave_cli.utils.cache import get_setting

        current = get_setting("theme", "dark")
        logger.info(f"Current theme: {current}")
        return

    if new_theme.lower() not in THEMES:
        logger.error(
            f"Invalid theme '{new_theme}'. "
            f"Available: {', '.join(THEMES.keys())}"
        )
        sys.exit(1)

    set_setting("theme", new_theme.lower())
    set_theme(new_theme)
    logger.success(f"Theme set to '{new_theme.lower()}'.")
