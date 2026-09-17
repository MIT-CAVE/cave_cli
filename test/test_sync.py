import argparse
import os
import pytest

import cave_cli.utils.sync
from cave_cli.commands.sync_cmd import sync_cmd
from cave_cli.utils.sync import (
    can_create_symlinks,
    clean_patterns,
    matches_any,
    normalize_pattern,
    strip_quotes,
    sync_files,
)


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


class TestNormalizePattern:
    def test_leading_dotslash(self):
        assert normalize_pattern("./cave_api") == "cave_api"
        assert normalize_pattern("./cave_api/sub") == "cave_api/sub"

    def test_leading_slash(self):
        assert normalize_pattern("/cave_api") == "cave_api"

    def test_trailing_slash(self):
        assert normalize_pattern("cave_api/") == "cave_api"
        assert normalize_pattern("cave_api/sub/") == "cave_api/sub"

    def test_windows_backslashes(self):
        assert (
            normalize_pattern("cave_api\\sub\\file.txt")
            == "cave_api/sub/file.txt"
        )

    def test_wildcard_preserved(self):
        assert normalize_pattern("./cave_api/*") == "cave_api/*"
        assert normalize_pattern("tests/*.py") == "tests/*.py"


class TestCleanPatterns:
    def test_single_string_multiple_quoted_items(self):
        result = clean_patterns(["'.git' '.gitignore' 'README.md'"])
        assert result == [".git", ".gitignore", "README.md"]

    def test_single_string_double_quoted_items(self):
        result = clean_patterns(['".git" ".gitignore" "README.md"'])
        assert result == [".git", ".gitignore", "README.md"]

    def test_single_string_unquoted_items(self):
        result = clean_patterns([".git .gitignore README.md"])
        assert result == [".git", ".gitignore", "README.md"]

    def test_list_of_separate_items(self):
        result = clean_patterns([".git", ".gitignore", "README.md"])
        assert result == [".git", ".gitignore", "README.md"]

    def test_trailing_slashes_normalized(self):
        result = clean_patterns(["cave_api/", "tests/"])
        assert result == ["cave_api", "tests"]

    def test_quoted_spaces_in_filename(self):
        result = clean_patterns(["'file with space.txt' other.txt"])
        assert result == ["file with space.txt", "other.txt"]

    def test_empty_and_none(self):
        assert clean_patterns(None) == []
        assert clean_patterns([]) == []
        assert clean_patterns(["   "]) == []

    def test_deduplication(self):
        result = clean_patterns(["a", "a", "b", "'a'"])
        assert result == ["a", "b"]


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

    def test_windows_backslashes(self):
        assert matches_any("subdir\\file.py", "file.py", ["subdir/*.py"])

    def test_directory_prefix_matching(self):
        assert matches_any(
            "cave_api/docs/index.md", "index.md", ["cave_api/docs"]
        )
        assert matches_any(
            "cave_api/docs/sub/index.md", "index.md", ["cave_api/docs"]
        )
        assert not matches_any(
            "cave_api/other/index.md", "index.md", ["cave_api/docs"]
        )


class TestSyncFiles:
    def test_sync_files_exclude_single_string_quoted(self, tmp_path):
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()

        # Remote source files
        (src / ".git").mkdir()
        (src / ".git" / "config").write_text("remote git")
        (src / ".gitignore").write_text("remote gitignore")
        (src / "README.md").write_text("remote readme")
        (src / "manage.py").write_text("remote manage")
        (src / "cave_app").mkdir()
        (src / "cave_app" / "settings.py").write_text("remote settings")

        # Local destination files
        (dst / ".gitignore").write_text("local gitignore")
        (dst / "README.md").write_text("local readme")
        (dst / "manage.py").write_text("local manage")

        sync_files(
            str(src),
            str(dst),
            excludes=["'.git' '.gitignore' 'README.md'"],
        )

        assert (dst / ".gitignore").read_text() == "local gitignore"
        assert (dst / "README.md").read_text() == "local readme"
        assert (dst / "manage.py").read_text() == "remote manage"
        assert (
            dst / "cave_app" / "settings.py"
        ).read_text() == "remote settings"
        assert not (dst / ".git").exists()

    def test_sync_files_exclude_list_of_strings(self, tmp_path):
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()

        (src / ".gitignore").write_text("remote gitignore")
        (src / "README.md").write_text("remote readme")
        (src / "manage.py").write_text("remote manage")

        (dst / ".gitignore").write_text("local gitignore")
        (dst / "README.md").write_text("local readme")
        (dst / "manage.py").write_text("local manage")

        sync_files(
            str(src),
            str(dst),
            excludes=[".git", ".gitignore", "README.md"],
        )

        assert (dst / ".gitignore").read_text() == "local gitignore"
        assert (dst / "README.md").read_text() == "local readme"
        assert (dst / "manage.py").read_text() == "remote manage"

    def test_sync_files_exclude_trailing_slash_directory(self, tmp_path):
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()

        (src / "cave_api").mkdir()
        (src / "cave_api" / "server.py").write_text("remote server")
        (src / "manage.py").write_text("remote manage")

        (dst / "cave_api").mkdir()
        (dst / "cave_api" / "server.py").write_text("local server")
        (dst / "manage.py").write_text("local manage")

        sync_files(
            str(src),
            str(dst),
            excludes=["cave_api/"],
        )

        assert (dst / "cave_api" / "server.py").read_text() == "local server"
        assert (dst / "manage.py").read_text() == "remote manage"

    def test_sync_files_include_overrides_exclude(self, tmp_path):
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()

        (src / "cave_api").mkdir()
        (src / "cave_api" / "docs").mkdir()
        (src / "cave_api" / "docs" / "index.md").write_text("remote docs")
        (src / "cave_api" / "server.py").write_text("remote server")
        (src / "manage.py").write_text("remote manage")

        (dst / "cave_api").mkdir()
        (dst / "cave_api" / "docs").mkdir()
        (dst / "cave_api" / "docs" / "index.md").write_text("local docs")
        (dst / "cave_api" / "server.py").write_text("local server")
        (dst / "manage.py").write_text("local manage")

        sync_files(
            str(src),
            str(dst),
            includes=["cave_api/docs"],
            excludes=["cave_api/*"],
        )

        assert (
            dst / "cave_api" / "docs" / "index.md"
        ).read_text() == "remote docs"
        assert (dst / "cave_api" / "server.py").read_text() == "local server"
        assert (dst / "manage.py").read_text() == "remote manage"

    def test_sync_files_preserves_and_overwrites_symlinks(self, tmp_path):
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()

        # Create source structure:
        with open(src / "target.txt", "w") as f:
            f.write("target content")
        os.symlink("target.txt", src / "link.txt")
        with open(src / "file.txt", "w") as f:
            f.write("new file content")
        with open(src / "dir_to_file", "w") as f:
            f.write("new file content replacing directory")

        # Create destination structure:
        with open(dst / "link.txt", "w") as f:
            f.write("old regular file")
        with open(dst / "other.txt", "w") as f:
            f.write("other")
        os.symlink("other.txt", dst / "file.txt")
        (dst / "dir_to_file").mkdir()

        sync_files(str(src), str(dst))

        assert os.path.islink(dst / "link.txt")
        assert os.readlink(dst / "link.txt") == "target.txt"
        assert not os.path.islink(dst / "file.txt")
        assert (dst / "file.txt").read_text() == "new file content"
        assert not os.path.islink(dst / "dir_to_file")
        assert not os.path.isdir(dst / "dir_to_file")
        assert (
            dst / "dir_to_file"
        ).read_text() == "new file content replacing directory"

    def test_can_create_symlinks(self):
        res = can_create_symlinks()
        assert isinstance(res, bool)

    def test_sync_files_fallback_when_symlinks_unsupported(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(
            cave_cli.utils.sync, "can_create_symlinks", lambda: False
        )

        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()

        with open(src / "target.txt", "w") as f:
            f.write("target content")
        os.symlink("target.txt", src / "link.txt")

        sync_files(str(src), str(dst))

        assert not os.path.islink(dst / "link.txt")
        assert (dst / "link.txt").read_text() == "target content"


class TestSyncCmd:
    def test_sync_cmd_with_quoted_excludes(self, tmp_path, monkeypatch):
        app_dir = tmp_path / "app"
        app_dir.mkdir()
        (app_dir / ".gitignore").write_text("local gitignore")
        (app_dir / "README.md").write_text("local readme")
        (app_dir / "manage.py").write_text("local manage")

        def fake_clone(url: str, dest: str, branch: str | None = None) -> bool:
            os.makedirs(os.path.join(dest, ".git"), exist_ok=True)
            with open(os.path.join(dest, ".git", "config"), "w") as f:
                f.write("remote git")
            with open(os.path.join(dest, ".gitignore"), "w") as f:
                f.write("remote gitignore")
            with open(os.path.join(dest, "README.md"), "w") as f:
                f.write("remote readme")
            with open(os.path.join(dest, "manage.py"), "w") as f:
                f.write("remote manage")
            return True

        monkeypatch.setattr("cave_cli.commands.sync_cmd.clone", fake_clone)
        monkeypatch.setattr(
            "cave_cli.commands.sync_cmd.find_app_dir", lambda: str(app_dir)
        )

        args = argparse.Namespace(
            url="git@github.com:mit-cave/cave_app_aws",
            branch=None,
            include=None,
            exclude=["'.git' '.gitignore' 'README.md'"],
            yes=True,
            verbose=False,
            loglevel="INFO",
        )

        sync_cmd(args, do_reset=False)

        assert (app_dir / ".gitignore").read_text() == "local gitignore"
        assert (app_dir / "README.md").read_text() == "local readme"
        assert (app_dir / "manage.py").read_text() == "remote manage"
        assert not (app_dir / ".git").exists()
