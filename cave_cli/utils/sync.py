import fnmatch
import os
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
                    is_src_dir = os.path.isdir(src_path) and not os.path.islink(src_path)
                    is_dst_dir = os.path.isdir(dst_path) and not os.path.islink(dst_path)
                    if not (is_src_dir and is_dst_dir):
                        if is_dst_dir:
                            shutil.rmtree(dst_path)
                        else:
                            os.unlink(dst_path)
                            
        return ignored

    shutil.copytree(
        source, dest, ignore=ignore_fn, dirs_exist_ok=True, symlinks=symlinks_supported
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
