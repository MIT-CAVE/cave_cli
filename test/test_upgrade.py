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


def test_migrate_3_6_0_preserves_package_data_cave_api(tmp_path):
    app_dir = tmp_path / "app"
    app_dir.mkdir()

    # Create root pyproject.toml with package-data
    pyproject_file = app_dir / "pyproject.toml"
    pyproject_file.write_text(
        "[project]\n"
        "name = 'myapp'\n"
        "version = '1.0.0'\n"
        "dependencies = []\n\n"
        "[tool.setuptools.package-data]\n"
        'cave_api = ["**/*", "*"]\n'
    )

    # Create cave_api/pyproject.toml
    cave_api_dir = app_dir / "cave_api"
    cave_api_dir.mkdir()
    cave_api_pyproject = cave_api_dir / "pyproject.toml"
    cave_api_pyproject.write_text(
        "[project]\ndependencies = [\n  'pytest'\n]\n"
    )

    # Run migration
    migrate_3_6_0(str(app_dir))

    # Assertions
    pyproject_content = pyproject_file.read_text()
    assert "[tool.setuptools.package-data]" in pyproject_content
    assert 'cave_api = ["**/*", "*"]' in pyproject_content
    assert "[project.optional-dependencies]" in pyproject_content
    assert '"pytest"' in pyproject_content


def test_migrate_3_6_0_continues_across_substep_failures(tmp_path):
    app_dir = tmp_path / "app"
    app_dir.mkdir()

    # Create requirements.txt
    req_file = app_dir / "requirements.txt"
    req_file.write_text("numpy")

    # Create nested cave_api/cave_api structure
    cave_api_dir = app_dir / "cave_api" / "cave_api"
    cave_api_dir.mkdir(parents=True)
    init_py = cave_api_dir / "__init__.py"
    init_py.write_text("x = 1")

    # Run migration
    failures = migrate_3_6_0(str(app_dir))
    assert failures == []
    # Assert requirements moved to legacy
    assert (app_dir / "legacy" / "requirements.txt").exists()
    # Assert cave_api was promoted
    assert (app_dir / "cave_api" / "__init__.py").exists()


def test_migrate_3_6_0_handles_existing_legacy_destinations_and_missing_files(
    tmp_path,
):
    app_dir = tmp_path / "app"
    app_dir.mkdir()

    # Create an llm directory, and also pre-create legacy/llm to test overwrite without nesting
    (app_dir / "llm").mkdir()
    (app_dir / "llm" / "prompt.txt").write_text("hello")
    legacy_llm = app_dir / "legacy" / "llm"
    legacy_llm.mkdir(parents=True)
    (legacy_llm / "old_prompt.txt").write_text("old")

    # Missing requirements.txt, VERSION, utils/pyproject.toml, cave_core/models.py
    # They should not cause any error!
    failures = migrate_3_6_0(str(app_dir))
    assert failures == []
    assert (app_dir / "legacy" / "llm" / "prompt.txt").exists()
    assert not (app_dir / "legacy" / "llm" / "llm").exists()


def test_upgrade_forces_verbose_mode(tmp_path):
    from unittest.mock import patch, MagicMock
    import argparse
    import pytest
    from cave_cli.commands.upgrade import upgrade

    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "manage.py").write_text("")
    (app_dir / "cave_core").mkdir()
    (app_dir / ".env").write_text("DATABASE_IMAGE=postgres:latest\n")
    (app_dir / "pyproject.toml").write_text(
        "[project]\nname = 'myapp'\nversion = '3.6.0'\n"
    )

    args = argparse.Namespace(
        yes=True,
        verbose=False,
        loglevel="INFO",
        url="https://example.com/repo.git",
        version="v3.6.0",
        skip_env_upgrade=True,
    )

    with (
        patch(
            "cave_cli.commands.upgrade.get_app",
            return_value=(str(app_dir), "app"),
        ),
        patch(
            "cave_cli.commands.upgrade.sync_cmd", return_value=True
        ) as mock_sync,
        patch("cave_cli.commands.upgrade.reset", return_value=0),
        patch("cave_cli.commands.upgrade.run_cave", return_value=0),
        patch("cave_cli.commands.upgrade.confirm_action") as mock_confirm,
        patch("cave_cli.commands.upgrade.remove_licence_info"),
    ):
        upgrade(args)

    assert args.verbose is True
    assert args.loglevel == "DEBUG"
    # Verify sync_args includes cave_api/examples
    sync_call_args = mock_sync.call_args[0][0]
    assert "cave_api/examples" in sync_call_args.include
    assert "cave_api/docs" in sync_call_args.include
    # Verify confirm prompt mentions cave_api/examples
    confirm_msg = mock_confirm.call_args[0][0]
    assert "cave_api/examples/" in confirm_msg


def test_upgrade_reports_reset_failure_and_exits(tmp_path):
    from unittest.mock import patch
    import argparse
    import pytest
    from cave_cli.commands.upgrade import upgrade

    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "manage.py").write_text("")
    (app_dir / "cave_core").mkdir()
    (app_dir / ".env").write_text("DATABASE_IMAGE=postgres:latest\n")
    (app_dir / "pyproject.toml").write_text(
        "[project]\nname = 'myapp'\nversion = '3.6.0'\n"
    )

    args = argparse.Namespace(
        yes=True,
        verbose=False,
        loglevel="INFO",
        url="https://example.com/repo.git",
        version="v3.6.0",
        skip_env_upgrade=True,
    )

    with (
        patch(
            "cave_cli.commands.upgrade.get_app",
            return_value=(str(app_dir), "app"),
        ),
        patch("cave_cli.commands.upgrade.sync_cmd", return_value=True),
        patch("cave_cli.commands.upgrade.reset", return_value=1),
        patch(
            "cave_cli.commands.upgrade.run_cave", return_value=0
        ) as mock_run_cave,
        patch("cave_cli.commands.upgrade.remove_licence_info"),
    ):
        with pytest.raises(SystemExit) as exc_info:
            upgrade(args)
        assert exc_info.value.code == 1
        # When reset fails, API docs run_cave should be skipped
        mock_run_cave.assert_not_called()


def test_upgrade_allows_all_reformatting_even_when_sync_fails(tmp_path):
    from unittest.mock import patch
    import argparse
    import pytest
    from cave_cli.commands.upgrade import upgrade

    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "manage.py").write_text("")
    (app_dir / "cave_core").mkdir()
    (app_dir / ".env").write_text("DATABASE_IMAGE=postgres:latest\n")
    # Pre-3.6 structure
    (app_dir / "requirements.txt").write_text("numpy\n")
    cave_api_inner = app_dir / "cave_api" / "cave_api"
    cave_api_inner.mkdir(parents=True)
    (cave_api_inner / "__init__.py").write_text("print('hi')\n")

    args = argparse.Namespace(
        yes=True,
        verbose=False,
        loglevel="INFO",
        url="https://example.com/repo.git",
        version="v3.6.0",
        skip_env_upgrade=True,
    )

    with (
        patch(
            "cave_cli.commands.upgrade.get_app",
            return_value=(str(app_dir), "app"),
        ),
        patch("cave_cli.commands.upgrade.sync_cmd", return_value=False),
        patch("cave_cli.commands.upgrade.reset", return_value=0),
        patch("cave_cli.commands.upgrade.run_cave", return_value=0),
        patch("cave_cli.commands.upgrade.remove_licence_info") as mock_licence,
    ):
        with pytest.raises(SystemExit) as exc_info:
            upgrade(args)
        assert exc_info.value.code == 1
        # Even though sync failed, migration and licence cleanup were still attempted!
        assert (app_dir / "cave_api" / "__init__.py").exists()
        mock_licence.assert_called_once()


def test_upgrade_stubs_and_restores_api_py_during_reset(tmp_path):
    from unittest.mock import patch
    import argparse
    from cave_cli.commands.upgrade import upgrade

    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "manage.py").write_text("")
    (app_dir / "cave_core").mkdir()
    (app_dir / ".env").write_text("DATABASE_IMAGE=postgres:latest\n")
    (app_dir / "pyproject.toml").write_text(
        "[project]\nname = 'myapp'\nversion = '3.6.0'\n"
    )

    cave_api_dir = app_dir / "cave_api"
    cave_api_dir.mkdir()
    api_py = cave_api_dir / "api.py"
    api_py.write_text("MY_REAL_CODE = 42\n")
    init_py = cave_api_dir / "__init__.py"
    init_py.write_text("INIT_CODE = 100\n")

    api_content_during_reset = []
    init_content_during_reset = []

    def mock_reset_fn(args):
        api_content_during_reset.append(api_py.read_text())
        init_content_during_reset.append(init_py.read_text())
        return 0

    args = argparse.Namespace(
        yes=True,
        verbose=False,
        loglevel="INFO",
        url="https://example.com/repo.git",
        version="v3.6.0",
        skip_env_upgrade=True,
    )

    with (
        patch(
            "cave_cli.commands.upgrade.get_app",
            return_value=(str(app_dir), "app"),
        ),
        patch("cave_cli.commands.upgrade.sync_cmd", return_value=True),
        patch("cave_cli.commands.upgrade.reset", side_effect=mock_reset_fn),
        patch("cave_cli.commands.upgrade.run_cave", return_value=0),
        patch("cave_cli.commands.upgrade.remove_licence_info"),
    ):
        upgrade(args)

    # During reset, api.py should have been a stub with execute_command, and __init__.py empty
    assert len(api_content_during_reset) == 1
    assert "def execute_command" in api_content_during_reset[0]
    assert init_content_during_reset[0] == ""

    # After upgrade completes, original content should be fully restored!
    assert api_py.read_text() == "MY_REAL_CODE = 42\n"
    assert init_py.read_text() == "INIT_CODE = 100\n"


def test_migrate_3_6_0_recovery_from_legacy_inner(tmp_path):
    app_dir = tmp_path / "app"
    app_dir.mkdir()

    # Suppose cave_api was previously moved to legacy/cave_api, but top-level cave_api has no api.py
    legacy_inner = app_dir / "legacy" / "cave_api" / "cave_api"
    legacy_inner.mkdir(parents=True)
    (legacy_inner / "api.py").write_text("def execute_command(): pass\n")
    (legacy_inner / "__init__.py").write_text("")

    failures = migrate_3_6_0(str(app_dir))
    assert failures == []
    # Assert cave_api has now been promoted from legacy_inner
    assert (app_dir / "cave_api" / "api.py").exists()
    assert (
        app_dir / "cave_api" / "api.py"
    ).read_text() == "def execute_command(): pass\n"
