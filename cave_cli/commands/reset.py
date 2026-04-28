import argparse

from cave_cli.commands.run import run_cave
from cave_cli.utils.display import print_section, step_done, step_start
from cave_cli.utils.docker import remove_containers, remove_volume
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

    print_section("Reset")

    step_start("Removing containers")
    remove_containers(app_name)
    step_done("Removing containers")

    step_start("Removing database volume")
    remove_volume(app_name)
    step_done("Removing database volume")

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
    run_cave(app_dir, app_name, reset_args, skip_header=True)
    step_done("Reset complete")
