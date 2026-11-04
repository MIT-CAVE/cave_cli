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
    cave completion
    cave completion --install
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
        "-q",
        "--quiet",
        action="store_true",
        default=False,
        help="Enable quiet mode (suppress most output, shorthand for --loglevel SILENT)",
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


def normalize_task_args(args: list[str]) -> list[str]:
    """
    Usage:

    - Normalizes command line arguments for 'cave task' to route arbitrary commands to 'start'

    Requires:

    - ``args``:
        - Type: list[str]
        - What: Raw command line argument list

    Returns:

    - ``normalized``:
        - Type: list[str]
        - What: Argument list with 'start' injected when arbitrary commands are run directly
    """
    try:
        idx = args.index("task")
    except ValueError:
        return args

    known_actions = {
        # Subcommands
        "start",
        "run",
        "list",
        "ls",
        "list-all",
        "la",
        "attach",
        "join",
        "log",
        "logs",
        "kill",
        "cancel",
        "kill-all",
        "cancel-all",
        "reset",
        "stop",
        "kill-server",
        # Action flags
        "-l",
        "--list",
        "-la",
        "--list-all",
        "-a",
        "--attach",
        "-k",
        "--kill",
        "--kill-all",
        "--reset",
        "--stop",
        "-h",
        "--help",
    }

    after_task = args[idx + 1 :]
    # If any known subcommand or action flag is present, or if no args after task, don't inject 'start'
    if any(a in known_actions for a in after_task) or not after_task:
        return args

    # Find the position of the first non-option argument (skipping options and their arguments)
    skip_next = False
    options_with_value = {"--loglevel", "--ll", "--docker-args"}
    for i, a in enumerate(after_task):
        if skip_next:
            skip_next = False
            continue
        if a in options_with_value:
            skip_next = True
            continue
        if any(a.startswith(f"{opt}=") for opt in options_with_value):
            continue
        if not a.startswith("-"):
            insert_pos = idx + 1 + i
            return args[:insert_pos] + ["start"] + args[insert_pos:]

    return args


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
            "Remove Docker containers and volumes, " "then rebuild from scratch"
        ),
    )
    add_global_args(p_reset)
    p_reset.add_argument(
        "--docker-args",
        default="",
        metavar="ARGS",
        help="Additional arguments to pass to docker run",
    )

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
        action="extend",
        default=None,
        metavar="PATTERN",
        help="File patterns to include (overrides excludes)",
    )
    p_sync.add_argument(
        "--exclude",
        nargs="+",
        action="extend",
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
        "-d",
        "--detached",
        action="store_true",
        default=False,
        help="Run test task in detached background mode",
    )
    p_test.add_argument(
        "--docker-args",
        default="",
        metavar="ARGS",
        help="Additional arguments to pass to docker run",
    )
    p_test.add_argument(
        "remaining",
        nargs="*",
        help="Test files or pytest arguments",
    )

    # ------------------------------------------------------------------ #
    # prettify                                                             #
    # ------------------------------------------------------------------ #
    p_prettify = subparsers.add_parser(
        "prettify",
        help="Format code with autoflake and black",
    )
    add_global_args(p_prettify)
    p_prettify.add_argument(
        "-d",
        "--detached",
        action="store_true",
        default=False,
        help="Run prettify task in detached background mode",
    )
    p_prettify.add_argument(
        "--docker-args",
        default="",
        metavar="ARGS",
        help="Additional arguments to pass to docker run",
    )
    p_prettify.add_argument(
        "remaining",
        nargs="*",
        help="Additional arguments passed to the prettify task",
    )

    # ------------------------------------------------------------------ #
    # task                                                                 #
    # ------------------------------------------------------------------ #
    p_task = subparsers.add_parser(
        "task",
        help="Inspect, kill, and manage running tasks and task runner",
    )
    add_global_args(p_task)
    p_task.add_argument(
        "-l",
        "--list",
        action="store_true",
        default=False,
        help="List current active tasks (queued and running)",
    )
    p_task.add_argument(
        "-la",
        "--list-all",
        action="store_true",
        default=False,
        help="List all tasks including completed, failed, and cancelled",
    )
    p_task.add_argument(
        "-a",
        "--attach",
        nargs="?",
        const=-1,
        type=int,
        dest="attach_id",
        default=None,
        metavar="ID",
        help="Attach to a task to follow progress and output",
    )
    p_task.add_argument(
        "-d",
        "--detached",
        action="store_true",
        default=False,
        help="Run task in detached background mode",
    )
    p_task.add_argument(
        "-k",
        "--kill",
        type=int,
        dest="kill_id",
        default=None,
        metavar="ID",
        help="Kill a specific task by its incremental ID",
    )
    p_task.add_argument(
        "--kill-all",
        action="store_true",
        default=False,
        help="Cancel all queued and running tasks",
    )
    p_task.add_argument(
        "--reset",
        action="store_true",
        default=False,
        help="Reset task runner database and rebuild container image",
    )
    p_task.add_argument(
        "--stop",
        action="store_true",
        default=False,
        help="Stop task server containers",
    )
    p_task.add_argument(
        "--docker-args",
        default="",
        metavar="ARGS",
        help="Additional arguments to pass to docker run",
    )

    task_subparsers = p_task.add_subparsers(
        dest="task_action",
        metavar="subcommand",
    )

    # task start
    p_task_start = task_subparsers.add_parser(
        "start",
        aliases=["run"],
        help="Schedule and run a task or script sequentially in the task container",
        description="Schedule and run arbitrary files or container commands in the task queue.",
    )
    add_global_args(p_task_start)
    p_task_start.add_argument(
        "-d",
        "--detached",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Run task in detached background mode",
    )
    p_task_start.add_argument(
        "--docker-args",
        default=argparse.SUPPRESS,
        metavar="ARGS",
        help="Additional arguments to pass to docker run",
    )
    p_task_start.add_argument(
        "task_cmd",
        nargs="+",
        metavar="command",
        help="Command or script to execute in task container (e.g. utils/prettify.py, python manage.py migrate)",
    )

    # task stop
    p_task_stop = task_subparsers.add_parser(
        "stop",
        aliases=["kill-server"],
        help="Stop task server containers and clean up completed tasks",
        description="Stop and remove background task runner containers and delete completed task logs.",
    )
    add_global_args(p_task_stop)

    # task list
    p_task_list = task_subparsers.add_parser(
        "list",
        aliases=["ls"],
        help="List current active tasks (queued and running)",
        description="Display active tasks in the queue with incremental IDs, status, and duration.",
    )
    add_global_args(p_task_list)
    p_task_list.add_argument(
        "-a",
        "--all",
        action="store_true",
        dest="list_all",
        default=argparse.SUPPRESS,
        help="List all tasks including completed, failed, and cancelled",
    )

    # task list-all
    p_task_list_all = task_subparsers.add_parser(
        "list-all",
        aliases=["la"],
        help="List all tasks including completed, failed, and cancelled",
        description="Display all recorded tasks in the project registry.",
    )
    add_global_args(p_task_list_all)

    # task attach
    p_task_attach = task_subparsers.add_parser(
        "attach",
        aliases=["join", "log", "logs"],
        help="Attach to a task to follow live progress and output",
        description=(
            "Reattach to a queued or running task to view live streaming logs.\n\n"
            "Controls while attached:\n"
            "  Esc      Detach from task and return to terminal (task continues running)\n"
            "  Ctrl+C   Cancel and terminate the task"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_global_args(p_task_attach)
    p_task_attach.add_argument(
        "task_id",
        nargs="?",
        type=int,
        default=None,
        metavar="ID",
        help="Incremental ID of task to attach to (default: current active task)",
    )

    # task kill
    p_task_kill = task_subparsers.add_parser(
        "kill",
        aliases=["cancel"],
        help="Cancel or terminate a specific task by its incremental ID",
        description="Cancel a queued task or terminate a running task's container execution.",
    )
    add_global_args(p_task_kill)
    p_task_kill.add_argument(
        "task_id",
        type=int,
        metavar="ID",
        help="Incremental ID of the task to kill",
    )

    # task kill-all
    p_task_kill_all = task_subparsers.add_parser(
        "kill-all",
        aliases=["cancel-all"],
        help="Cancel all queued and running tasks",
        description="Cancel all queued tasks and terminate any currently running task container.",
    )
    add_global_args(p_task_kill_all)

    # task reset
    p_task_reset = task_subparsers.add_parser(
        "reset",
        help="Reset task runner database and rebuild container image",
        description="Tear down the task server, remove database/redis volumes, rebuild image, and reset task registry.",
    )
    add_global_args(p_task_reset)
    p_task_reset.add_argument(
        "--docker-args",
        default=argparse.SUPPRESS,
        metavar="ARGS",
        help="Additional arguments to pass to docker run",
    )

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
    p_kill.add_argument(
        "-t",
        "--task",
        "--test",
        action="store_true",
        default=False,
        help="Stop task server containers instead of live app",
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
    # doctor                                                               #
    # ------------------------------------------------------------------ #
    p_doctor = subparsers.add_parser(
        "doctor",
        help="Check the health of the CAVE environment",
    )
    add_global_args(p_doctor)

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
    # theme                                                                #
    # ------------------------------------------------------------------ #
    p_theme = subparsers.add_parser(
        "theme",
        help="Set the CLI color theme",
    )
    add_global_args(p_theme)
    p_theme.add_argument(
        "name",
        nargs="?",
        default=None,
        metavar="THEME",
        help="Name of the theme to apply (dark, light, solarized, monokai)",
    )

    # ------------------------------------------------------------------ #
    # _task-watcher / _test-watcher (internal idle daemon)                #
    # ------------------------------------------------------------------ #
    p_watcher = subparsers.add_parser(
        "_task-watcher",
        aliases=["_test-watcher"],
        help=argparse.SUPPRESS,
    )
    p_watcher.add_argument("app_dir")
    p_watcher.add_argument("app_name")
    p_watcher.add_argument("keep_alive", type=int)

    # ------------------------------------------------------------------ #
    # _task-runner (internal task execution worker)                       #
    # ------------------------------------------------------------------ #
    p_task_runner = subparsers.add_parser(
        "_task-runner",
        help=argparse.SUPPRESS,
    )
    p_task_runner.add_argument("app_dir")
    p_task_runner.add_argument("app_name")
    p_task_runner.add_argument("task_id", type=int)
    p_task_runner.add_argument("--docker-args", default="")

    # ------------------------------------------------------------------ #
    # completion                                                           #
    # ------------------------------------------------------------------ #
    p_completion = subparsers.add_parser(
        "completion",
        help="Generate or install shell completion script for bash/zsh",
        description=(
            "Generate or install shell completion scripts for Bash and Zsh.\n\n"
            "Quick setup:\n"
            "  cave completion --install    Automatically add to ~/.bashrc or ~/.zshrc\n\n"
            "Or load in current session:\n"
            '  eval "$(cave completion)"'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_global_args(p_completion)
    p_completion.add_argument(
        "-i",
        "--install",
        action="store_true",
        default=False,
        help="Automatically append completion hook to ~/.bashrc or ~/.zshrc",
    )
    p_completion.add_argument(
        "shell",
        nargs="?",
        default="bash",
        choices=["bash", "zsh"],
        help="Target shell (default: bash)",
    )

    # ------------------------------------------------------------------ #
    # _complete (internal completion hook)                                 #
    # ------------------------------------------------------------------ #
    p_complete = subparsers.add_parser(
        "_complete",
        help=argparse.SUPPRESS,
    )
    p_complete.add_argument(
        "--cword",
        type=int,
        default=1,
        help=argparse.SUPPRESS,
    )
    p_complete.add_argument(
        "words",
        nargs="*",
        help=argparse.SUPPRESS,
    )

    # ------------------------------------------------------------------ #
    # Dispatch                                                             #
    # ------------------------------------------------------------------ #
    args = parser.parse_args(normalize_task_args(sys.argv[1:]))

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

    if getattr(args, "quiet", False):
        logger.set_level("SILENT")
    elif getattr(args, "verbose", False):
        logger.set_level("DEBUG")
    else:
        logger.set_level(getattr(args, "loglevel", "INFO"))

    # ------------------------------------------------------------------ #
    # Command dispatch                                                     #
    # ------------------------------------------------------------------ #
    if args.command == "create":
        from cave_cli.commands.doctor import check_all
        from cave_cli.commands.create import create

        check_all()
        create(args)

    elif args.command == "run":
        from cave_cli.commands.doctor import check_all
        from cave_cli.commands.run import run

        check_all()
        run(args)

    elif args.command == "reset":
        from cave_cli.commands.doctor import check_all
        from cave_cli.commands.reset import reset

        check_all()
        reset(args)

    elif args.command == "upgrade":
        from cave_cli.commands.doctor import check_all
        from cave_cli.commands.upgrade import upgrade

        check_all()
        upgrade(args)

    elif args.command == "sync":
        from cave_cli.commands.doctor import check_all
        from cave_cli.commands.sync_cmd import sync_cmd

        check_all()
        sync_cmd(args)

    elif args.command == "test":
        from cave_cli.commands.doctor import check_all
        from cave_cli.commands.test import test

        check_all()
        test(args)

    elif args.command in ("_task-watcher", "_test-watcher"):
        from cave_cli.utils.task_server import run_task_idle_watcher

        run_task_idle_watcher(args.app_dir, args.app_name, args.keep_alive)

    elif args.command == "_task-runner":
        from cave_cli.commands.task import run_task_worker

        run_task_worker(
            args.app_dir,
            args.app_name,
            args.task_id,
            docker_args_str=args.docker_args,
        )

    elif args.command == "task":
        from cave_cli.commands.doctor import check_all
        from cave_cli.commands.task import task

        check_all()
        task(args)

    elif args.command == "prettify":
        from cave_cli.commands.doctor import check_all
        from cave_cli.commands.prettify import prettify

        check_all()
        prettify(args)

    elif args.command == "list":
        from cave_cli.commands.doctor import check_all
        from cave_cli.commands.list_cmd import list_cmd

        check_all()
        list_cmd(args)

    elif args.command == "kill":
        from cave_cli.commands.doctor import check_all
        from cave_cli.commands.kill import kill

        check_all()
        kill(args)

    elif args.command == "purge":
        from cave_cli.commands.doctor import check_all
        from cave_cli.commands.purge import purge

        check_all()
        purge(args)

    elif args.command == "list-versions":
        from cave_cli.commands.doctor import check_all
        from cave_cli.commands.list_versions import list_versions

        check_all()
        list_versions(args)

    elif args.command == "update":
        from cave_cli.commands.doctor import check_all
        from cave_cli.commands.update import update

        check_all()
        update(args)

    elif args.command == "doctor":
        from cave_cli.commands.doctor import doctor

        doctor(args)

    elif args.command == "theme":
        from cave_cli.commands.theme import theme_cmd

        theme_cmd(args)

    elif args.command == "uninstall":
        from cave_cli.commands.uninstall import uninstall

        uninstall(args)

    elif args.command == "version":
        from cave_cli.commands.version import version as version_cmd

        version_cmd(args)

    elif args.command == "completion":
        from cave_cli.commands.completion import completion_cmd

        completion_cmd(args)

    elif args.command == "_complete":
        from cave_cli.utils.complete import get_completions

        words = getattr(args, "words", []) or ["cave"]
        cword = getattr(args, "cword", 1)
        candidates = get_completions(words, cword)
        if candidates:
            print(" ".join(candidates))

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
