import fnmatch
import os
import shutil
from pathlib import Path

from cave_cli.utils.logger import logger


def sync_files(
    source: str,
    dest: str,
    includes: list[str] | None = None,
    excludes: list[str] | None = None,
) -> None:
    """
    Usage:

    - Syncs files from a source directory to a destination directory

    Requires:

    - ``source``:
        - Type: str
        - What: The source directory to copy from

    - ``dest``:
        - Type: str
        - What: The destination directory to copy to

    Optional:

    - ``includes``:
        - Type: list[str] | None
        - What: Patterns for files that should always be included
          (overrides excludes)
        - Default: None

    - ``excludes``:
        - Type: list[str] | None
        - What: Patterns for files that should be excluded
        - Default: None

    Notes:

    - Always excludes ``.git``
    - Include patterns override exclude patterns (matching rsync semantics)
    - Uses ``shutil.copytree`` with ``dirs_exist_ok=True`` for merge behavior
    """
    clean_includes = [strip_quotes(p) for p in (includes or [])]
    clean_excludes = [strip_quotes(p) for p in (excludes or [])]
    clean_excludes.append(".git")

    def ignore_fn(directory: str, contents: list[str]) -> set[str]:
        rel_dir = os.path.relpath(directory, source)
        ignored: set[str] = set()
        for name in contents:
            if rel_dir == ".":
                rel_path = name
            else:
                rel_path = os.path.join(rel_dir, name)
            if matches_any(rel_path, name, clean_includes):
                continue
            if matches_any(rel_path, name, clean_excludes):
                ignored.add(name)
        return ignored

    shutil.copytree(
        source, dest, ignore=ignore_fn, dirs_exist_ok=True
    )


def strip_quotes(pattern: str) -> str:
    pattern = pattern.strip()
    if (pattern.startswith("'") and pattern.endswith("'")) or (
        pattern.startswith('"') and pattern.endswith('"')
    ):
        return pattern[1:-1]
    return pattern


def matches_any(
    rel_path: str, name: str, patterns: list[str]
) -> bool:
    for pattern in patterns:
        if fnmatch.fnmatch(name, pattern):
            return True
        if fnmatch.fnmatch(rel_path, pattern):
            return True
    return False
