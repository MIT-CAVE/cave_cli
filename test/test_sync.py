import pytest
from cave_cli.utils.sync import strip_quotes, matches_any, sync_files


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


class TestSyncFiles:
    def test_sync_files_preserves_and_overwrites_symlinks(self, tmp_path):
        import os

        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()

        # Create source structure:
        # target.txt (file)
        # link.txt (symlink -> target.txt)
        # file.txt (file)
        # dir_to_file (file)
        with open(src / "target.txt", "w") as f:
            f.write("target content")
        os.symlink("target.txt", src / "link.txt")
        with open(src / "file.txt", "w") as f:
            f.write("new file content")
        with open(src / "dir_to_file", "w") as f:
            f.write("new file content replacing directory")

        # Create destination structure:
        # link.txt (regular file)
        # file.txt (symlink -> other)
        # dir_to_file (directory)
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
        from cave_cli.utils.sync import can_create_symlinks

        res = can_create_symlinks()
        assert isinstance(res, bool)

    def test_sync_files_fallback_when_symlinks_unsupported(
        self, tmp_path, monkeypatch
    ):
        import os
        import cave_cli.utils.sync
        from cave_cli.utils.sync import sync_files

        monkeypatch.setattr(
            cave_cli.utils.sync, "can_create_symlinks", lambda: False
        )

        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()

        # Create source structure:
        # target.txt (file)
        # link.txt (symlink -> target.txt)
        with open(src / "target.txt", "w") as f:
            f.write("target content")
        os.symlink("target.txt", src / "link.txt")

        sync_files(str(src), str(dst))

        # Because symlinks are unsupported, dst/link.txt should be created as a regular file with the content of target.txt.
        assert not os.path.islink(dst / "link.txt")
        assert (dst / "link.txt").read_text() == "target content"
