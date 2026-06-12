import argparse
import os
import re
import shutil
import tempfile

from cave_cli.commands.create import remove_licence_info
from cave_cli.commands.run import run_cave
from cave_cli.commands.sync_cmd import sync_cmd
from cave_cli.commands.reset import reset
from cave_cli.utils.constants import HTTPS_URL
from cave_cli.utils.display import print_section, step_done, step_start
from cave_cli.utils.env import upgrade_env
from cave_cli.utils.git import clone
from cave_cli.utils.logger import logger
from cave_cli.utils.validate import confirm_action, find_app_dir, get_app
from cave_cli.utils.version import (
    get_app_version,
    get_breaking_instructions,
    is_breaking_change,
    version_tuple,
)


def migrate_3_6_0(app_dir: str) -> None:
    import re
    import tomllib
    from pathlib import Path

    step_start("Applying 3.6.0 Migrations")
    app_path = Path(app_dir)

    # Create legacy/ directory
    legacy_dir = app_path / "legacy"
    legacy_dir.mkdir(exist_ok=True)

    # Move requirements.txt into legacy/
    req_file = app_path / "requirements.txt"
    if req_file.exists():
        shutil.move(req_file, legacy_dir / "requirements.txt")

    # Move llm/ into legacy/
    llm_dir = app_path / "llm"
    if llm_dir.exists() and llm_dir.is_dir():
        shutil.move(llm_dir, legacy_dir / "llm")

    # Move utils/pyproject.toml and utils/extra_requirements.txt into legacy/utils/
    legacy_utils_dir = legacy_dir / "utils"
    utils_pyproject = app_path / "utils" / "pyproject.toml"
    utils_extra_req = app_path / "utils" / "extra_requirements.txt"
    if utils_pyproject.exists() or utils_extra_req.exists():
        legacy_utils_dir.mkdir(exist_ok=True)
        if utils_pyproject.exists():
            shutil.move(utils_pyproject, legacy_utils_dir / "pyproject.toml")
        if utils_extra_req.exists():
            shutil.move(utils_extra_req, legacy_utils_dir / "extra_requirements.txt")

    # Remove VERSION file
    version_file = app_path / "VERSION"
    if version_file.exists():
        version_file.unlink()

    # Collect cave_api requirements before moving the directory
    cave_api_requirements = []
    cave_api_req = app_path / "cave_api" / "requirements.txt"
    if cave_api_req.exists():
        try:
            cave_api_requirements.extend(cave_api_req.read_text().splitlines())
        except Exception as e:
            logger.warning(f"Failed to read cave_api requirements: {e}")

    # Update pyproject.toml with cave_api optional dependencies
    pyproject_path = app_path / "pyproject.toml"
    if cave_api_requirements and pyproject_path.exists():
        try:
            with open(pyproject_path, "rb") as f:
                content = f.read()
                pyproject = tomllib.load(f)

            existing_deps = pyproject.get("project", {}).get("dependencies", [])
            new_deps = [req for req in cave_api_requirements if req not in existing_deps]

            if new_deps:
                deps_str = "\n".join(f'  "{dep}",' for dep in new_deps)
                cave_api_block = f'\n[project.optional-dependencies]\ncave_api = [\n{deps_str}\n]\n'

                if "[project.optional-dependencies]" in content.decode():
                    content = re.sub(
                        r'(\[project\.optional-dependencies\].*?cave_api\s*=\s*\[)[^\]]*(\])',
                        f'\\1\n{deps_str}\n\\2',
                        content.decode(),
                        flags=re.DOTALL
                    ).encode()
                else:
                    content = content + cave_api_block.encode()

                with open(pyproject_path, "wb") as f:
                    f.write(content)

        except Exception as e:
            logger.warning(f"Failed to update pyproject.toml: {e}")

    # Move cave_api/tests/ to top-level tests/ before restructuring cave_api
    cave_api_tests = app_path / "cave_api" / "tests"
    tests_dest = app_path / "tests"
    if cave_api_tests.exists() and cave_api_tests.is_dir():
        if tests_dest.exists():
            shutil.rmtree(tests_dest)
        shutil.copytree(cave_api_tests, tests_dest)

    # Move old cave_api/ into legacy/cave_api/, then promote cave_api/cave_api/ to cave_api/
    cave_api = app_path / "cave_api"
    cave_api_inner = cave_api / "cave_api"
    legacy_cave_api = legacy_dir / "cave_api"

    if cave_api_inner.exists() and cave_api_inner.is_dir():
        shutil.move(cave_api, legacy_cave_api)
        shutil.copytree(legacy_cave_api / "cave_api", cave_api)
    else:
        logger.warning("Expected cave_api/cave_api directory not found, skipping API migration steps.")

    # Update code references, skipping legacy/ and tool directories
    for py_file in app_path.rglob("*.py"):
        if any(
            part.startswith(".") or part in ("__pycache__", "venv", ".venv", ".nox", "legacy")
            for part in py_file.parts
        ):
            continue
        try:
            content = py_file.read_text()
            new_content = content.replace("cave_api.cave_api", "cave_api")
            new_content = new_content.replace("cave_api/cave_api", "cave_api")
            new_content = new_content.replace(
                'importlib.resources.files("cave_api") / "cave_api"', 'importlib.resources.files("cave_api")'
            )
            new_content = new_content.replace(
                "importlib.resources.files('cave_api') / 'cave_api'", "importlib.resources.files('cave_api')"
            )

            if new_content != content:
                py_file.write_text(new_content)
        except Exception as e:
            logger.warning(f"Failed to migrate code in {py_file}: {e}")

    step_done("Applying 3.6.0 Migrations")


def upgrade(args: argparse.Namespace) -> None:
    """
    Usage:

    - Upgrades the CAVE app in the current directory from the template repository
    """
    auto_yes = getattr(args, "yes", False)
    app_dir, app_name = get_app()
    url = getattr(args, "url", None) or HTTPS_URL
    version = getattr(args, "version", None)
    skip_env_upgrade = getattr(args, "skip_env_upgrade", False)

    current_v = get_app_version(app_dir)
    target_v = version or "main"

    temp_dir = None
    # If target version is not a clear version tag, or if we need it for env upgrade anyway, clone it
    if not version_tuple(target_v) or not skip_env_upgrade:
        step_start(f"Fetching target version ({target_v})")
        temp_dir = tempfile.mkdtemp()
        clone(url, temp_dir, branch=version or "main")
        if not version_tuple(target_v):
            target_v = get_app_version(temp_dir)
        step_done(f"Target version identified as {target_v}")

    msg = "This will potentially update all files not in 'cave_api/', 'tests/' or '.env' and reset your database"
    if is_breaking_change(current_v, target_v):
        instructions = get_breaking_instructions(current_v, target_v)
        instruction_text = "\n" + "\n".join(instructions) if instructions else ""
        msg = f"Upgrading from {current_v} to {target_v} is a BREAKING CHANGE.{instruction_text}\n\n{msg}"

    confirm_action(msg, auto_yes=auto_yes)

    print_section("Upgrade")
    logger.info("Upgrading CAVE App via a Sync operation...")

    sync_args = argparse.Namespace(
        url=url,
        branch=version or "main",
        include=["cave_api/docs"],
        exclude=[".env", ".gitignore", "cave_api/*", "tests/*"],
        yes=True,
        verbose=getattr(args, "verbose", False),
        loglevel=getattr(args, "loglevel", "INFO"),
    )

    sync_cmd(sync_args, do_reset=False)

    current_version = version_tuple(current_v)
    target_version = version_tuple(target_v)
    if current_version and target_version and current_version < (3, 6, 0) <= target_version:
        should_migrate = confirm_action(
            "Upgrading to 3.6.0 requires structural changes to your codebase "
            "(directory layout, import paths, and dependency files). "
            "We have an automated migration process to help apply these changes",
            auto_yes=auto_yes,
            continue_on_no=True,
        )
        if should_migrate:
            migrate_3_6_0(app_dir)
    
    reset_args = argparse.Namespace(
        yes=True,
        verbose=getattr(args, "verbose", False),
        loglevel=getattr(args, "loglevel", "INFO"),
    )
    reset(reset_args)

    if not skip_env_upgrade:

        step_start("Upgrading environment file")
        # temp_dir should already be created and cloned if not skipped
        if not temp_dir:
            temp_dir = tempfile.mkdtemp()
            clone(url, temp_dir, branch=version or "main")
        env_path = os.path.join(app_dir, ".env")
        upgrade_env(env_path, temp_dir)
        step_done("Upgrading environment file")

    if temp_dir:
        shutil.rmtree(temp_dir, ignore_errors=True)

    remove_licence_info(app_dir)

    step_start("Updating API docs")
    docs_args = argparse.Namespace(
        entrypoint="./utils/generate_docs.sh",
        interactive=False,
        it=False,
        docker_args="",
        ip_port=None,
        yes=True,
        verbose=getattr(args, "verbose", False),
        loglevel=getattr(args, "loglevel", "INFO"),
    )
    run_cave(app_dir, app_name, docs_args)
    step_done("Updating API docs")

    logger.success("Upgrade complete.")
