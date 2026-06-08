import re
import tomllib
from pathlib import Path

def get_version_from_req_list(req_key: str, req_strings: list[str]) -> str:
    """
    Given a req string like: cave_utils==1.2.3, cave_utils>=1.2.3, cave_utils<=1.2.3, cave_utils~=1.2.3b1
    Extracts the version number (1.2.3, 1.2.3b1, etc) and returns it with a 'v' prefix (e.g. v1.2.3)
    """
    for req_string in req_strings:
        if req_key in req_string:
            match = re.search(r"([><=~!]*)(\d+\.\d+\.\d+[a-zA-Z0-9]*)", req_string)
            if match:
                return f"v{match.group(2)}"
    return "Unknown"


def get_app_version(app_dir: str) -> str:
    """
    Retrieves the version of the CAVE app in the specified directory.
    Checks pyproject.toml first, then falls back to a VERSION file.
    """
    app_path = Path(app_dir)
    pyproject_file = app_path / "pyproject.toml"
    version_file = app_path / "VERSION"

    if pyproject_file.is_file():
        try:
            with open(pyproject_file, "rb") as f:
                pyproject_data = tomllib.load(f)
            version = pyproject_data.get("project", {}).get("version", "Unknown")
            if version != "Unknown":
                return f"v{version}" if not version.startswith("v") else version
        except Exception:
            pass

    if version_file.is_file():
        try:
            version = version_file.read_text().strip()
            if version:
                return f"v{version}" if not version.startswith("v") else version
        except Exception:
            pass

    return "Unknown"


def version_tuple(v: str) -> tuple[int, ...]:
    """
    Parses a version string into a comparable tuple of integers.
    Handles 'v' prefix and other non-digit characters by extracting only digits.
    """
    return tuple(int(x) for x in re.findall(r"\d+", v))


def is_breaking_change(current_v: str, target_v: str) -> bool:
    """
    Checks if upgrading from current_v to target_v is a breaking change.
    Break points are:
    - Major version changes
    - Crossing the 3.6.0 threshold
    """
    if current_v == "Unknown" or not target_v:
        return False

    c = version_tuple(current_v)
    t = version_tuple(target_v)

    if not c or not t:
        return False

    # Major version change
    if c[0] < t[0]:
        return True

    # Specific break point: 3.6.0
    # If we are below 3.6.0 and upgrading to 3.6.0 or higher
    break_point = (3, 6, 0)
    if c < break_point <= t:
        return True

    return False
