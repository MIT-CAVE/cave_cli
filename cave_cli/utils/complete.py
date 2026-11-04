import os
import sys
from pathlib import Path

from cave_cli.utils.validate import validate_app_dir


def find_app_dir_safe(start: str | None = None) -> str | None:
    """
    Usage:

    - Searches parent directories for a valid CAVE app without exiting on failure

    Optional:

    - ``start``:
        - Type: str | None
        - What: Directory to start searching from
        - Default: None (current working directory)

    Returns:

    - ``app_dir``:
        - Type: str | None
        - What: Path to CAVE app root if found, None otherwise
    """
    path = Path(start or os.getcwd()).resolve()
    while True:
        if not validate_app_dir(str(path)):
            return str(path)
        parent = path.parent
        if parent == path:
            return None
        path = parent


def get_test_files(start_dir: str | None = None) -> list[str]:
    """
    Usage:

    - Discovers available test files in the app's tests directories

    Optional:

    - ``start_dir``:
        - Type: str | None
        - What: Directory to start searching for the CAVE app from
        - Default: None (current working directory)

    Returns:

    - ``files``:
        - Type: list[str]
        - What: List of test file names found in tests/ or cave_api/tests/
    """
    app_dir = find_app_dir_safe(start_dir)
    cwd = Path(start_dir or os.getcwd()).resolve()

    candidate_roots: list[Path] = []
    if app_dir:
        candidate_roots.append(Path(app_dir))
    if cwd not in candidate_roots:
        candidate_roots.append(cwd)

    candidate_subdirs = ["tests", "cave_api/tests", "cave_app/tests", "test"]
    files: set[str] = set()

    for root in candidate_roots:
        for sub in candidate_subdirs:
            t_dir = root / sub
            if t_dir.is_dir():
                for dirpath, _, filenames in os.walk(t_dir):
                    rel_dir = os.path.relpath(dirpath, str(t_dir))
                    for name in filenames:
                        if (
                            name.endswith(".py")
                            and name != "__init__.py"
                            and not name.startswith(".")
                        ):
                            if rel_dir == ".":
                                files.add(name)
                            else:
                                files.add(os.path.join(rel_dir, name))

    return sorted(files)


def get_task_candidate_files(start_dir: str | None = None) -> list[str]:
    """
    Usage:

    - Discovers runnable script and python files in the CAVE app repository

    Optional:

    - ``start_dir``:
        - Type: str | None
        - What: Directory to start searching for the CAVE app from
        - Default: None (current working directory)

    Returns:

    - ``files``:
        - Type: list[str]
        - What: List of relative file paths for runnable scripts
    """
    app_dir = find_app_dir_safe(start_dir)
    if not app_dir:
        return []

    root = Path(app_dir)
    ignore_dirs = {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".nox",
        "site-packages",
        "node_modules",
    }
    results: list[str] = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d
            for d in dirnames
            if d not in ignore_dirs and not d.startswith(".")
        ]
        rel_dir = os.path.relpath(dirpath, str(root))
        for f in filenames:
            if f.endswith((".py", ".sh")):
                if rel_dir == ".":
                    results.append(f)
                else:
                    results.append(os.path.join(rel_dir, f))

    return sorted(results)


def get_completions(words: list[str], cword: int) -> list[str]:
    """
    Usage:

    - Generates completion candidates based on the command line words and cursor index

    Requires:

    - ``words``:
        - Type: list[str]
        - What: List of command-line words typed so far

    - ``cword``:
        - Type: int
        - What: Index of the current word being completed

    Returns:

    - ``candidates``:
        - Type: list[str]
        - What: List of valid completion suggestions
    """
    top_commands = [
        "create",
        "run",
        "start",
        "reset",
        "reset-db",
        "upgrade",
        "sync",
        "test",
        "prettify",
        "task",
        "list",
        "kill",
        "purge",
        "list-versions",
        "lv",
        "doctor",
        "update",
        "uninstall",
        "version",
        "theme",
        "completion",
    ]

    global_flags = [
        "-v",
        "--verbose",
        "-q",
        "--quiet",
        "--loglevel",
        "-y",
        "--yes",
        "-V",
        "--version",
        "-h",
        "--help",
    ]

    # Completing the first argument after 'cave'
    if cword <= 1:
        return top_commands + global_flags

    subcmd = words[1]

    if subcmd == "test":
        test_flags = ["-d", "--detached", "--docker-args"] + global_flags
        test_files = get_test_files()
        return test_files + test_flags

    if subcmd in ("run", "start"):
        return [
            "--entrypoint",
            "--docker-args",
            "-it",
            "-interactive",
            "--interactive",
            "--all",
        ] + global_flags

    if subcmd in ("reset", "reset-db"):
        return ["--docker-args"] + global_flags

    if subcmd == "prettify":
        return ["-d", "--detached", "--docker-args"] + global_flags

    if subcmd == "task":
        task_flags = [
            "-l",
            "--list",
            "-la",
            "--list-all",
            "-a",
            "--attach",
            "-d",
            "--detached",
            "-k",
            "--kill",
            "--kill-all",
            "--reset",
            "--stop",
            "--docker-args",
        ] + global_flags
        task_subcommands = [
            "list",
            "list-all",
            "attach",
            "kill",
            "kill-all",
            "reset",
            "stop",
            "start",
            "run",
        ]

        # Check if completing a task ID after kill or attach
        prev_word = words[cword - 1] if cword > 0 else ""
        if prev_word in ("kill", "-k", "--kill", "attach", "-a", "--attach"):
            app_dir = find_app_dir_safe()
            if app_dir:
                from cave_cli.utils.task_queue import list_tasks

                active_ids = [
                    str(t["id"])
                    for t in list_tasks(app_dir)
                    if t.get("status") in ("queued", "running")
                ]
                return active_ids

        candidate_files = get_task_candidate_files()
        if prev_word in ("start", "run"):
            return candidate_files

        return task_subcommands + candidate_files + task_flags

    if subcmd == "list":
        return ["-a", "--all"] + global_flags

    if subcmd == "kill":
        from cave_cli.utils.docker import (
            get_running_apps,
            get_running_task_servers,
        )

        apps = get_running_apps() + get_running_task_servers()
        return apps + ["-a", "--all", "-t", "--task", "--test"] + global_flags

    if subcmd == "theme":
        return ["dark", "light", "solarized", "monokai"] + global_flags

    if subcmd == "completion":
        return ["-i", "--install", "bash", "zsh"] + global_flags

    return global_flags


def get_completion_script() -> str:
    """
    Usage:

    - Returns the shell completion script for bash and zsh

    Returns:

    - ``script``:
        - Type: str
        - What: Shell script source to enable cave completion
    """
    return """# CAVE CLI Shell Completion
# Load into current shell: eval "$(cave completion)"
# Install permanently: cave completion --install

if [ -n "$ZSH_VERSION" ]; then
    autoload -U +X bashcompinit && bashcompinit 2>/dev/null
fi

_cave_completions() {
    local cur prev words cword
    if declare -F _init_completion >/dev/null 2>&1; then
        _init_completion -n : || return
    else
        cur="${COMP_WORDS[COMP_CWORD]}"
        prev="${COMP_WORDS[COMP_CWORD-1]}"
        words=("${COMP_WORDS[@]}")
        cword=$COMP_CWORD
    fi

    local candidates
    candidates=$(cave _complete --cword "$cword" "${words[@]}" 2>/dev/null)
    COMPREPLY=( $(compgen -W "$candidates" -- "$cur") )
}
complete -o default -F _cave_completions cave
"""


def install_completion() -> str | None:
    """
    Usage:

    - Automatically installs the completion hook into the user's shell rc file

    Returns:

    - ``target_file``:
        - Type: str | None
        - What: Path of updated rc file, or None if failed
    """
    shell_path = os.environ.get("SHELL", "")
    shell_name = os.path.basename(shell_path)
    home = Path.home()

    if "zsh" in shell_name:
        rc_path = home / ".zshrc"
    elif "bash" in shell_name:
        rc_path = home / ".bashrc"
        if not rc_path.exists() and (home / ".bash_profile").exists():
            rc_path = home / ".bash_profile"
    else:
        rc_path = home / ".bashrc"

    marker = 'eval "$(cave completion)"'
    if rc_path.exists():
        content = rc_path.read_text(encoding="utf-8")
        if marker in content:
            return str(rc_path)

    with open(rc_path, "a", encoding="utf-8") as f:
        f.write(f"\n# CAVE CLI Auto-completion\n{marker}\n")

    return str(rc_path)
