import fnmatch
import os
import shlex
import shutil
from pathlib import Path

from cave_cli.utils.logger import logger


def can_create_symlinks() -> bool:
    """
    Check if the current user/OS environment has permission to create symbolic links.
    On Windows, this requires Developer Mode or Administrator privileges.
    """
    import tempfile

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_file = os.path.join(tmpdir, "file")
            tmp_link = os.path.join(tmpdir, "link")
            with open(tmp_file, "w") as f:
                f.write("")
            os.symlink(tmp_file, tmp_link)
            return True
    except OSError:
        return False


def normalize_pattern(pattern: str) -> str:
    """
    Usage:

    - Normalizes a file pattern by standardizing path separators, removing
      leading relative markers (./) and trailing slashes.

    Requires:

    - ``pattern``:
        - Type: str
        - What: Pattern to normalize

    Returns:

    - ``normalized``:
        - Type: str
        - What: Clean normalized pattern string
    """
    p = pattern.strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    if p.startswith("/") and len(p) > 1:
        p = p.lstrip("/")
    if p.endswith("/") and len(p) > 1:
        p = p.rstrip("/")
    return p


def clean_patterns(patterns: list[str] | None) -> list[str]:
    """
    Usage:

    - Parses a list of pattern strings that may contain whitespace-separated
      or quoted tokens into individual normalized pattern strings.

    Optional:

    - ``patterns``:
        - Type: list[str] | None
        - What: List of raw pattern strings
        - Default: None

    Returns:

    - ``cleaned``:
        - Type: list[str]
        - What: List of individual stripped and normalized pattern strings
    """
    if not patterns:
        return []
    result: list[str] = []
    for item in patterns:
        item = item.strip()
        if not item:
            continue
        try:
            tokens = shlex.split(item)
        except ValueError:
            tokens = item.split()
        for token in tokens:
            cleaned = strip_quotes(token)
            if cleaned:
                cleaned = normalize_pattern(cleaned)
                if cleaned and cleaned not in result:
                    result.append(cleaned)
    return result


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
    clean_includes = clean_patterns(includes)
    clean_excludes = clean_patterns(excludes)
    if ".git" not in clean_excludes:
        clean_excludes.append(".git")

    symlinks_supported = can_create_symlinks()

    def ignore_fn(directory: str, contents: list[str]) -> set[str]:
        rel_dir = os.path.relpath(directory, source)
        ignored: set[str] = set()
        for name in contents:
            if rel_dir == ".":
                rel_path = name
            else:
                rel_path = os.path.join(rel_dir, name)

            is_ignored = False
            if not matches_any(rel_path, name, clean_includes):
                if matches_any(rel_path, name, clean_excludes):
                    ignored.add(name)
                    is_ignored = True

            if not is_ignored:
                # If we are syncing this file/directory, resolve any conflicts at the destination.
                dst_path = os.path.join(dest, rel_path)
                if os.path.lexists(dst_path):
                    src_path = os.path.join(directory, name)
                    # If both are concrete directories, let shutil.copytree's dirs_exist_ok merge them.
                    # Otherwise (file vs file, link vs file, etc.), we must remove the destination path
                    # first to avoid conflicts and FileExistsError (especially when copying symbolic links).
                    is_src_dir = os.path.isdir(src_path) and not os.path.islink(
                        src_path
                    )
                    is_dst_dir = os.path.isdir(dst_path) and not os.path.islink(
                        dst_path
                    )
                    if not (is_src_dir and is_dst_dir):
                        if is_dst_dir:
                            shutil.rmtree(dst_path)
                        else:
                            os.unlink(dst_path)

        return ignored

    shutil.copytree(
        source,
        dest,
        ignore=ignore_fn,
        dirs_exist_ok=True,
        symlinks=symlinks_supported,
    )


def strip_quotes(pattern: str) -> str:
    """
    Usage:

    - Strips matching enclosing single or double quotes from a pattern string.

    Requires:

    - ``pattern``:
        - Type: str
        - What: String to strip quotes from

    Returns:

    - ``stripped``:
        - Type: str
        - What: String without outer quotes
    """
    pattern = pattern.strip()
    if (pattern.startswith("'") and pattern.endswith("'")) or (
        pattern.startswith('"') and pattern.endswith('"')
    ):
        return pattern[1:-1]
    return pattern


def matches_any(rel_path: str, name: str, patterns: list[str]) -> bool:
    """
    Usage:

    - Checks if a relative path or filename matches any of the given patterns.

    Requires:

    - ``rel_path``:
        - Type: str
        - What: Relative path of the file or directory

    - ``name``:
        - Type: str
        - What: Base name of the file or directory

    - ``patterns``:
        - Type: list[str]
        - What: List of glob patterns to test against

    Returns:

    - ``matched``:
        - Type: bool
        - What: True if rel_path or name matches any pattern
    """
    norm_rel_path = rel_path.replace("\\", "/")
    norm_name = name.replace("\\", "/")
    for pattern in patterns:
        norm_pattern = pattern.replace("\\", "/")
        if fnmatch.fnmatch(norm_name, norm_pattern):
            return True
        if fnmatch.fnmatch(norm_rel_path, norm_pattern):
            return True
        if (
            "*" not in norm_pattern
            and "?" not in norm_pattern
            and "[" not in norm_pattern
            and norm_rel_path.startswith(norm_pattern.rstrip("/") + "/")
        ):
            return True
    return False
