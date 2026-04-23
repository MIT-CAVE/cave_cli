# CAVE CLI: Development Guide

## Project Purpose

`cave_cli` is a Python CLI for creating and managing Docker-based CAVE web applications. Developed by MIT-CAVE (Center for Transportation & Logistics). Licensed under Apache 2.0.

Core capabilities:

- **App creation** -- clone the `cave_app` template, configure `.env`, build Docker images, and initialize git
- **App lifecycle** -- run, reset, upgrade, sync, test, prettify, kill, and purge CAVE apps
- **Docker orchestration** -- manages multi-container stacks (Django, Postgres, Redis/Valkey, Nginx)
- **CLI self-management** -- update and uninstall the CLI itself via pip

Repo: `MIT-CAVE/cave_cli` on GitHub

---

## Directory Layout (relevant files only)

```
cave_cli/
  __init__.py              # Package version via importlib.metadata
  cli.py                   # Entry point: argparse command/subcommand definitions + dispatch
  commands/
    __init__.py
    create.py              # Create a new CAVE app from the template repository
    run.py                 # Build and run app Docker containers (Django, DB, Redis, Nginx)
    reset.py               # Remove containers/volumes and rebuild from scratch
    upgrade.py             # Upgrade app files from upstream template via sync
    sync_cmd.py            # Merge files from another git repository into the app
    test.py                # Run tests in cave_api/tests/ via Docker entrypoint
    prettify.py            # Format code with autoflake and black via Docker entrypoint
    list_cmd.py            # List running CAVE apps with their URLs
    kill.py                # Stop Docker containers for an app (or all apps)
    purge.py               # Remove an app directory and all its Docker resources
    list_versions.py       # List available CAVE app versions from remote git tags
    update.py              # Update the CLI itself via pip install --upgrade from GitHub
    uninstall.py           # Remove the CLI package via pip uninstall
    version.py             # Print CLI version and app-specific versions
  utils/
    __init__.py
    constants.py           # Shared constants: URLs, regex patterns, env variable lists
    docker.py              # Docker operations: check, build, run, remove, inspect
    env.py                 # .env file parsing, writing, validation, interactive creation
    git.py                 # Git operations: clone, init, add, commit, fetch, checkout, ls-remote
    logger.py              # CaveLogger -- multi-level logger (DEBUG/INFO/WARN/ERROR/SILENT)
    net.py                 # Network utilities: port availability, IP:port parsing
    subprocess.py          # Subprocess wrappers: run(), run_and_log(), version_tuple()
    sync.py                # File sync with include/exclude pattern matching
    validate.py            # App name/directory validation, app discovery, user confirmation
legacy/
  cave.sh                  # Previous Bash CLI (v2.x)
  cave-1.4.0.sh            # Legacy Bash CLI (v1.4.0)
  help.txt                 # Help text for v2.x CLI
  help-1.4.0.txt           # Help text for v1.4.0 CLI
  install.sh               # Legacy installer script
  utils.sh                 # Legacy shared Bash utilities
pyproject.toml             # Package metadata, entry point, black config
setup.cfg                  # setuptools package discovery
requirements.txt           # Dev dependencies (black, autoflake, pdoc, twine, build)
```

---

## Installation & Development Setup

The CLI is a pure Python package with no runtime dependencies. Install in editable mode for development:

```bash
pip install -r requirements.txt
```

This installs dev tools (black, autoflake, pdoc, twine, build) and the package itself in editable mode (`-e .`).

The entry point is defined in `pyproject.toml`:

```
[project.scripts]
cave = "cave_cli.cli:main"
```

After installation, the `cave` command is available globally. In editable mode, changes to the source take effect immediately.

---

## CLI Commands

| Command | Aliases | Description |
|---|---|---|
| `cave create <name>` | | Create a new CAVE app from the template repository |
| `cave run [ip:port]` | `start` | Build and run the app's Docker containers |
| `cave reset` | `reset-db` | Remove containers/volumes and rebuild from scratch |
| `cave upgrade` | | Upgrade app files from upstream template |
| `cave sync --url <url>` | | Merge files from another repo into the app |
| `cave test` | | Run tests in `cave_api/tests/` |
| `cave prettify` | | Format code with autoflake and black |
| `cave list` | | List running CAVE apps |
| `cave kill` | | Stop containers for an app |
| `cave purge <path>` | | Remove an app and all its Docker resources |
| `cave list-versions` | `lv` | List available CAVE app versions |
| `cave update` | | Update the CLI itself via pip |
| `cave uninstall` | | Remove the CLI package |
| `cave version` | | Print CLI and app version information |

### Global Flags

| Flag | Description |
|---|---|
| `-v`, `--verbose` | Enable debug logging (shorthand for `--loglevel DEBUG`) |
| `--loglevel LEVEL` | Set log level: `DEBUG`, `INFO`, `WARN`, `ERROR`, `SILENT` |
| `-y`, `--yes` | Automatically answer confirmation prompts with yes |
| `-V`, `--version` | Show CLI version number and exit |

---

## Core Architecture

### Entry Point & Dispatch

`cave_cli/cli.py:main()` defines all subcommands via `argparse` subparsers, normalizes aliases, configures logging, and dispatches to the appropriate command function. Each command is lazily imported at dispatch time.

### Command Pattern

Most commands that operate on an existing app follow this pattern:

1. Call `get_app()` to discover the app directory (walks up from `cwd` looking for `manage.py` + `cave_core/`)
2. Perform the command's work using `app_dir` and `app_name`
3. Many commands delegate to `run_cave(app_dir, app_name, args)` which orchestrates the Docker container stack

### Docker Container Stack

Each CAVE app runs as a multi-container Docker deployment:

| Container | Image | Purpose |
|---|---|---|
| `{app_name}_django` | `cave-app:{app_name}` | Django application server |
| `{app_name}_db_host` | `postgres:latest` (configurable) | PostgreSQL database |
| `{app_name}_redis_host` | `valkey/valkey:7` (configurable) | Cache (Redis/Valkey) |
| `{app_name}_nginx_host` | `nginx` | Reverse proxy (LAN hosting only) |

Network: `cave-net:{app_name}`
Volumes: `{app_name}_pg_volume`, `{app_name}_redis_volume`

### App Discovery

`validate.py:find_app_dir()` walks up the directory tree from `cwd` (or a given start path) looking for a valid CAVE app. Validation checks for `manage.py`, `cave_core/`, `cave_api/`, `cave_app/`, `.env`, `requirements.txt`, and `Dockerfile`.

`validate.py:get_app()` wraps `find_app_dir()` and returns both the absolute path and the directory basename as the app name.

### Logging

`CaveLogger` in `logger.py` is a module-level singleton. Output goes to stderr in the format `LEVEL: message`. Log level is set from the `--loglevel` flag or `--verbose` shorthand. The `header()` method prints separator lines around a title.

### Subprocess Execution

`subprocess.py` provides two wrappers:

- `run()` -- general subprocess execution with options for capture, check, cwd, and interactive I/O passthrough
- `run_and_log()` -- runs a command and pipes each output line through the logger at a specified level

---

## Coding Conventions

### Formatting

Run before committing:

```bash
autoflake --remove-all-unused-imports --in-place --recursive cave_cli/
black cave_cli/
```

Black is configured in `pyproject.toml`:

```toml
[tool.black]
line-length = 80
target-version = ['py311']
```

### Type Hints

All functions and methods must have type hints.

- **Basic types**: use builtins directly -- `int`, `str`, `float`, `dict`, `list`, `tuple`
- **Union**: use `|` operator -- `str | None`, `int | float`
- **Complex dicts**: `dict[str, str]`, `dict[str, int]`, etc.

```python
def clone(url: str, dest: str, branch: str | None = None) -> bool: ...
def get_app(start: str | None = None) -> tuple[str, str]: ...
def run_detached(name: str, image: str, volumes: list[str] | None = None) -> None: ...
```

### Docstrings

CAVE CLI uses a custom structured docstring format:

```python
def method(self, param1: str, param2: int = 0) -> str:
    """
    Usage:

    - High-level description of what this method does.

    Requires:

    - ``param1``:
        - Type: str
        - What: Description of what this parameter does.

    Optional:

    - ``param2``:
        - Type: int
        - What: Description of what this parameter does.
        - Default: 0

    Returns:

    - ``return_value``:
        - Type: str
        - What: What the return value represents.

    Notes:

    - Any important implementation details or surprises.
    """
```

**Rules:**
- `Usage:` is always the first section -- plain English, bullet points
- `Requires:` covers parameters without defaults; `Optional:` covers parameters with defaults
- Each parameter entry: double-backtick name, then `Type` -> `What` -> `Default` (optional params) -> `Note` (if needed) sub-bullets
- `Returns:` describes the return value with the same sub-bullet format
- `Notes:` for implementation details, non-obvious behavior, or constraints
- Omit any section that doesn't apply

### Error Handling

- Validation errors and fatal conditions call `logger.error()` followed by `sys.exit(1)`
- Subprocess failures are checked via `result.returncode`
- User confirmation uses `confirm_action()` which prompts and exits on refusal
- `EOFError` and `KeyboardInterrupt` are caught on all `input()` calls

### Imports

- Standard library imports first, then package imports
- Lazy imports inside dispatch branches in `cli.py` to avoid loading unused modules
- Relative imports within the package: `from cave_cli.utils.logger import logger`

### Other Rules

- **No runtime dependencies**: the package has zero external dependencies (only stdlib + Docker/git on PATH)
- **Python >= 3.11**: required for `|` union types and `importlib.metadata`
- **No automated tests**: verify changes by running CLI commands manually against a CAVE app
- **Sensitive files**: `.env`, `MAPBOX_TOKEN`, and `CONFIG` are gitignored -- never commit these
