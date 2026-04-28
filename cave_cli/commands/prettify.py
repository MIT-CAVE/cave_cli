import argparse

from cave_cli.commands.run import run_cave
from cave_cli.utils.display import print_section
from cave_cli.utils.validate import get_app


def prettify(args: argparse.Namespace) -> None:
    """
    Usage:

    - Runs code formatting on the CAVE app in the current directory
    """
    app_dir, app_name = get_app()
    print_section("Prettify")

    run_args = argparse.Namespace(
        entrypoint="./utils/prettify.sh",
        interactive=False,
        it=False,
        docker_args="",
        ip_port=None,
        yes=True,
        verbose=getattr(args, "verbose", False),
        loglevel=getattr(args, "loglevel", "INFO"),
    )
    run_cave(app_dir, app_name, run_args)
