from cave_cli.utils.subprocess import run, run_and_log


def clone(
    url: str,
    dest: str,
    branch: str | None = None,
    single_branch: bool = True,
) -> bool:
    """
    Usage:

    - Clones a git repository

    Requires:

    - ``url``:
        - Type: str
        - What: The repository URL to clone

    - ``dest``:
        - Type: str
        - What: The destination directory

    Optional:

    - ``branch``:
        - Type: str | None
        - What: A specific branch or tag to clone
        - Default: None (clones the default branch)

    - ``single_branch``:
        - Type: bool
        - What: Whether to clone only the specified branch
        - Default: True

    Returns:

    - ``success``:
        - Type: bool
        - What: True if the clone succeeded, False otherwise
    """
    cmd = ["git", "clone"]
    if branch:
        cmd.extend(["-b", branch])
    if single_branch:
        cmd.append("--single-branch")
    cmd.extend([url, dest])
    result = run_and_log(cmd)
    return result.returncode == 0


def init(path: str) -> None:
    """
    Usage:

    - Initializes a new git repository

    Requires:

    - ``path``:
        - Type: str
        - What: The directory to initialize
    """
    run_and_log(["git", "init"], cwd=path)


def add(path: str, files: list[str] | None = None) -> None:
    """
    Usage:

    - Stages files in the git repository

    Requires:

    - ``path``:
        - Type: str
        - What: The repository directory

    Optional:

    - ``files``:
        - Type: list[str] | None
        - What: Specific files to stage
        - Default: None (stages all files)
    """
    cmd = ["git", "add"]
    cmd.extend(files or ["."])
    run_and_log(cmd, cwd=path)


def commit(path: str, message: str) -> None:
    """
    Usage:

    - Creates a git commit

    Requires:

    - ``path``:
        - Type: str
        - What: The repository directory

    - ``message``:
        - Type: str
        - What: The commit message
    """
    run_and_log(["git", "commit", "-m", message], cwd=path)


def branch_rename(path: str, name: str) -> None:
    """
    Usage:

    - Renames the current branch

    Requires:

    - ``path``:
        - Type: str
        - What: The repository directory

    - ``name``:
        - Type: str
        - What: The new branch name
    """
    run_and_log(["git", "branch", "-M", name], cwd=path)


def fetch(path: str) -> None:
    """
    Usage:

    - Fetches from the remote

    Requires:

    - ``path``:
        - Type: str
        - What: The repository directory
    """
    run_and_log(["git", "fetch"], cwd=path)


def checkout(path: str, ref: str) -> None:
    """
    Usage:

    - Checks out a branch or tag

    Requires:

    - ``path``:
        - Type: str
        - What: The repository directory

    - ``ref``:
        - Type: str
        - What: The branch, tag, or commit to check out
    """
    run_and_log(["git", "checkout", ref], cwd=path)


def pull(path: str) -> None:
    """
    Usage:

    - Pulls from the remote

    Requires:

    - ``path``:
        - Type: str
        - What: The repository directory
    """
    run_and_log(["git", "pull"], cwd=path)


def ls_remote_tags(url: str) -> list[str]:
    """
    Usage:

    - Lists remote tags for a git repository

    Requires:

    - ``url``:
        - Type: str
        - What: The repository URL

    Returns:

    - ``tags``:
        - Type: list[str]
        - What: A sorted list of tag names
    """
    result = run(["git", "ls-remote", "--tags", url])
    tags: list[str] = []
    if result.returncode != 0 or not result.stdout:
        return tags
    for line in result.stdout.strip().splitlines():
        parts = line.split("refs/tags/")
        if len(parts) == 2:
            tag = parts[1].rstrip("^{}")
            if tag and tag not in tags and not tag.endswith("^{}"):
                tags.append(tag)
    return tags


def ls_remote_heads(url: str) -> list[str]:
    """
    Usage:

    - Lists remote branch heads for a git repository

    Requires:

    - ``url``:
        - Type: str
        - What: The repository URL

    Returns:

    - ``branches``:
        - Type: list[str]
        - What: A sorted list of branch names
    """
    result = run(["git", "ls-remote", "--heads", url])
    branches: list[str] = []
    if result.returncode != 0 or not result.stdout:
        return branches
    for line in result.stdout.strip().splitlines():
        parts = line.split("refs/heads/")
        if len(parts) == 2:
            branch = parts[1].strip()
            if branch:
                branches.append(branch)
    return branches
