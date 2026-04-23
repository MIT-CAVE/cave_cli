import json
import os
import sys
from pathlib import Path


def get_cache_dir() -> str:
    """
    Usage:

    - Returns the platform-appropriate cache directory for cave_cli

    Returns:

    - ``path``:
        - Type: str
        - What: Absolute path to the cache directory (created if missing)

    Notes:

    - Windows: %LOCALAPPDATA%/cave_cli
    - macOS: ~/Library/Caches/cave_cli
    - Linux: $XDG_CACHE_HOME/cave_cli (fallback ~/.cache/cave_cli)
    """
    if os.name == "nt":
        base_dir = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    elif sys.platform == "darwin":
        base_dir = os.path.expanduser("~/Library/Caches")
    else:
        base_dir = os.environ.get(
            "XDG_CACHE_HOME", os.path.expanduser("~/.cache")
        )

    path = os.path.join(base_dir, "cave_cli")
    os.makedirs(path, exist_ok=True)
    return path


def cache_path(name: str) -> str:
    return os.path.join(get_cache_dir(), f"{name}.json")


def load_entries(name: str) -> list[dict[str, str]]:
    """
    Usage:

    - Loads cached entries from a JSON file

    Requires:

    - ``name``:
        - Type: str
        - What: The cache name (e.g. "mapbox_tokens", "admin_emails")

    Returns:

    - ``entries``:
        - Type: list[dict[str, str]]
        - What: A list of dicts with "label" and "value" keys
    """
    path = cache_path(name)
    if not os.path.isfile(path):
        return []
    try:
        data = json.loads(Path(path).read_text())
        if isinstance(data, list):
            return [
                e
                for e in data
                if isinstance(e, dict) and "label" in e and "value" in e
            ]
    except (json.JSONDecodeError, OSError):
        pass
    return []


def save_entry(name: str, label: str, value: str) -> None:
    """
    Usage:

    - Appends a new labeled entry to a cache file, deduplicating by value

    Requires:

    - ``name``:
        - Type: str
        - What: The cache name

    - ``label``:
        - Type: str
        - What: A user-provided label for the entry

    - ``value``:
        - Type: str
        - What: The value to cache
    """
    entries = load_entries(name)
    entries = [e for e in entries if e["value"] != value]
    entries.append({"label": label, "value": value})
    Path(cache_path(name)).write_text(
        json.dumps(entries, indent=2) + "\n"
    )


def _mask_value(value: str) -> str:
    if len(value) <= 4:
        return "****"
    return f"****{value[-4:]}"


def prompt_cached_entry(
    name: str,
    prompt_new: str,
    prompt_label: str = "Label for this entry: ",
    mask: bool = False,
    default: str | None = None,
) -> str:
    """
    Usage:

    - Displays cached entries and lets the user pick one, enter a new
      value, use a default, or skip

    Requires:

    - ``name``:
        - Type: str
        - What: The cache name to load/save entries from

    - ``prompt_new``:
        - Type: str
        - What: Prompt text shown when asking for a new value

    Optional:

    - ``prompt_label``:
        - Type: str
        - What: Prompt text shown when asking for a label for the new entry
        - Default: "Label for this entry: "

    - ``mask``:
        - Type: bool
        - What: Whether to mask values in the display (show last 4 chars)
        - Default: False

    - ``default``:
        - Type: str | None
        - What: A default value offered as an option
        - Default: None

    Returns:

    - ``value``:
        - Type: str
        - What: The selected or entered value, or empty string if skipped
    """
    entries = load_entries(name)

    if not entries:
        try:
            value = input(
                f"{prompt_new}"
                f"{f' Leave blank for default ({default})' if default else ''}"
                ": "
            )
        except (EOFError, KeyboardInterrupt):
            value = ""
        if not value:
            return default or ""
        try:
            label = input(prompt_label)
        except (EOFError, KeyboardInterrupt):
            label = ""
        if not label:
            label = value if not mask else f"entry-{len(entries) + 1}"
        save_entry(name, label, value)
        return value

    print(f"\n{prompt_new}")
    print(f"Saved entries:")
    for i, entry in enumerate(entries, 1):
        display = (
            _mask_value(entry["value"]) if mask else entry["value"]
        )
        suffix = " (default)" if i == 1 else ""
        print(f"  [{i}] {entry['label']} ({display}){suffix}")
    print(f"  [N] Enter a new value")
    if default is not None:
        print(f"  [D] Use default ({default})")
    else:
        print(f"  [S] Skip")

    max_idx = len(entries)
    range_str = str(max_idx) if max_idx == 1 else f"1-{max_idx}"
    skip_key = "/D" if default else "/S"
    while True:
        try:
            choice = input(f"Choose [{range_str}/N{skip_key}]: ")
        except (EOFError, KeyboardInterrupt):
            return default or ""
        choice = choice.strip()

        if not choice:
            return entries[0]["value"]

        if choice.upper() == "N":
            try:
                value = input(f"{prompt_new}: ")
            except (EOFError, KeyboardInterrupt):
                return default or ""
            if not value:
                return default or ""
            try:
                label = input(prompt_label)
            except (EOFError, KeyboardInterrupt):
                label = ""
            if not label:
                label = (
                    value if not mask else f"entry-{len(entries) + 1}"
                )
            save_entry(name, label, value)
            return value

        if choice.upper() == "S" and default is None:
            return ""

        if choice.upper() == "D" and default is not None:
            return default

        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= max_idx:
                return entries[idx - 1]["value"]

        print(f"Invalid choice. Please try again.")
