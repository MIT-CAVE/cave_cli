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

    # Move cave_core/models.py to legacy/cave_core/models.py if it exists
    models_file = app_path / "cave_core" / "models.py"
    if models_file.exists():
        try:
            legacy_cave_core = legacy_dir / "cave_core"
            legacy_cave_core.mkdir(exist_ok=True)
            shutil.move(models_file, legacy_cave_core / "models.py")
        except Exception as e:
            logger.warn(f"Failed to move cave_core/models.py to legacy/cave_core/models.py: {e}")

    # Collect api requirements from cave_api/requirements.txt and cave_api/pyproject.toml
    # before moving/restructuring the cave_api directory
    api_requirements = []
    
    # 1. Pull from cave_api/requirements.txt
    cave_api_req = app_path / "cave_api" / "requirements.txt"
    if cave_api_req.exists():
        try:
            for line in cave_api_req.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    api_requirements.append(line)
        except Exception as e:
            logger.warn(f"Failed to read cave_api requirements: {e}")

    # 2. Pull from cave_api/pyproject.toml
    cave_api_pyproject = app_path / "cave_api" / "pyproject.toml"
    if cave_api_pyproject.exists():
        try:
            with open(cave_api_pyproject, "rb") as f:
                cave_api_pyproject_data = tomllib.loads(f.read().decode())
            deps = cave_api_pyproject_data.get("project", {}).get("dependencies", [])
            for dep in deps:
                dep = dep.strip()
                if dep and dep not in api_requirements:
                    api_requirements.append(dep)
        except Exception as e:
            logger.warn(f"Failed to read cave_api pyproject.toml: {e}")

    # Deduplicate requirements while preserving order
    seen = set()
    cleaned_requirements = []
    for req in api_requirements:
        if req not in seen:
            seen.add(req)
            cleaned_requirements.append(req)

    # Update pyproject.toml optional-dependencies.api section
    pyproject_path = app_path / "pyproject.toml"
    if cleaned_requirements and pyproject_path.exists():
        try:
            with open(pyproject_path, "rb") as f:
                content_bytes = f.read()
            content = content_bytes.decode()

            deps_str = "\n".join(f'  "{dep}",' for dep in cleaned_requirements)
            
            if "[project.optional-dependencies]" in content:
                if re.search(r"api\s*=\s*\[", content):
                    content = re.sub(
                        r"(api\s*=\s*\[)[^\]]*(\])",
                        f"\\1\n{deps_str}\n\\2",
                        content,
                        flags=re.DOTALL
                    )
                else:
                    content = re.sub(
                        r"(\[project\.optional-dependencies\])",
                        f"\\1\napi = [\n{deps_str}\n]",
                        content
                    )
            else:
                content += f'\n[project.optional-dependencies]\napi = [\n{deps_str}\n]\n'

            with open(pyproject_path, "wb") as f:
                f.write(content.encode())

        except Exception as e:
            logger.warn(f"Failed to update pyproject.toml: {e}")

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
        logger.warn("Expected cave_api/cave_api directory not found, skipping API migration steps.")

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
            logger.warn(f"Failed to migrate code in {py_file}: {e}")

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

    # Collect existing api optional dependencies
    api_deps = []
    pyproject_path = os.path.join(app_dir, "pyproject.toml")
    if os.path.exists(pyproject_path):
        try:
            import tomllib
            with open(pyproject_path, "rb") as f:
                pyproject = tomllib.load(f)
            api_deps = pyproject.get("project", {}).get("optional-dependencies", {}).get("api", [])
        except Exception:
            pass

    current_v = get_app_version(app_dir)
    current_version = version_tuple(current_v)
    is_pre_3_6 = (
        (current_version and current_version < (3, 6, 0)) or
        (not current_version and os.path.exists(os.path.join(app_dir, "requirements.txt")))
    )
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

    if api_deps and os.path.exists(pyproject_path):
        try:
            with open(pyproject_path, "r") as f:
                content = f.read()

            deps_list_str = "\n".join(f'    "{dep}",' for dep in api_deps)

            if "[project.optional-dependencies]" in content:
                if re.search(r"api\s*=\s*\[", content):
                    content = re.sub(
                        r"(api\s*=\s*\[)[^\]]*(\])",
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
                content += (
                    f"\n[project.optional-dependencies]\napi = [\n{deps_list_str}\n]\n"
                )

            with open(pyproject_path, "w") as f:
                f.write(content)
            logger.info("Preserved 'api' optional dependencies in pyproject.toml")
        except Exception as e:
            logger.warn(f"Failed to preserve 'api' optional dependencies: {e}")

    target_version = version_tuple(target_v)
    if is_pre_3_6 and target_version and target_version >= (3, 6, 0):
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
