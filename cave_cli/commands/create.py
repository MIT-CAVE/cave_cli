import argparse
import os
import shutil
import stat
import sys
from pathlib import Path

from cave_cli.commands.reset import reset
from cave_cli.commands.run import run_cave
from cave_cli.utils.constants import HTTPS_URL
from cave_cli.utils.docker import build_image, check_docker, generate_secret_key
from cave_cli.utils.env import create_env_interactive
from cave_cli.utils.git import add, branch_rename, clone, commit, init
from cave_cli.utils.logger import logger
from cave_cli.utils.validate import validate_app_name


def create(args: argparse.Namespace) -> None:
    """
    Usage:

    - Creates a new CAVE app from the template repository
    """
    app_name = args.name
    error = validate_app_name(app_name)
    if error:
        logger.error(error)
        sys.exit(1)

    if os.path.isdir(app_name):
        logger.error(
            f"Cannot create app '{app_name}': "
            "This folder already exists in the current directory"
        )
        sys.exit(1)

    clone_url = getattr(args, "url", None) or HTTPS_URL
    version = getattr(args, "version", None)

    logger.header("App Creation:")
    logger.info("Downloading the app template...")

    success = clone(clone_url, app_name, branch=version)
    if not success or not os.path.isdir(app_name):
        logger.error("Clone failed. Ensure you used a valid version.")
        logger.error(
            f"The version must be a tag (or branch) listed at {clone_url}."
        )
        sys.exit(1)

    logger.info("Done")

    app_dir = os.path.abspath(app_name)
    remove_licence_info(app_dir)

    Path(os.path.join(app_dir, ".env")).touch()

    example_env = os.path.join(app_dir, "example.env")
    env_path = os.path.join(app_dir, ".env")

    build_image(app_name, app_dir)
    secret_key = generate_secret_key(app_name)

    create_env_interactive(
        app_name=app_name,
        env_path=env_path,
        template_path=example_env,
        docker_secret_key=secret_key,
    )

    reset_args = argparse.Namespace(
        yes=True,
        verbose=getattr(args, "verbose", False),
        loglevel=getattr(args, "loglevel", "INFO"),
    )
    reset(reset_args, app_dir=app_dir, app_name=app_name)

    logger.header("Version Control:")
    logger.info("Configuring git repository...")
    git_dir = os.path.join(app_dir, ".git")
    if os.path.isdir(git_dir):
        rmtree_force(git_dir)
    init(app_dir)

    gitignore_path = os.path.join(app_dir, ".gitignore")
    if os.path.isfile(gitignore_path):
        content = Path(gitignore_path).read_text()
        content = content.replace(".env", "")
        Path(gitignore_path).write_text(content)

    if os.path.isfile(gitignore_path):
        content = Path(gitignore_path).read_text()
        if "media" not in content:
            content += "\n# Media\nmedia\n"
            Path(gitignore_path).write_text(content)

    add(app_dir)
    commit(app_dir, "Initialize CAVE App")
    branch_rename(app_dir, "main")
    logger.info("Done.")

    logger.info("Generating LLM Docs...")
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
    logger.info("Done.")

    logger.header("App Creation Status:")
    logger.info(f"App '{app_name}' created successfully!")
    logger.info(
        f"Created variables and additional configuration options "
        f"are available in {app_name}/.env"
    )


def force_remove(func, path, exc):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def rmtree_force(path: str) -> None:
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=force_remove)
    else:
        shutil.rmtree(path, onerror=force_remove)


def remove_licence_info(app_dir: str) -> None:
    license_path = os.path.join(app_dir, "LICENSE")
    if os.path.isfile(license_path):
        os.remove(license_path)

    readme_path = os.path.join(app_dir, "README.md")
    if os.path.isfile(readme_path):
        lines = Path(readme_path).read_text().splitlines()
        for i, line in enumerate(lines):
            if line.strip() == "## License Notice":
                lines = lines[:i]
                break
        Path(readme_path).write_text("\n".join(lines) + "\n")

    notice_path = os.path.join(app_dir, "NOTICE.md")
    if os.path.isfile(notice_path):
        lines = Path(notice_path).read_text().splitlines()
        for i, line in enumerate(lines):
            if line.startswith("Licensed under"):
                lines = lines[:i]
                break
        Path(notice_path).write_text("\n".join(lines) + "\n")

    setup_path = os.path.join(app_dir, "cave_api", "setup.py")
    if os.path.isfile(setup_path):
        content = Path(setup_path).read_text()
        import re

        content = re.sub(r'^\s*license="MIT",\s*\n', "", content, flags=re.M)
        content = re.sub(
            r'^\s*"License.*MIT License",\s*\n', "", content, flags=re.M
        )
        Path(setup_path).write_text(content)
