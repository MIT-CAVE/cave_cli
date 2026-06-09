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


# Map of (major, minor, patch) threshold to list of instruction strings
BREAKING_CHANGES = {
    (3, 0, 0): [
        "The interface between CAVE App and CAVE Static has changed.",
        "You MUST upgrade cave_static to 2.4.0 or higher (in your .env file) to be compatible with CAVE App 3.0.0 or higher.",
        "If you choose to upgrade cave_static to 3.0.0 or higher, you will need to update your api to match the new interface."
    ],
    (3, 6, 0): [
        "The following changes are required to migrate to 3.6.0:",
        "  Replace 'requirements.txt' with 'pyproject.toml' for dependency management",
        "  Restructure 'cave_api/cave_api/' directly into 'cave_api/'",
        "  Move 'cave_api/tests/' to the project root as 'tests/'",
        "  Update all 'cave_api.cave_api' import paths to 'cave_api'",
        "  Move legacy files into 'legacy/' (requirements.txt, llm/, utils/pyproject.toml, utils/extra_requirements.txt)",
        "  Remove the 'VERSION' file",
        "The automated migration can handle all of the above.",
        "Any remaining custom code referencing the old structure may need manual updates.",
    ],
}


def get_breaking_instructions(current_v: str, target_v: str) -> list[str]:
    """
    Returns a list of instructions for all breaking changes crossed
    when upgrading from current_v to target_v.
    """
    if current_v == "Unknown" or not target_v:
        return []

    c = version_tuple(current_v)
    t = version_tuple(target_v)

    if not c or not t:
        return []

    instructions = []
    # Sort thresholds to ensure we process them in chronological order
    for threshold in sorted(BREAKING_CHANGES.keys()):
        # If the threshold is greater than our current version
        # AND less than or equal to our target version, it's a break we're crossing.
        if c < threshold <= t:
            items = BREAKING_CHANGES[threshold]
            if isinstance(items, str):
                instructions.append(f"- {items}")
            else:
                for item in items:
                    instructions.append(f"- {item}")

    return instructions


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
