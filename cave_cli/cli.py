"""
CAVE CLI entry point.

Usage:
    cave <command> [options]

Examples:
    cave create my_app
    cave create my_app --version v3.1.0
    cave run
    cave run -it
    cave run 192.168.1.1:8000
    cave reset -y
    cave upgrade --version v3.1.0
    cave sync --url git@github.com:mit-cave/cave_app_aws.git
    cave test
    cave prettify
    cave list
    cave kill
    cave purge my_app
    cave list-versions
    cave lv  --all --pattern v3*
    cave update
    cave version
"""

import argparse
import sys
from importlib.metadata import version


def add_global_args(parser: argparse.ArgumentParser) -> None:
    """Args shared by all commands."""
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help="Enable verbose logging output (shorthand for --loglevel DEBUG)",
    )
    parser.add_argument(
        "--loglevel",
        "--ll",
        default="INFO",
        metavar="LEVEL",
        help=(
            "Specify a log level: DEBUG, INFO, WARN, ERROR, SILENT "
            "(default: INFO)"
        ),
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        default=False,
        help="Automatically answer confirmation prompts with yes",
    )


def main():
    __version__ = version("cave_cli")
    parser = argparse.ArgumentParser(
        prog="cave",
        description=(
            f"CAVE CLI ({__version__}): "
            "Create and manage Docker-based CAVE web applications."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"CAVE_CLI={__version__}",
        help="Show the version number and exit",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="command")

    # ------------------------------------------------------------------ #
    # create                                                               #
    # ------------------------------------------------------------------ #
    p_create = subparsers.add_parser(
        "create",
        help="Create a new CAVE app from the template repository",
    )
    add_global_args(p_create)
    p_create.add_argument(
        "name",
        metavar="app-name",
        help="Name for the new CAVE app",
    )
    p_create.add_argument(
        "--version",
        default=None,
        metavar="VERSION",
        help="CAVE app version (git tag or branch name)",
    )
    p_create.add_argument(
        "--url",
        default=None,
        metavar="URL",
        help="Git URL for the app template repository",
    )

    # ------------------------------------------------------------------ #
    # run / start                                                          #
    # ------------------------------------------------------------------ #
    p_run = subparsers.add_parser(
        "run",
        aliases=["start"],
        help="Build and run the CAVE app in the current directory",
    )
    add_global_args(p_run)
    p_run.add_argument(
        "ip_port",
        nargs="?",
        default=None,
        metavar="ip:port",
        help="IP and port for LAN hosting (e.g. 192.168.1.1:8000)",
    )
    p_run.add_argument(
        "--entrypoint",
        default=None,
        metavar="CMD",
        help="Entrypoint script to run (default: ./utils/run_server.sh)",
    )
    p_run.add_argument(
        "--docker-args",
        default="",
        metavar="ARGS",
        help="Additional arguments to pass to docker run",
    )
    p_run.add_argument(
        "-it",
        "-interactive",
        "--interactive",
        dest="interactive",
        action="store_true",
        default=False,
        help="Run in interactive mode (entrypoint set to bash)",
    )
    p_run.add_argument(
        "--all",
        dest="show_all",
        action="store_true",
        default=False,
        help="Show raw container output instead of the TUI dashboard (also enabled by --verbose)",
    )

    # ------------------------------------------------------------------ #
    # reset                                                                #
    # ------------------------------------------------------------------ #
    p_reset = subparsers.add_parser(
        "reset",
        aliases=["reset-db"],
        help=(
            "Remove Docker containers and volumes, "
            "then rebuild from scratch"
        ),
    )
    add_global_args(p_reset)

    # ------------------------------------------------------------------ #
    # upgrade                                                              #
    # ------------------------------------------------------------------ #
    p_upgrade = subparsers.add_parser(
        "upgrade",
        help="Upgrade the CAVE app in the current directory",
    )
    add_global_args(p_upgrade)
    p_upgrade.add_argument(
        "--version",
        default=None,
        metavar="VERSION",
        help="CAVE app version to upgrade to (git tag or branch name)",
    )
    p_upgrade.add_argument(
        "--url",
        default=None,
        metavar="URL",
        help="Git URL for the app template repository",
    )
    p_upgrade.add_argument(
        "--skip-env-upgrade",
        action="store_true",
        default=False,
        help="Skip upgrading the project .env file",
    )

    # ------------------------------------------------------------------ #
    # sync                                                                 #
    # ------------------------------------------------------------------ #
    p_sync = subparsers.add_parser(
        "sync",
        help="Merge files from another repository into the CAVE app",
    )
    add_global_args(p_sync)
    p_sync.add_argument(
        "--url",
        required=True,
        metavar="URL",
        help="Git URL of the repository to sync from",
    )
    p_sync.add_argument(
        "--branch",
        default=None,
        metavar="BRANCH",
        help="Branch of the repository to sync from",
    )
    p_sync.add_argument(
        "--include",
        nargs="+",
        default=None,
        metavar="PATTERN",
        help="File patterns to include (overrides excludes)",
    )
    p_sync.add_argument(
        "--exclude",
        nargs="+",
        default=None,
        metavar="PATTERN",
        help="File patterns to exclude",
    )

    # ------------------------------------------------------------------ #
    # test                                                                 #
    # ------------------------------------------------------------------ #
    p_test = subparsers.add_parser(
        "test",
        help="Run tests in cave_api/tests/",
    )
    add_global_args(p_test)
    p_test.add_argument(
        "remaining",
        nargs="*",
        help="Additional arguments passed to the test runner",
    )

    # ------------------------------------------------------------------ #
    # prettify                                                             #
    # ------------------------------------------------------------------ #
    p_prettify = subparsers.add_parser(
        "prettify",
        help="Format code with autoflake and black",
    )
    add_global_args(p_prettify)

    # ------------------------------------------------------------------ #
    # list                                                                 #
    # ------------------------------------------------------------------ #
    p_list = subparsers.add_parser(
        "list",
        help="List running CAVE apps",
    )
    add_global_args(p_list)
    p_list.add_argument(
        "-a",
        "--all",
        action="store_true",
        default=False,
        help="Show all CAVE app containers with full names",
    )

    # ------------------------------------------------------------------ #
    # kill                                                                 #
    # ------------------------------------------------------------------ #
    p_kill = subparsers.add_parser(
        "kill",
        help="Stop Docker containers for a CAVE app",
    )
    add_global_args(p_kill)
    p_kill.add_argument(
        "name",
        nargs="?",
        default=None,
        metavar="app-name",
        help="Name of the CAVE app to kill",
    )
    p_kill.add_argument(
        "-a",
        "--all",
        action="store_true",
        default=False,
        help="Kill all running CAVE apps",
    )

    # ------------------------------------------------------------------ #
    # purge                                                                #
    # ------------------------------------------------------------------ #
    p_purge = subparsers.add_parser(
        "purge",
        help="Remove a CAVE app and all its Docker resources",
    )
    add_global_args(p_purge)
    p_purge.add_argument(
        "path",
        metavar="app-path",
        help="Path to the CAVE app directory to purge",
    )

    # ------------------------------------------------------------------ #
    # list-versions / lv                                                   #
    # ------------------------------------------------------------------ #
    p_lv = subparsers.add_parser(
        "list-versions",
        aliases=["lv"],
        help="List available CAVE app versions",
    )
    add_global_args(p_lv)
    p_lv.add_argument(
        "--all",
        action="store_true",
        default=False,
        help="Show all versions (default: 5 most recent per major version)",
    )
    p_lv.add_argument(
        "--pattern",
        default=None,
        metavar="PATTERN",
        help="Glob pattern to filter versions (e.g. v3.*, v3.4.*)",
    )

    # ------------------------------------------------------------------ #
    # update                                                               #
    # ------------------------------------------------------------------ #
    p_update = subparsers.add_parser(
        "update",
        help="Update the CAVE CLI itself",
    )
    add_global_args(p_update)
    p_update.add_argument(
        "--version",
        default=None,
        metavar="VERSION",
        help="Specific CAVE CLI version to install (git tag or branch)",
    )

    # ------------------------------------------------------------------ #
    # uninstall                                                            #
    # ------------------------------------------------------------------ #
    p_uninstall = subparsers.add_parser(
        "uninstall",
        help="Remove the CAVE CLI",
    )
    add_global_args(p_uninstall)

    # ------------------------------------------------------------------ #
    # version                                                              #
    # ------------------------------------------------------------------ #
    p_version = subparsers.add_parser(
        "version",
        help="Print version information",
    )
    add_global_args(p_version)

    # ------------------------------------------------------------------ #
    # Dispatch                                                             #
    # ------------------------------------------------------------------ #
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    # Normalize aliases
    _COMMAND_ALIASES: dict[str, str] = {
        "start": "run",
        "reset-db": "reset",
        "lv": "list-versions",
    }
    args.command = _COMMAND_ALIASES.get(args.command, args.command)

    # Configure logging
    from cave_cli.utils.logger import logger

    if args.verbose:
        logger.set_level("DEBUG")
    else:
        logger.set_level(args.loglevel)

    # ------------------------------------------------------------------ #
    # Command dispatch                                                     #
    # ------------------------------------------------------------------ #
    if args.command == "create":
        from cave_cli.utils.docker import check_docker
        from cave_cli.commands.create import create

        check_docker()
        create(args)

    elif args.command == "run":
        from cave_cli.utils.docker import check_docker
        from cave_cli.commands.run import run

        check_docker()
        run(args)

    elif args.command == "reset":
        from cave_cli.utils.docker import check_docker
        from cave_cli.commands.reset import reset

        check_docker()
        reset(args)

    elif args.command == "upgrade":
        from cave_cli.utils.docker import check_docker
        from cave_cli.commands.upgrade import upgrade

        check_docker()
        upgrade(args)

    elif args.command == "sync":
        from cave_cli.utils.docker import check_docker
        from cave_cli.commands.sync_cmd import sync_cmd

        check_docker()
        sync_cmd(args)

    elif args.command == "test":
        from cave_cli.utils.docker import check_docker
        from cave_cli.commands.test import test

        check_docker()
        test(args)

    elif args.command == "prettify":
        from cave_cli.utils.docker import check_docker
        from cave_cli.commands.prettify import prettify

        check_docker()
        prettify(args)

    elif args.command == "list":
        from cave_cli.utils.docker import check_docker
        from cave_cli.commands.list_cmd import list_cmd

        check_docker()
        list_cmd(args)

    elif args.command == "kill":
        from cave_cli.utils.docker import check_docker
        from cave_cli.commands.kill import kill

        check_docker()
        kill(args)

    elif args.command == "purge":
        from cave_cli.utils.docker import check_docker
        from cave_cli.commands.purge import purge

        check_docker()
        purge(args)

    elif args.command == "list-versions":
        from cave_cli.commands.list_versions import list_versions

        list_versions(args)

    elif args.command == "update":
        from cave_cli.commands.update import update

        update(args)

    elif args.command == "uninstall":
        from cave_cli.commands.uninstall import uninstall

        uninstall(args)

    elif args.command == "version":
        from cave_cli.commands.version import version as version_cmd

        version_cmd(args)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
