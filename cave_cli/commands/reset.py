import argparse

from cave_cli.commands.run import run_cave
from cave_cli.utils.docker import remove_containers, remove_volume
from cave_cli.utils.logger import logger
from cave_cli.utils.validate import confirm_action, get_app


def reset(
    args: argparse.Namespace,
    app_dir: str | None = None,
    app_name: str | None = None,
) -> None:
    """
    Usage:

    - Removes Docker containers and volumes, then rebuilds from scratch
    """
    auto_yes = getattr(args, "yes", False)
    if not auto_yes:
        confirm_action(
            "This will remove the Docker containers "
            "(deleted and recreated from scratch) for this app. "
            "All data in your database will be lost"
        )

    if app_dir is None or app_name is None:
        app_dir, app_name = get_app()
    remove_containers(app_name)
    remove_volume(app_name)

    reset_args = argparse.Namespace(
        entrypoint="./utils/reset_db.sh",
        interactive=False,
        it=False,
        docker_args="",
        ip_port=None,
        yes=True,
        verbose=getattr(args, "verbose", False),
        loglevel=getattr(args, "loglevel", "INFO"),
    )
    run_cave(app_dir, app_name, reset_args)
    logger.info("DB reset complete.")
