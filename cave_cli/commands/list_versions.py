import argparse
import re

from cave_cli.utils.constants import CHAR_LINE, VALID_REPOS
from cave_cli.utils.git import ls_remote_heads, ls_remote_tags
from cave_cli.utils.logger import logger


def version_sort_key(v: str) -> list[int]:
    return [int(x) for x in re.findall(r"\d+", v)]


def list_versions(args: argparse.Namespace) -> None:
    """
    Usage:

    - Lists all available stable versions of a CAVE repository
    """
    pattern = getattr(args, "pattern", "*")
    if pattern.startswith("v"):
        pattern = pattern[1:]

    repo = getattr(args, "repo", "cave_app")
    if repo not in VALID_REPOS:
        logger.error(
            f"Invalid repo provided. Must be one of "
            f"{list(VALID_REPOS)}."
        )
        return

    git_url = f"https://github.com/MIT-CAVE/{repo}.git"

    raw_heads = ls_remote_heads(git_url)
    stable_branches = [
        b
        for b in raw_heads
        if re.match(r"^V[0-9]+$", b)
        and (pattern == "*" or re.search(pattern, b[1:]))
    ]

    raw_tags = ls_remote_tags(git_url)
    stable_tags = [
        t
        for t in raw_tags
        if re.match(r"^v[0-9]+\.[0-9]+\.[0-9]+$", t)
        and (pattern == "*" or re.search(pattern, t[1:]))
    ]

    stable_tags.sort(key=version_sort_key)
    stable_branches.sort(key=version_sort_key)

    print(f"CAVE Versions (repo: {repo}):")

    last_major = None
    for tag in stable_tags:
        major = tag.split(".")[0]
        if major != last_major:
            major_no_v = major.lstrip("v")
            print(f"\n{CHAR_LINE}")
            print(f"Version {major_no_v}:")
            print(CHAR_LINE)
            branch = f"V{major_no_v}"
            if branch in stable_branches:
                print(f"  {branch} (latest version of {major})")
            last_major = major
        print(f"  {tag}")
