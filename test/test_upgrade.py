import os
import shutil
from pathlib import Path
from cave_cli.commands.upgrade import migrate_3_6_0


def test_migrate_3_6_0_renames_models_file(tmp_path):
    # Set up directory layout
    app_dir = tmp_path / "app"
    app_dir.mkdir()

    # Create cave_core directory and models.py
    cave_core_dir = app_dir / "cave_core"
    cave_core_dir.mkdir()
    models_file = cave_core_dir / "models.py"
    models_file.write_text("class MyModel:")

    # Create requirements.txt
    req_file = app_dir / "requirements.txt"
    req_file.write_text("numpy\npandas")

    # Create VERSION file to verify it gets removed
    version_file = app_dir / "VERSION"
    version_file.write_text("3.5.0")

    # Create root pyproject.toml
    pyproject_file = app_dir / "pyproject.toml"
    pyproject_file.write_text(
        "[project]\nname = 'myapp'\nversion = '1.0.0'\ndependencies = []\n"
    )

    # Create cave_api directory
    cave_api_dir = app_dir / "cave_api"
    cave_api_dir.mkdir()

    # Create cave_api/requirements.txt
    cave_api_req = cave_api_dir / "requirements.txt"
    cave_api_req.write_text("requests>=2.0.0\n# comment\npytest\n")

    # Create cave_api/pyproject.toml
    cave_api_pyproject = cave_api_dir / "pyproject.toml"
    cave_api_pyproject.write_text(
        "[project]\ndependencies = [\n  'pytest',\n  'django>=4.0'\n]\n"
    )

    # Run migration
    migrate_3_6_0(str(app_dir))

    # Assertions
    assert not models_file.exists()
    legacy_dir = app_dir / "legacy"
    assert (legacy_dir / "cave_core" / "models.py").exists()
    assert (
        legacy_dir / "cave_core" / "models.py"
    ).read_text() == "class MyModel:"
    assert not version_file.exists()
    assert not req_file.exists()
    assert (legacy_dir / "requirements.txt").exists()
    assert (legacy_dir / "requirements.txt").read_text() == "numpy\npandas"

    # Assert that pyproject.toml has merged api dependencies
    pyproject_content = pyproject_file.read_text()
    assert "[project.optional-dependencies]" in pyproject_content
    assert '"requests>=2.0.0"' in pyproject_content
    assert '"pytest"' in pyproject_content
    assert '"django>=4.0"' in pyproject_content
