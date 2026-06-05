import pytest
from cave_cli.utils.env import parse_env, set_env_value, validate_env, generate_password


class TestParseEnv:
    def test_basic_key_value(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text("KEY=value\n")
        assert parse_env(str(f)) == {"KEY": "value"}

    def test_single_quoted_value(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text("KEY='value'\n")
        assert parse_env(str(f)) == {"KEY": "value"}

    def test_double_quoted_value(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text('KEY="value"\n')
        assert parse_env(str(f)) == {"KEY": "value"}

    def test_ignores_comments(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text("# comment\nKEY=value\n")
        assert parse_env(str(f)) == {"KEY": "value"}

    def test_ignores_blank_lines(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text("\nKEY=value\n\n")
        assert parse_env(str(f)) == {"KEY": "value"}

    def test_multiple_vars(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text("A=1\nB=2\n")
        assert parse_env(str(f)) == {"A": "1", "B": "2"}

    def test_missing_file(self, tmp_path):
        assert parse_env(str(tmp_path / "missing.env")) == {}

    def test_value_with_equals(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text("KEY=a=b\n")
        assert parse_env(str(f)) == {"KEY": "a=b"}


class TestSetEnvValue:
    def test_replaces_existing_key(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text("KEY=old\n")
        set_env_value(str(f), "KEY", "new")
        assert parse_env(str(f)) == {"KEY": "new"}

    def test_appends_new_key(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text("OTHER=val\n")
        set_env_value(str(f), "KEY", "added")
        result = parse_env(str(f))
        assert result["KEY"] == "added"
        assert result["OTHER"] == "val"

    def test_value_stored_single_quoted(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text("")
        set_env_value(str(f), "KEY", "myvalue")
        assert "KEY='myvalue'" in f.read_text()


class TestValidateEnv:
    def test_valid_env(self, tmp_path):
        f = tmp_path / ".env"
        lines = [
            f"{var}=x\n"
            for var in (
                "DATABASE_IMAGE",
                "DATABASE_PASSWORD",
                "DJANGO_ADMIN_EMAIL",
                "DJANGO_ADMIN_FIRST_NAME",
                "DJANGO_ADMIN_LAST_NAME",
                "DJANGO_ADMIN_PASSWORD",
                "DJANGO_ADMIN_USERNAME",
                "SECRET_KEY",
                "STATIC_APP_URL",
                "STATIC_APP_URL_PATH",
            )
        ]
        f.write_text("".join(lines))
        assert validate_env(str(f)) == []

    def test_missing_variable(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text("SECRET_KEY=x\n")
        errors = validate_env(str(f))
        assert any("DATABASE_IMAGE" in e for e in errors)

    def test_retired_variable_flagged(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text("DATABASE_HOST=x\n")
        errors = validate_env(str(f))
        assert any("DATABASE_HOST" in e for e in errors)


class TestGeneratePassword:
    def test_default_length(self):
        assert len(generate_password()) == 16

    def test_custom_length(self):
        assert len(generate_password(24)) == 24

    def test_alphanumeric_only(self):
        pw = generate_password(100)
        assert pw.isalnum()

    def test_randomness(self):
        assert generate_password() != generate_password()
