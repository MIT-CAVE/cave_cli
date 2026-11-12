import argparse
import os
import re
import shutil
import sys
import tempfile
import tomllib
from pathlib import Path

from cave_cli.commands.create import remove_licence_info
from cave_cli.commands.reset import reset
from cave_cli.commands.run import run_cave
from cave_cli.commands.sync_cmd import sync_cmd
from cave_cli.utils.constants import HTTPS_URL
from cave_cli.utils.display import (
    print_section,
    step_done,
    step_fail,
    step_start,
)
from cave_cli.utils.env import upgrade_env
from cave_cli.utils.git import clone
from cave_cli.utils.logger import logger
from cave_cli.utils.subprocess import run
from cave_cli.utils.validate import confirm_action, find_app_dir, get_app
from cave_cli.utils.version import (
    get_app_version,
    get_breaking_instructions,
    is_breaking_change,
    version_tuple,
)


def fix_app_permissions(app_dir: str) -> None:
    """
    Usage:

    - Ensures all files in the app directory are owned by the current user
      so subsequent file moves and deletes do not fail with PermissionError.

    Requires:

    - ``app_dir``:
        - Type: str
        - What: Root directory of the CAVE application.
    """
    try:
        if hasattr(os, "getuid"):
            uid = os.getuid()
            gid = os.getgid()
            run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-v",
                    f"{app_dir}:/app",
                    "alpine",
                    "chown",
                    "-R",
                    f"{uid}:{gid}",
                    "/app",
                ]
            )
    except Exception:
        pass


def migrate_3_6_0(app_dir: str) -> list[str]:
    """
    Usage:

    - Applies 3.6.0 structural migrations to the CAVE application.
    - Moves legacy files, updates optional dependencies in pyproject.toml,
      restructures cave_api, and updates import paths.

    Requires:

    - ``app_dir``:
        - Type: str
        - What: Root directory of the CAVE application.

    Returns:

    - ``failures``:
        - Type: list[str]
        - What: List of error messages for any migration steps that failed.
    """
    failures: list[str] = []
    step_start("Applying 3.6.0 Migrations")
    app_path = Path(app_dir)

    # 1. Create legacy/ directory
    legacy_dir = app_path / "legacy"
    try:
        legacy_dir.mkdir(exist_ok=True)
    except Exception as e:
        logger.debug(f"Could not create legacy/ directory: {e}")

    # 2. Move requirements.txt into legacy/
    req_file = app_path / "requirements.txt"
    dest_req = legacy_dir / "requirements.txt"
    if req_file.exists():
        try:
            if dest_req.exists():
                dest_req.unlink()
            shutil.move(req_file, dest_req)
        except Exception as e:
            logger.debug(f"Could not move requirements.txt to legacy/: {e}")

    # 3. Move llm/ into legacy/
    llm_dir = app_path / "llm"
    dest_llm = legacy_dir / "llm"
    if llm_dir.exists() and llm_dir.is_dir():
        try:
            if dest_llm.exists():
                shutil.rmtree(dest_llm, ignore_errors=True)
            shutil.move(llm_dir, dest_llm)
        except Exception as e:
            logger.debug(f"Could not move llm/ to legacy/: {e}")

    # 4. Move utils/pyproject.toml and utils/extra_requirements.txt into legacy/utils/
    legacy_utils_dir = legacy_dir / "utils"
    utils_pyproject = app_path / "utils" / "pyproject.toml"
    utils_extra_req = app_path / "utils" / "extra_requirements.txt"
    if utils_pyproject.exists() or utils_extra_req.exists():
        try:
            legacy_utils_dir.mkdir(exist_ok=True)
            if utils_pyproject.exists():
                dest_pyproject = legacy_utils_dir / "pyproject.toml"
                if dest_pyproject.exists():
                    dest_pyproject.unlink()
                shutil.move(utils_pyproject, dest_pyproject)
            if utils_extra_req.exists():
                dest_extra = legacy_utils_dir / "extra_requirements.txt"
                if dest_extra.exists():
                    dest_extra.unlink()
                shutil.move(utils_extra_req, dest_extra)
        except Exception as e:
            logger.debug(f"Could not move utils legacy files: {e}")

    # 5. Remove VERSION file
    version_file = app_path / "VERSION"
    if version_file.exists():
        try:
            version_file.unlink()
        except Exception as e:
            logger.debug(f"Could not remove VERSION file: {e}")

    # 6. Move cave_core/models.py to legacy/cave_core/models.py if it exists
    models_file = app_path / "cave_core" / "models.py"
    if models_file.exists():
        try:
            legacy_cave_core = legacy_dir / "cave_core"
            legacy_cave_core.mkdir(exist_ok=True)
            dest_models = legacy_cave_core / "models.py"
            if dest_models.exists():
                dest_models.unlink()
            shutil.move(models_file, dest_models)
        except Exception as e:
            logger.debug(
                f"Could not move cave_core/models.py to legacy/cave_core/models.py: {e}"
            )

    # 7 & 8. Collect api requirements and update pyproject.toml optional-dependencies.api section
    api_requirements: list[str] = []
    cave_api_req = app_path / "cave_api" / "requirements.txt"
    if cave_api_req.exists():
        try:
            for line in cave_api_req.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    api_requirements.append(line)
        except Exception as e:
            logger.warn(f"Failed to read cave_api requirements: {e}")

    cave_api_pyproject = app_path / "cave_api" / "pyproject.toml"
    if cave_api_pyproject.exists():
        try:
            with open(cave_api_pyproject, "rb") as f:
                cave_api_pyproject_data = tomllib.loads(f.read().decode())
            deps = cave_api_pyproject_data.get("project", {}).get(
                "dependencies", []
            )
            for dep in deps:
                dep = dep.strip()
                if dep and dep not in api_requirements:
                    api_requirements.append(dep)
        except Exception as e:
            logger.warn(f"Failed to read cave_api pyproject.toml: {e}")

    seen = set()
    cleaned_requirements = []
    for req in api_requirements:
        if req not in seen:
            seen.add(req)
            cleaned_requirements.append(req)

    pyproject_path = app_path / "pyproject.toml"
    if cleaned_requirements and pyproject_path.exists():
        try:
            with open(pyproject_path, "rb") as f:
                content_bytes = f.read()
            content = content_bytes.decode()

            deps_str = "\n".join(f'  "{dep}",' for dep in cleaned_requirements)

            if "[project.optional-dependencies]" in content:
                if re.search(r"(?<![\w-])api\s*=\s*\[", content):
                    content = re.sub(
                        r"(?<![\w-])(api\s*=\s*\[)[^\]]*(\])",
                        f"\\1\n{deps_str}\n\\2",
                        content,
                        flags=re.DOTALL,
                    )
                else:
                    content = re.sub(
                        r"(\[project\.optional-dependencies\])",
                        f"\\1\napi = [\n{deps_str}\n]",
                        content,
                    )
            else:
                content += f"\n[project.optional-dependencies]\napi = [\n{deps_str}\n]\n"

            with open(pyproject_path, "wb") as f:
                f.write(content.encode())
        except Exception as e:
            msg = f"Failed to update pyproject.toml: {e}"
            logger.warn(msg)
            failures.append(msg)

    # 9. Move cave_api/tests/ to top-level tests/ before restructuring cave_api
    cave_api_tests = app_path / "cave_api" / "tests"
    tests_dest = app_path / "tests"
    if cave_api_tests.exists() and cave_api_tests.is_dir():
        try:
            if tests_dest.exists():
                shutil.rmtree(tests_dest, ignore_errors=True)
            shutil.copytree(
                cave_api_tests,
                tests_dest,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
        except Exception as e:
            logger.debug(f"Could not move cave_api/tests to tests/: {e}")

    # 10. Move old cave_api/ into legacy/cave_api/, then promote cave_api/cave_api/ to cave_api/
    cave_api = app_path / "cave_api"
    cave_api_inner = cave_api / "cave_api"
    legacy_cave_api = legacy_dir / "cave_api"
    legacy_inner = legacy_cave_api / "cave_api"

    if cave_api_inner.exists() and cave_api_inner.is_dir():
        try:
            temp_inner = app_path / "_cave_api_inner_tmp"
            if temp_inner.exists():
                shutil.rmtree(temp_inner, ignore_errors=True)
            shutil.copytree(
                cave_api_inner,
                temp_inner,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
            if legacy_cave_api.exists():
                shutil.rmtree(legacy_cave_api, ignore_errors=True)
                if legacy_cave_api.exists():
                    run(
                        [
                            "docker",
                            "run",
                            "--rm",
                            "-v",
                            f"{app_dir}:/app",
                            "alpine",
                            "rm",
                            "-rf",
                            "/app/legacy/cave_api",
                        ]
                    )
            shutil.move(cave_api, legacy_cave_api)
            shutil.move(temp_inner, cave_api)
        except Exception as e:
            msg = f"Failed to restructure cave_api directory: {e}"
            logger.warn(msg)
            failures.append(msg)
    elif (
        legacy_inner.exists()
        and legacy_inner.is_dir()
        and (not cave_api.exists() or not (cave_api / "api.py").exists())
    ):
        # Recovery: cave_api was already moved to legacy in a prior run, promote it to cave_api
        try:
            if cave_api.exists():
                shutil.rmtree(cave_api, ignore_errors=True)
            shutil.copytree(
                legacy_inner,
                cave_api,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
        except Exception as e:
            msg = f"Failed to promote legacy cave_api directory: {e}"
            logger.warn(msg)
            failures.append(msg)
    else:
        logger.debug(
            "Expected cave_api/cave_api directory not found, skipping API migration steps."
        )

    # 11. Update code references, skipping legacy/ and tool directories
    for py_file in app_path.rglob("*.py"):
        if any(
            part.startswith(".")
            or part in ("__pycache__", "venv", ".venv", ".nox", "legacy")
            for part in py_file.parts
        ):
            continue
        try:
            content = py_file.read_text()
            new_content = content.replace("cave_api.cave_api", "cave_api")
            new_content = new_content.replace("cave_api/cave_api", "cave_api")
            new_content = new_content.replace(
                'importlib.resources.files("cave_api") / "cave_api"',
                'importlib.resources.files("cave_api")',
            )
            new_content = new_content.replace(
                "importlib.resources.files('cave_api') / 'cave_api'",
                "importlib.resources.files('cave_api')",
            )

            if new_content != content:
                py_file.write_text(new_content)
        except Exception as e:
            msg = f"Failed to migrate code in {py_file}: {e}"
            logger.warn(msg)
            failures.append(msg)

    step_done("Applying 3.6.0 Migrations")
    return failures


def upgrade(args: argparse.Namespace) -> None:
    """
    Usage:

    - Upgrades the CAVE app in the current directory from the template repository.
    - Forces verbose logging mode so all outputs and errors are clearly visible.
    - Runs all file migrations and reformatting steps before Docker rebuilds.
    - Reports all failure points if any step fails and exits with non-zero status.

    Requires:

    - ``args``:
        - Type: argparse.Namespace
        - What: Parsed CLI arguments
    """
    # Force verbose mode for cave upgrade without an option not to
    args.verbose = True
    args.loglevel = "DEBUG"
    logger.set_level("DEBUG")

    failures: list[str] = []
    auto_yes = getattr(args, "yes", False)
    app_dir, app_name = get_app()
    url = getattr(args, "url", None) or HTTPS_URL
    version = getattr(args, "version", None)
    skip_env_upgrade = getattr(args, "skip_env_upgrade", False)

    # Fix file permissions in app directory so root-owned docker files don't block migrations
    fix_app_permissions(app_dir)

    # Collect existing api optional dependencies
    api_deps = []
    pyproject_path = os.path.join(app_dir, "pyproject.toml")
    if os.path.exists(pyproject_path):
        try:
            with open(pyproject_path, "rb") as f:
                pyproject = tomllib.load(f)
            api_deps = (
                pyproject.get("project", {})
                .get("optional-dependencies", {})
                .get("api", [])
            )
        except Exception:
            pass

    current_v = get_app_version(app_dir)
    current_version = version_tuple(current_v)
    is_pre_3_6 = (
        (current_version and current_version < (3, 6, 0))
        or (
            not current_version
            and os.path.exists(os.path.join(app_dir, "requirements.txt"))
        )
        or os.path.isdir(os.path.join(app_dir, "cave_api", "cave_api"))
    )
    target_v = version or "main"

    temp_dir = None
    # If target version is not a clear version tag, or if we need it for env upgrade anyway, clone it
    if not version_tuple(target_v) or not skip_env_upgrade:
        step_start(f"Fetching target version ({target_v})")
        temp_dir = tempfile.mkdtemp()
        clone_success = clone(url, temp_dir, branch=version or "main")
        if not clone_success:
            logger.warn(
                f"Failed to clone target repo from {url} (branch: {target_v})"
            )
            failures.append(f"Fetching target version from {url}")
        elif not version_tuple(target_v):
            target_v = get_app_version(temp_dir)
        step_done(f"Target version identified as {target_v}")

    msg = (
        "This will potentially update all files not in 'cave_api/' (note: "
        "'cave_api/docs/' and 'cave_api/examples/' will be updated), "
        "'tests/' or '.env' and reset your database"
    )
    if is_breaking_change(current_v, target_v):
        instructions = get_breaking_instructions(current_v, target_v)
        instruction_text = (
            "\n" + "\n".join(instructions) if instructions else ""
        )
        msg = f"Upgrading from {current_v} to {target_v} is a BREAKING CHANGE.{instruction_text}\n\n{msg}"

    confirm_action(msg, auto_yes=auto_yes)

    print_section("Upgrade")
    logger.info("Upgrading CAVE App via a Sync operation...")

    # ── Item A: Sync files from template repository ─────────────────────
    sync_args = argparse.Namespace(
        url=url,
        branch=version or "main",
        include=["cave_api/docs", "cave_api/examples"],
        exclude=[".env", ".gitignore", "cave_api/*", "tests/*"],
        yes=True,
        verbose=True,
        loglevel="DEBUG",
    )
    try:
        sync_ok = sync_cmd(sync_args, do_reset=False)
        if not sync_ok:
            failures.append("Syncing template files")
    except Exception as e:
        logger.error(f"Failed to sync files: {e}")
        failures.append(f"Syncing template files: {e}")

    # ── Item B: Restore 'api' optional dependencies in pyproject.toml ────
    if api_deps and os.path.exists(pyproject_path):
        try:
            with open(pyproject_path, "r") as f:
                content = f.read()

            deps_list_str = "\n".join(f'    "{dep}",' for dep in api_deps)

            if "[project.optional-dependencies]" in content:
                if re.search(r"(?<![\w-])api\s*=\s*\[", content):
                    content = re.sub(
                        r"(?<![\w-])(api\s*=\s*\[)[^\]]*(\])",
                        f"\\1\n{deps_list_str}\n  \\2",
                        content,
                        flags=re.DOTALL,
                    )
                else:
                    content = re.sub(
                        r"(\[project\.optional-dependencies\])",
                        f"\\1\napi = [\n{deps_list_str}\n]",
                        content,
                    )
            else:
                content += f"\n[project.optional-dependencies]\napi = [\n{deps_list_str}\n]\n"

            with open(pyproject_path, "w") as f:
                f.write(content)
            logger.info(
                "Preserved 'api' optional dependencies in pyproject.toml"
            )
        except Exception as e:
            logger.warn(f"Failed to preserve 'api' optional dependencies: {e}")
            failures.append(f"Preserving 'api' optional dependencies: {e}")

    # ── Item C: 3.6.0 Migrations (cave_api restructuring, etc.) ─────────
    target_version = version_tuple(target_v)
    target_is_at_least_3_6 = (
        (target_version and target_version >= (3, 6, 0))
        or (target_v == "main")
        or not target_version
    )
    if is_pre_3_6 and target_is_at_least_3_6:
        should_migrate = confirm_action(
            "Upgrading to 3.6.0 requires structural changes to your codebase "
            "(directory layout, import paths, and dependency files). "
            "We have an automated migration process to help apply these changes",
            auto_yes=auto_yes,
            continue_on_no=True,
        )
        if should_migrate:
            migration_failures = migrate_3_6_0(app_dir)
            failures.extend(migration_failures)

    # ── Item D: Upgrade environment file ─────────────────────────────────
    if not skip_env_upgrade:
        step_start("Upgrading environment file")
        try:
            if not temp_dir:
                temp_dir = tempfile.mkdtemp()
                clone(url, temp_dir, branch=version or "main")
            env_path = os.path.join(app_dir, ".env")
            upgrade_env(env_path, temp_dir)
            step_done("Upgrading environment file")
        except Exception as e:
            step_fail("Upgrading environment file", str(e))
            logger.error(f"Failed to upgrade environment file: {e}")
            failures.append(f"Upgrading environment file: {e}")

    # Clean up temp_dir if used
    if temp_dir:
        shutil.rmtree(temp_dir, ignore_errors=True)
        temp_dir = None

    # ── Item E: Remove license info ──────────────────────────────────────
    try:
        remove_licence_info(app_dir)
    except Exception as e:
        logger.warn(f"Failed to remove license info: {e}")
        failures.append(f"Removing license info: {e}")

    # ── Item F: Reset database and rebuild containers (cave reset) ──────
    # Temporarily stub api.py (and __init__.py) if present so that
    # database migrations and reset_db.sh can initialize cleanly without
    # failing on broken model code or legacy imports.
    cave_api_dir = Path(app_dir) / "cave_api"
    real_api_py = cave_api_dir / "api.py"
    backup_api_py = cave_api_dir / "api.py.real"
    real_init_py = cave_api_dir / "__init__.py"
    backup_init_py = cave_api_dir / "__init__.py.real"

    api_stubbed = False
    init_stubbed = False

    if real_api_py.exists():
        try:
            shutil.copy2(real_api_py, backup_api_py)
            real_api_py.write_text(
                "# Temporary stub created by cave upgrade for database reset\n"
                "def execute_command(*args, **kwargs):\n"
                "    return {}\n"
            )
            api_stubbed = True
        except Exception as e:
            logger.warn(f"Failed to create temporary stub api.py: {e}")

    if real_init_py.exists():
        try:
            shutil.copy2(real_init_py, backup_init_py)
            real_init_py.write_text("")
            init_stubbed = True
        except Exception as e:
            logger.warn(f"Failed to create temporary stub __init__.py: {e}")

    try:
        reset_args = argparse.Namespace(
            yes=True,
            verbose=True,
            loglevel="DEBUG",
            no_tui=True,
            raw=True,
            exit_on_error=False,
        )
        reset_code = reset(reset_args)
        if reset_code != 0:
            failures.append("Reset database and build containers (cave reset)")
    finally:
        # Always restore the real api.py and __init__.py
        if api_stubbed and backup_api_py.exists():
            try:
                shutil.move(backup_api_py, real_api_py)
            except Exception as e:
                logger.warn(f"Failed to restore original api.py: {e}")

        if init_stubbed and backup_init_py.exists():
            try:
                shutil.move(backup_init_py, real_init_py)
            except Exception as e:
                logger.warn(f"Failed to restore original __init__.py: {e}")

    # ── Item G: Update API docs ──────────────────────────────────────────
    if reset_code == 0:
        step_start("Updating API docs")
        docs_args = argparse.Namespace(
            entrypoint="./utils/generate_docs.sh",
            interactive=False,
            it=False,
            docker_args="",
            ip_port=None,
            yes=True,
            verbose=True,
            loglevel="DEBUG",
            no_tui=True,
            raw=True,
            exit_on_error=False,
        )
        docs_code = run_cave(app_dir, app_name, docs_args)
        if docs_code != 0:
            step_fail(
                "Updating API docs",
                f"Command failed with exit code {docs_code}",
            )
            failures.append("Updating API docs")
        else:
            step_done("Updating API docs")
    else:
        logger.warn("Skipping updating API docs due to reset failure.")
        failures.append("Updating API docs (skipped due to reset failure)")

    # ── Final Status Report ──────────────────────────────────────────────
    if failures:
        logger.error(
            "Upgrade encountered errors at the following failure points:"
        )
        for f in failures:
            logger.error(f"  - {f}")
        logger.error(
            "Please review the logs above and address the failure points (e.g. check why 'cave reset' failed)."
        )
        sys.exit(1)

    logger.success("Upgrade complete.")
