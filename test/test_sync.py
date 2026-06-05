import pytest
from cave_cli.utils.sync import strip_quotes, matches_any


class TestStripQuotes:
    def test_single_quotes(self):
        assert strip_quotes("'hello'") == "hello"

    def test_double_quotes(self):
        assert strip_quotes('"hello"') == "hello"

    def test_no_quotes(self):
        assert strip_quotes("hello") == "hello"

    def test_mismatched_quotes(self):
        assert strip_quotes("'hello\"") == "'hello\""

    def test_strips_whitespace(self):
        assert strip_quotes("  'hello'  ") == "hello"

    def test_empty_quoted(self):
        assert strip_quotes("''") == ""


class TestMatchesAny:
    def test_name_wildcard(self):
        assert matches_any("subdir/file.py", "file.py", ["*.py"])

    def test_rel_path_match(self):
        assert matches_any("subdir/file.txt", "file.txt", ["subdir/*"])

    def test_no_match(self):
        assert not matches_any("file.txt", "file.txt", ["*.py"])

    def test_empty_patterns(self):
        assert not matches_any("file.txt", "file.txt", [])

    def test_git_directory(self):
        assert matches_any(".git", ".git", [".git"])

    def test_exact_rel_path(self):
        assert matches_any("docs/readme.md", "readme.md", ["docs/readme.md"])
