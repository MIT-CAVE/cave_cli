import pytest
from cave_cli.utils.validate import validate_app_name


class TestValidateAppName:
    def test_valid_simple(self):
        assert validate_app_name("myapp") is None

    def test_valid_with_hyphen(self):
        assert validate_app_name("my-app") is None

    def test_valid_with_underscore(self):
        assert validate_app_name("my_app") is None

    def test_valid_with_numbers(self):
        assert validate_app_name("app123") is None

    def test_too_short(self):
        assert validate_app_name("a") is not None

    def test_uppercase_rejected(self):
        assert validate_app_name("MyApp") is not None

    def test_starts_with_hyphen(self):
        assert validate_app_name("-myapp") is not None

    def test_starts_with_underscore(self):
        assert validate_app_name("_myapp") is not None

    def test_ends_with_hyphen(self):
        assert validate_app_name("myapp-") is not None

    def test_ends_with_underscore(self):
        assert validate_app_name("myapp_") is not None

    def test_hyphen_followed_by_underscore(self):
        assert validate_app_name("my-_app") is not None

    def test_underscore_followed_by_hyphen(self):
        assert validate_app_name("my_-app") is not None

    def test_spaces_rejected(self):
        assert validate_app_name("my app") is not None

    def test_too_long(self):
        assert validate_app_name("a" * 256) is not None

    def test_max_valid_length(self):
        assert validate_app_name("a" * 255) is None
