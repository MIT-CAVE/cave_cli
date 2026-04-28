import argparse
import fnmatch
import re
from collections import defaultdict

from cave_cli.utils.constants import VALID_REPOS
from cave_cli.utils.display import (
    GREEN,
    RED,
    RESET,
    print_section,
    step_done,
    step_start,
)
from cave_cli.utils.git import ls_remote_tags
from cave_cli.utils.logger import logger

RECENT_LIMIT = 5


def _version_sort_key(v: str) -> list[int]:
    return [int(x) for x in re.findall(r"\d+", v)]


def list_versions(args: argparse.Namespace) -> None:
    """
    Usage:

    - Lists available stable versions across all CAVE repositories,
      grouped by major version, with a presence check per repo

    Optional:

    - ``all``:
        - Type: bool
        - What: Show all versions instead of the 5 most recent per major
        - Default: False
    """
    show_all = getattr(args, "all", False)
    pattern = getattr(args, "pattern", None)

    repo_tags: dict[str, set[str]] = {}
    for repo in VALID_REPOS:
        step_start(f"Fetching {repo}")
        git_url = f"https://github.com/MIT-CAVE/{repo}.git"
        raw = ls_remote_tags(git_url)
        repo_tags[repo] = {
            t for t in raw if re.match(r"^v[0-9]+\.[0-9]+\.[0-9]+$", t)
        }
        step_done(f"Fetching {repo}")

    all_versions = sorted(
        (
            v for v in set().union(*repo_tags.values())
            if not pattern or fnmatch.fnmatch(v, pattern)
        ),
        key=_version_sort_key,
        reverse=True,
    )

    if not all_versions:
        logger.info("No stable versions found.")
        return

    by_major: dict[int, list[str]] = defaultdict(list)
    for v in all_versions:
        major = _version_sort_key(v)[0]
        by_major[major].append(v)

    repos = list(VALID_REPOS)
    version_w = max(len("Version"), max(len(v) for v in all_versions))
    col_w = [max(len(r), 3) for r in repos]
    pad = 2
    indent = "  "

    col_header = indent + f"{'Version':<{version_w}}"
    for r, w in zip(repos, col_w):
        col_header += " " * pad + f"{r:^{w}}"
    col_sep = indent + "-" * (len(col_header) - len(indent))

    for major in sorted(by_major.keys(), reverse=True):
        versions = by_major[major]
        shown = versions if show_all else versions[:RECENT_LIMIT]
        hidden = len(versions) - len(shown)

        print_section(f"v{major}.x.x Releases")
        print(col_header)
        print(col_sep)

        for v in shown:
            row = indent + f"{v:<{version_w}}"
            for r, w in zip(repos, col_w):
                mark = f"{GREEN}✓{RESET}" if v in repo_tags[r] else ""
                row += " " * pad + f"{mark:^{w + len(GREEN) + len(RESET) if mark else w}}"
            print(row)

        if hidden:
            print(f"\n  +{hidden} older versions, pass --all to see them")

    print("")
