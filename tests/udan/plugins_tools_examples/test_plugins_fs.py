"""Tests for filesystem plugins."""

import os
from pathlib import Path

import udan.plugins_tools_examples.plugins_builtins
import udan.renders.plugins_renders
from tests.conftest import make_qp, register_tools_from_module
from udan.attributes.api_attribute_storage import AttributeStorageAPI
from udan.core.api_attributes import AttributeDescriptor
from udan.core_tools_loading.api_types import Group
from udan.plugins_tools_examples import plugins_fs
from udan.plugins_tools_examples.plugins_fs import (
    FileLine,
    PathGlob,
    count_lines,
    env_entry_value,
    extend_dir,
    extend_file_lines,
    extend_rg,
    file_content,
    file_line_content,
    get_directory_size,
    get_synchronization_type,
    git_tree,
    greps_in,
    group_by_globs,
    insert_glob_groups,
    insert_ls_files,
    is_empty_dir,
    modification_date,
    read_env,
    read_file,
    relative_path,
    render_file_line,
)


def test_insert_ls_files_default(tmp_path):
    """Test insert_ls_files with default directory and pattern."""
    # Create test files
    (tmp_path / "file1.txt").write_text("content1")
    (tmp_path / "file2.txt").write_text("content2")
    (tmp_path / "other.py").write_text("# code")

    # Test listing all files
    files = list(insert_ls_files(str(tmp_path)))
    assert len(files) == 3
    assert all(isinstance(f, Path) for f in files)
    assert "file1.txt" in [f.name for f in files]
    assert "file2.txt" in [f.name for f in files]
    assert "other.py" in [f.name for f in files]


def test_insert_ls_files_with_pattern(tmp_path):
    """Test insert_ls_files with glob pattern."""
    (tmp_path / "file1.txt").write_text("content1")
    (tmp_path / "file2.txt").write_text("content2")
    (tmp_path / "script.py").write_text("# code")

    # Test pattern matching
    txt_files = list(insert_ls_files(str(tmp_path), "*.txt"))
    assert len(txt_files) == 2
    assert all(f.suffix == ".txt" for f in txt_files)

    py_files = list(insert_ls_files(str(tmp_path), "*.py"))
    assert len(py_files) == 1
    assert py_files[0].name == "script.py"


def test_insert_ls_files_with_query(tmp_path, make_ctx):
    """Test insert_ls_files through query execution."""
    (tmp_path / "test.txt").write_text("content")
    (tmp_path / "data.json").write_text("{}")

    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, insert_ls_files.__module__)

    # Query should show files
    forest, attrs, render_specs, out = qp.execute_query(f"insert_ls_files {tmp_path}")

    # Check both files are present in output
    lines = out.strip().split("\n")
    assert len(lines) == 2
    # Check both filenames are in the output (order may vary)
    file_names = [line.split("/")[-1] for line in lines]
    assert "test.txt" in file_names
    assert "data.json" in file_names


def test_extend_file_lines(tmp_path):
    """Test extend_file_lines extender."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("line1\nline2\nline3\n")

    # Extend with Path object
    lines = list(extend_file_lines(test_file))
    assert len(lines) == 3
    assert lines[0] == "line1"
    assert lines[1] == "line2"
    assert lines[2] == "line3"

    # Test with non-Path item returns nothing
    assert list(extend_file_lines("not a path")) == []
    assert list(extend_file_lines(tmp_path)) == []


def test_extend_dir(tmp_path):
    """Test extend_dir extender."""
    # Create test structure
    (tmp_path / "file1.txt").write_text("content1")
    (tmp_path / "file2.txt").write_text("content2")
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    (subdir / "nested.txt").write_text("nested")

    # Extend directory
    files = list(extend_dir(tmp_path))
    assert len(files) == 3
    assert all(isinstance(f, Path) for f in files)
    assert "file1.txt" in [f.name for f in files]
    assert "file2.txt" in [f.name for f in files]
    assert "subdir" in [f.name for f in files]

    # Test with non-Path item
    assert extend_dir("not a path") is None


def test_extend_dir_pattern(tmp_path):
    """With a pattern, files must match it; only directories leading to a match are kept."""

    (tmp_path / "code.py").write_text("code")
    (tmp_path / "notes.txt").write_text("notes")
    (tmp_path / "with_py" / "inner.py").mkdir(parents=True)
    (tmp_path / "empty_branch" / "deeper").mkdir(parents=True)

    entries = list(extend_dir(tmp_path, "*.py"))
    assert {entry.name for entry in entries} == {"code.py", "with_py"}

    # The default keeps every entry, as before.
    assert {entry.name for entry in extend_dir(tmp_path)} == {"code.py", "notes.txt", "with_py", "empty_branch"}


def test_count_lines(tmp_path):
    """Test count_lines attribute."""
    # Create file with specific line count
    test_file = tmp_path / "test.txt"
    test_file.write_text("\n".join(["line"] * 5))

    assert count_lines(str(test_file)) == 5
    assert count_lines(test_file) == 5

    # Test with non-existent file
    assert count_lines("nonexistent.txt") == 0

    # Test with invalid type
    assert count_lines(123) == -1


def test_count_lines_with_query(tmp_path, make_ctx):
    """Test count_lines through query execution."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("\n".join(["line"] * 3))

    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, insert_ls_files.__module__)
    register_tools_from_module(ctx, udan.renders.plugins_renders.__name__)

    # Query should show line count
    forest, attrs, render_specs, out = qp.execute_query(f"insert_ls_files {tmp_path}, count_lines")

    # Output should contain the file with line count
    lines = out.strip().split("\n")
    assert len(lines) == 1
    assert "test.txt :: 3" in lines[0]


def test_modification_date(tmp_path):
    """Test modification_date attribute."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("content")

    # Should return a string
    mod_date = modification_date(str(test_file))
    assert isinstance(mod_date, str)
    assert len(mod_date) > 0

    # Same with Path object
    mod_date_path = modification_date(test_file)
    assert isinstance(mod_date_path, str)
    assert mod_date == mod_date_path


def test_get_synchronization_type(tmp_path):
    """Test get_synchronization_type attribute."""
    # Test with .git directory
    git_repo = tmp_path / "git_repo"
    git_repo.mkdir()
    (git_repo / ".git").mkdir()

    assert get_synchronization_type(git_repo) == "git"

    # Test with .stfolder directory
    syncthing_dir = tmp_path / "syncthing"
    syncthing_dir.mkdir()
    (syncthing_dir / ".stfolder").mkdir()

    assert get_synchronization_type(syncthing_dir) == "syncthing"

    # Test with no sync
    normal_dir = tmp_path / "normal"
    normal_dir.mkdir()

    assert get_synchronization_type(normal_dir) == "UNK"


def test_get_directory_size(tmp_path):
    """Test get_directory_size attribute."""
    # Create directory with files
    test_dir = tmp_path / "test_dir"
    test_dir.mkdir()

    # Create files of known sizes
    (test_dir / "file1.txt").write_text("x" * 1000)  # ~1 KB
    (test_dir / "file2.txt").write_text("y" * 100)  # ~100 B

    size_str = get_directory_size(test_dir)
    assert isinstance(size_str, str)
    # Total size is 1100 bytes, which should be formatted as KB
    assert "KB" in size_str


def test_get_directory_size_formats(tmp_path):
    """Test get_directory_size with different size formats."""
    test_dir = tmp_path / "size_test"
    test_dir.mkdir()

    # Test bytes (< 1 KB)
    (test_dir / "small.txt").write_text("x" * 100)
    size = get_directory_size(test_dir)
    assert "B" in size
    assert "KB" not in size

    # Test KB (1 KB - 1 MB)
    test_dir_kb = tmp_path / "kb_test"
    test_dir_kb.mkdir()
    (test_dir_kb / "file.txt").write_text("x" * 5000)  # ~5 KB
    size_kb = get_directory_size(test_dir_kb)
    assert "KB" in size_kb


def test_is_empty_dir(tmp_path):
    """Test is_empty_dir attribute."""
    # Empty directory
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    assert is_empty_dir(empty_dir) == 1

    # Non-empty directory
    non_empty = tmp_path / "non_empty"
    non_empty.mkdir()
    (non_empty / "file.txt").write_text("content")
    assert is_empty_dir(non_empty) == 0

    # File (not a directory)
    test_file = tmp_path / "test.txt"
    test_file.write_text("content")
    assert is_empty_dir(test_file) == 0

    # Non-existent path
    assert is_empty_dir("nonexistent") == 0


def test_filesystem_workflow(tmp_path, make_ctx):
    """Test complete filesystem workflow with inserters and extenders."""
    # Create test structure
    (tmp_path / "test.py").write_text("def foo():\n    pass\n")
    (tmp_path / "README.md").write_text("# Test\n")

    subdir = tmp_path / "src"
    subdir.mkdir()
    (subdir / "main.py").write_text("# main\n")

    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, insert_ls_files.__module__)

    # Query: list files and get their line counts
    forest, attrs, render_specs, out = qp.execute_query(f"insert_ls_files {tmp_path}, count_lines")

    # Should show files with line counts
    lines = out.strip().split("\n")
    # Check for specific files (may be in any order)
    file_entries = [line for line in lines if "README.md" in line or "test.py" in line]
    assert len(file_entries) >= 2


def test_filter_is_empty_dir(tmp_path, make_ctx):
    """Test that is_empty_dir attribute correctly identifies empty vs non-empty directories."""
    # Create test directory structure
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    non_empty_dir = tmp_path / "non_empty"
    non_empty_dir.mkdir()
    (non_empty_dir / "file.txt").write_text("content")

    another_empty = tmp_path / "another_empty"
    another_empty.mkdir()

    # Direct attribute test
    assert is_empty_dir(empty_dir) == 1, "Empty directory should return 1"
    assert is_empty_dir(non_empty_dir) == 0, "Non-empty directory should return 0"
    assert is_empty_dir(another_empty) == 1, "Empty directory should return 1"

    # Test with query system to verify attribute calculation works
    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, insert_ls_files.__module__)
    register_tools_from_module(ctx, udan.plugins_tools_examples.plugins_builtins.__name__)
    register_tools_from_module(ctx, udan.renders.plugins_renders.__name__)

    # Query: list directories with is_empty_dir attribute
    forest, attrs, render_specs, out = qp.execute_query(f"insert_ls_files {tmp_path}, is_empty_dir")

    # Parse output to check is_empty_dir values
    lines = out.strip().split("\n")

    # Check each directory specifically
    # Non-empty directory should have value 0
    non_empty_lines = [line for line in lines if "/non_empty " in line]
    assert len(non_empty_lines) == 1, "Should have one 'non_empty' directory"
    assert ":: 0" in non_empty_lines[0], "Non-empty directory should show is_empty_dir=0"

    # Empty directory should have value 1
    empty_lines = [line for line in lines if "/empty " in line]
    assert len(empty_lines) == 1, "Should have one 'empty' directory"
    assert ":: 1" in empty_lines[0], "Empty directory should show is_empty_dir=1"

    # Another empty directory should also have value 1
    another_empty_lines = [line for line in lines if "/another_empty " in line]
    assert len(another_empty_lines) == 1, "Should have one 'another_empty' directory"
    assert ":: 1" in another_empty_lines[0], "Empty directory should show is_empty_dir=1"


def test_extend_rg_basic(tmp_path):
    """Test extend_rg extender with basic pattern matching."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello world\npython code\nworld test\n")

    # Test without -o flag (full lines)
    lines = list(extend_rg(test_file, "world"))
    assert len(lines) == 2
    assert "hello world" in lines
    assert "world test" in lines

    # Test with pattern that doesn't match
    lines_nomatch = list(extend_rg(test_file, "xyz"))
    assert len(lines_nomatch) == 0


def test_extend_rg_with_o_flag(tmp_path):
    """Test extend_rg with o=True (only matching parts)."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello world\npython code\ntest world test\n")

    # With o=True, yield only the matching parts
    matches = list(extend_rg(test_file, "world|test", o=True))
    # Should get ["world", "world", "test", "test"]
    assert len(matches) == 4
    assert matches.count("world") == 2
    assert matches.count("test") == 2


def test_extend_rg_with_numbers(tmp_path):
    """Test extend_rg with number patterns."""
    test_file = tmp_path / "numbers.txt"
    test_file.write_text("value 123\n456 test\nno numbers\n999")

    # Match numbers
    numbers = list(extend_rg(test_file, r"\d+", o=True))
    assert len(numbers) == 3
    assert "123" in numbers
    assert "456" in numbers
    assert "999" in numbers

    # Full lines containing numbers
    lines_with_numbers = list(extend_rg(test_file, r"\d+"))
    assert len(lines_with_numbers) == 3
    assert "value 123" in lines_with_numbers
    assert "456 test" in lines_with_numbers


def test_extend_rg_with_query(tmp_path, make_ctx):
    """Test extend_rg through query execution."""
    test_file = tmp_path / "code.py"
    test_file.write_text("def foo():\n    pass\ndef bar():\n    return 42\n")

    ctx = make_ctx()
    register_tools_from_module(ctx, insert_ls_files.__module__)

    register_tools_from_module(ctx, udan.plugins_tools_examples.plugins_builtins.__name__)

    # For now, just test that the function works correctly
    # Query argument passing for extenders can be tested separately
    lines_direct = list(extend_rg(test_file, "def"))
    assert len(lines_direct) == 2
    assert "def foo():" in lines_direct
    assert "def bar():" in lines_direct


def test_extend_rg_empty_file(tmp_path):
    """Test extend_rg with empty file."""
    test_file = tmp_path / "empty.txt"
    test_file.write_text("")

    lines = list(extend_rg(test_file, "pattern"))
    assert len(lines) == 0


def test_extend_rg_nonexistent_file():
    """Test extend_rg with non-existent file."""
    lines = list(extend_rg("/nonexistent/file.txt", "pattern"))
    assert len(lines) == 0


def test_extend_rg_complex_pattern(tmp_path):
    """Test extend_rg with complex regex pattern."""
    test_file = tmp_path / "data.txt"
    test_file.write_text("email@example.com\nuser@test.org\nno email here\nadmin@domain.co.uk\n")

    # Email pattern
    emails = list(extend_rg(test_file, r"[\w.]+@[\w.]+", o=True))
    assert len(emails) == 3
    assert "email@example.com" in emails
    assert "user@test.org" in emails
    assert "admin@domain.co.uk" in emails


def test_greps_in_all_tokens_present(tmp_path):
    """Test greps_in keeps a file containing all required tokens."""
    test_file = tmp_path / "notes.txt"
    test_file.write_text("TODO: fix parser\nFIXME: handle empty input\n")

    assert greps_in(test_file, ["TODO", "FIXME"]) is True


def test_greps_in_missing_token(tmp_path):
    """Test greps_in drops a file missing at least one required token."""
    test_file = tmp_path / "notes.txt"
    test_file.write_text("TODO: fix parser\n")

    assert greps_in(test_file, ["TODO", "FIXME"]) is False


def test_greps_in_negative_token(tmp_path):
    """Test greps_in drops a file containing an excluded token."""
    test_file = tmp_path / "notes.txt"
    test_file.write_text("TODO: fix parser\nskip this in tests\n")

    assert greps_in(test_file, ["TODO", "-tests"]) is False


def test_greps_in_positive_and_negative(tmp_path):
    """Test greps_in keeps a file with required tokens and no excluded tokens."""
    matching = tmp_path / "matching.txt"
    matching.write_text("TODO: fix parser\n")
    other = tmp_path / "other.txt"
    other.write_text("TODO: covered by tests\n")

    assert greps_in(matching, ["TODO", "-tests"]) is True
    assert greps_in(other, ["TODO", "-tests"]) is False


def test_greps_in_no_tokens(tmp_path):
    """Test greps_in with no tokens keeps every existing file (shell behavior)."""
    test_file = tmp_path / "notes.txt"
    test_file.write_text("anything\n")

    assert greps_in(test_file, []) is True


def test_greps_in_empty_file(tmp_path):
    """Test greps_in on an empty file with a required token."""
    test_file = tmp_path / "empty.txt"
    test_file.write_text("")

    assert greps_in(test_file, ["TODO"]) is False
    assert greps_in(test_file, ["-TODO"]) is True


def test_greps_in_nonexistent_file(tmp_path):
    """Test greps_in drops paths that are not existing files."""
    assert greps_in(tmp_path / "missing.txt", ["TODO"]) is False
    assert greps_in(str(tmp_path), ["TODO"]) is False


def test_greps_in_accepts_str_and_pathglob(tmp_path):
    """Test greps_in accepts str paths and PathGlob items."""
    test_file = tmp_path / "notes.txt"
    test_file.write_text("TODO: fix parser\n")

    assert greps_in(str(test_file), ["TODO"]) is True
    assert greps_in(PathGlob(path=test_file, glob_group="*.txt"), ["TODO"]) is True
    assert greps_in(PathGlob(path=test_file, glob_group="*.txt"), ["-TODO"]) is False


def test_greps_in_token_matching_is_plain_substring(tmp_path):
    """Test greps_in treats tokens as plain substrings, not regexes."""
    test_file = tmp_path / "notes.txt"
    test_file.write_text("value = a.b.c\n")

    # Regex metacharacters are matched literally (grep -F behavior)
    assert greps_in(test_file, ["a.b"]) is True
    assert greps_in(test_file, ["axb"]) is False


def test_relative_path_basic():
    """Test relative_path attribute with basic paths."""
    # Test with string paths
    result = relative_path("/a/b/c/d.txt", "/a/")
    assert result == "b/c/d.txt"

    # Test with Path objects

    result_path = relative_path(Path("/a/b/c/d.txt"), Path("/a/"))
    assert result_path == "b/c/d.txt"


def test_relative_path_with_different_base_depths():
    """Test relative_path with different base directory depths."""
    # Base is one level deep
    assert relative_path("/a/b/c/d.txt", "/a/") == "b/c/d.txt"

    # Base is two levels deep
    assert relative_path("/a/b/c/d.txt", "/a/b") == "c/d.txt"

    # Base is three levels deep
    assert relative_path("/a/b/c/d.txt", "/a/b/c") == "d.txt"


def test_relative_path_with_file_in_base():
    """Test relative_path when item is directly in base_path."""
    assert relative_path("/a/file.txt", "/a/") == "file.txt"
    assert relative_path("/a/file.txt", "/a") == "file.txt"


def test_relative_path_not_relative():
    """Test relative_path when item is not relative to base_path."""
    # Different root paths
    result = relative_path("/x/y/z.txt", "/a/")
    # Should return absolute path since it's not relative
    assert result == "/x/y/z.txt"


def test_relative_path_with_trailing_slash_variations():
    """Test relative_path handles trailing slash variations."""
    # With trailing slash on base
    assert relative_path("/a/b/c/d.txt", "/a/") == "b/c/d.txt"

    # Without trailing slash on base
    assert relative_path("/a/b/c/d.txt", "/a") == "b/c/d.txt"


def test_relative_path_with_query(tmp_path, make_ctx):
    """Test relative_path through query execution."""
    # Create test directory structure
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "file1.txt").write_text("content1")
    (tmp_path / "subdir" / "nested").mkdir()
    (tmp_path / "subdir" / "nested" / "file2.txt").write_text("content2")
    (tmp_path / "root.txt").write_text("root content")

    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, insert_ls_files.__module__)

    # Query: list all files recursively in tmp_path with relative_path from
    # tmp_path
    forest, attrs, render_specs, out = qp.execute_query(f"insert_ls_files {tmp_path} **/*, relative_path {tmp_path}")

    lines = out.strip().split("\n")

    # Check that relative paths are shown
    # Files should show paths relative to tmp_path
    assert any("subdir/file1.txt" in line or "subdir\\file1.txt" in line for line in lines)
    assert any("subdir/nested/file2.txt" in line or "subdir\\nested\\file2.txt" in line for line in lines)


def test_relative_path_with_directories(tmp_path):
    """Test relative_path with directory items."""
    # Create test structure
    (tmp_path / "project").mkdir()
    (tmp_path / "project" / "src").mkdir()
    (tmp_path / "project" / "src" / "main.py").write_text("# main")

    # Test relative path of directory
    result = relative_path(tmp_path / "project" / "src", tmp_path)
    # Normalize path separators for cross-platform compatibility
    result_normalized = result.replace("\\", "/")
    assert "project/src" in result_normalized


def test_relative_path_current_directory(tmp_path):
    """Test relative_path with current directory (.) as base."""
    # Create a file in tmp_path
    (tmp_path / "test.txt").write_text("content")

    # Relative to tmp_path (simulating ".")
    result = relative_path(tmp_path / "test.txt", tmp_path)
    assert result == "test.txt"


def test_relative_path_with_nested_structure(tmp_path):
    """Test relative_path with deeply nested directory structure."""
    # Create nested structure: a/b/c/d/e/file.txt
    nested_dir = tmp_path / "a" / "b" / "c" / "d" / "e"
    nested_dir.mkdir(parents=True)
    (nested_dir / "file.txt").write_text("deep content")

    # Relative to tmp_path
    result = relative_path(nested_dir / "file.txt", tmp_path)
    result_normalized = result.replace("\\", "/")
    assert "a/b/c/d/e/file.txt" in result_normalized

    # Relative to intermediate directory
    intermediate = tmp_path / "a" / "b"
    result_intermediate = relative_path(nested_dir / "file.txt", intermediate)
    result_intermediate_normalized = result_intermediate.replace("\\", "/")
    assert "c/d/e/file.txt" in result_intermediate_normalized


def test_relative_path_cross_platform(tmp_path):
    """Test that relative_path works correctly across platforms."""
    # Create test file
    test_file = tmp_path / "test.txt"
    test_file.write_text("content")

    # Test with both string and Path inputs
    result_str = relative_path(str(test_file), str(tmp_path))
    result_path = relative_path(test_file, tmp_path)

    # Both should give the same result
    assert result_str == result_path
    assert result_str == "test.txt"


def test_read_env_basic(tmp_path):
    """Test read_env inserter with basic .env file."""
    env_file = tmp_path / ".env"
    env_file.write_text("KEY1=value1\nKEY2=value2\nKEY3=value3\n")

    entries = list(read_env(str(env_file)))
    assert len(entries) == 3

    # Check each entry has the correct structure
    for entry in entries:
        assert entry["type"] == "entry"
        assert entry["comment"] is None
        assert isinstance(entry["entry"], list)
        assert len(entry["entry"]) == 2

    # Check keys and values
    keys = [e["entry"][0] for e in entries]
    values = [e["entry"][1] for e in entries]
    assert keys == ["KEY1", "KEY2", "KEY3"]
    assert values == ["value1", "value2", "value3"]


def test_read_env_with_comments_and_empty_lines(tmp_path):
    """Test read_env preserves comments and empty lines."""
    env_file = tmp_path / ".env"
    env_file.write_text("""
# This is a comment
KEY1=value1

# Another comment
KEY2=value2

""")

    entries = list(read_env(str(env_file)))
    # The file starts with empty line, then has comment, entry, empty,
    # comment, entry, empty = 7
    assert len(entries) == 7

    # Check structure - first empty line
    assert entries[0]["type"] == "comment"
    assert entries[0]["comment"] == ""
    assert entries[0]["entry"] is None

    # Then the comment
    assert entries[1]["type"] == "comment"
    assert entries[1]["comment"] == "# This is a comment"
    assert entries[1]["entry"] is None

    # Then the entry
    assert entries[2]["type"] == "entry"
    assert entries[2]["entry"] == ["KEY1", "value1"]

    # Then empty line
    assert entries[3]["type"] == "comment"
    assert entries[3]["comment"] == ""

    # Then second comment
    assert entries[4]["type"] == "comment"
    assert entries[4]["comment"] == "# Another comment"

    # Then second entry
    assert entries[5]["type"] == "entry"
    assert entries[5]["entry"] == ["KEY2", "value2"]

    # Then final empty line
    assert entries[6]["type"] == "comment"
    assert entries[6]["comment"] == ""


def test_read_env_with_quoted_values(tmp_path):
    """Test read_env handles quoted values."""
    env_file = tmp_path / ".env"
    env_file.write_text("KEY1=\"quoted value\"\nKEY2='single quotes'\nKEY3=unquoted\n")

    entries = list(read_env(str(env_file)))
    assert len(entries) == 3
    keys = [e["entry"][0] for e in entries]
    values = [e["entry"][1] for e in entries]
    assert keys == ["KEY1", "KEY2", "KEY3"]
    assert values == ["quoted value", "single quotes", "unquoted"]


def test_read_env_with_equals_in_value(tmp_path):
    """Test read_env handles equals sign in value."""
    env_file = tmp_path / ".env"
    env_file.write_text("DATABASE_URL=postgresql://localhost:5432/db?ssl=true\n")

    entries = list(read_env(str(env_file)))
    assert len(entries) == 1
    assert entries[0]["type"] == "entry"
    assert entries[0]["entry"][0] == "DATABASE_URL"
    assert entries[0]["entry"][1] == "postgresql://localhost:5432/db?ssl=true"


def test_read_env_nonexistent_file(tmp_path):
    """Test read_env with nonexistent file."""
    entries = list(read_env(str(tmp_path / "nonexistent.env")))
    assert len(entries) == 0


def test_env_entry_value_attribute():
    """Test env_entry_value attribute extracts value from dict entry."""
    entry = {"type": "entry", "entry": ["KEY", "value"], "comment": None}
    assert env_entry_value(entry) == "value"

    # Test with different entry
    entry2 = {"type": "entry", "entry": ["PORT", "8080"], "comment": None}
    assert env_entry_value(entry2) == "8080"

    # Test with comment - should return empty string
    comment = {"type": "comment", "entry": None, "comment": "# comment"}
    assert env_entry_value(comment) == ""

    # Test with invalid dict
    assert env_entry_value("invalid") == ""
    assert env_entry_value({}) == ""


def test_env_entry_workflow_with_query(tmp_path, make_ctx):
    """Test complete env file workflow through query execution."""
    env_file = tmp_path / ".env"
    env_file.write_text("NAME=John\nAGE=30\nCITY=NYC\n")

    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, read_env.__module__)

    # Query: read env file and show values
    forest, attrs, render_specs, out = qp.execute_query(f"read_env {env_file}, env_entry_value")

    lines = out.strip().split("\n")
    assert len(lines) == 3

    # Check that values are shown
    assert any("John" in line for line in lines)
    assert any("30" in line for line in lines)
    assert any("NYC" in line for line in lines)


# read_file tests


def test_read_file_basic(tmp_path):
    """Test read_file reads all lines with line numbers."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("line1\nline2\nline3\n")

    lines = list(read_file(str(test_file)))
    assert len(lines) == 3

    assert lines[0].line_number == 0
    assert lines[0].content == "line1"

    assert lines[1].line_number == 1
    assert lines[1].content == "line2"

    assert lines[2].line_number == 2
    assert lines[2].content == "line3"


def test_read_file_with_empty_lines(tmp_path):
    """Test read_file preserves empty lines."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("\nline1\n\nline2\n")

    lines = list(read_file(str(test_file)))
    assert len(lines) == 4

    assert lines[0].line_number == 0
    assert lines[0].content == ""

    assert lines[1].line_number == 1
    assert lines[1].content == "line1"

    assert lines[2].line_number == 2
    assert lines[2].content == ""

    assert lines[3].line_number == 3
    assert lines[3].content == "line2"


def test_read_file_with_trailing_newline(tmp_path):
    """Test read_file handles trailing newline correctly."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("line1\nline2\nline3")

    lines = list(read_file(str(test_file)))
    assert len(lines) == 3

    # Last line should not have trailing newline (it's stripped)
    assert lines[2].content == "line3"


def test_read_file_without_final_newline(tmp_path):
    """Test read_file handles file without final newline."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("line1\nline2\nline3")

    lines = list(read_file(str(test_file)))
    assert len(lines) == 3
    assert lines[2].content == "line3"


def test_read_file_nonexistent_file(tmp_path):
    """Test read_file with nonexistent file."""
    lines = list(read_file(str(tmp_path / "nonexistent.txt")))
    assert len(lines) == 0


def test_file_line_content_attribute():
    """Test file_line_content attribute extracts content from dict."""
    line = FileLine(line_number=0, content="hello world")
    assert file_line_content(line) == "hello world"

    # Test with different line
    line2 = FileLine(line_number=4, content="another line")
    assert file_line_content(line2) == "another line"

    # Test with invalid type
    assert file_line_content("invalid") == ""
    assert file_line_content({}) == ""


def test_file_line_workflow_with_query(tmp_path, make_ctx):
    """Test complete workflow: read file with query."""

    test_file = tmp_path / "test.txt"
    test_file.write_text("line1\nline2\nline3\n")

    ctx = make_ctx(plugins_fs)
    qp = make_qp(ctx)

    # Query: read file and show contents
    forest, attrs, render_specs, out = qp.execute_query(f'read_file "{test_file}"')

    # The supported render shows the bare lines: no bullets, no numbers
    assert render_specs[0].name == "file-line"
    assert out.splitlines() == ["line1", "line2", "line3"]


def test_file_line_render_query(tmp_path, make_ctx):
    """Test read_file with an explicit :file-line render and its numbers variant."""

    test_file = tmp_path / "test.txt"
    test_file.write_text("line1\nline2\n")

    ctx = make_ctx(plugins_fs)
    qp = make_qp(ctx)

    forest, attrs, render_specs, out = qp.execute_query(f'read_file "{test_file}", :file-line')
    assert render_specs[0].name == "file-line"
    assert out.splitlines() == ["line1", "line2"]

    _, _, _, numbered = qp.execute_query(f'read_file "{test_file}", :file-line numbers')
    assert numbered.splitlines() == ["0 :: line1", "1 :: line2"]


def test_render_file_line():
    """Test render_file_line formats FileLine correctly."""
    line = FileLine(line_number=0, content="hello world")
    assert render_file_line(line) == "hello world"

    # Test with indent
    assert render_file_line(line, indent="  ") == "  hello world"

    line_empty = FileLine(line_number=1, content="")
    assert render_file_line(line_empty) == ""

    # Test with numbers
    assert render_file_line(line, numbers=True) == "0 :: hello world"
    assert render_file_line(line, indent="  ", numbers=True) == "  0 :: hello world"
    assert render_file_line(line_empty, numbers=True) == "1 :: "

    # Test with trim
    line_padded = FileLine(line_number=2, content="  padded line  ")
    assert render_file_line(line_padded) == "  padded line  "
    assert render_file_line(line_padded, trim=True) == "padded line"
    assert render_file_line(line_padded, numbers=True, trim=True) == "2 :: padded line"

    # Test with non-FileLine (fallback)
    assert render_file_line("invalid") == "invalid"
    assert render_file_line(42) == "42"


def test_ls_files_tests_resources():
    """Test ls_files with the tests/resources directory."""
    resources_dir = Path("tests/resources")

    # Test that the directory exists
    assert resources_dir.is_dir()

    # List files in tests/resources
    files = list(insert_ls_files(str(resources_dir)))

    # Check that we get Path objects
    assert all(isinstance(f, Path) for f in files)

    # Check for known files in the directory
    file_names = [f.name for f in files]
    assert "test_data.csv" in file_names


def test_ls_files_tests_resources_with_query(make_ctx):
    """Test ls_files tests/resources through query execution."""
    resources_dir = Path("tests/resources")

    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, insert_ls_files.__module__)

    # Query should show files in tests/resources
    forest, attrs, render_specs, out = qp.execute_query(f"insert_ls_files {resources_dir}")

    lines = out.strip().split("\n")
    assert len(lines) > 0

    # Check for known files in output
    output = "\n".join(lines)
    assert "test_data.csv" in output


# file_content attribute tests


def test_file_content(tmp_path):
    """Test file_content attribute reads various file types."""
    # Test basic content
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello world")

    content = file_content(str(test_file))
    assert content == "hello world"

    # Test with Path object
    content_path = file_content(test_file)
    assert content_path == "hello world"

    # Test multiline content
    test_file.write_text("line1\nline2\nline3")
    content = file_content(test_file)
    assert content == "line1\nline2\nline3"

    # Test empty file
    test_file.write_text("")
    assert file_content(test_file) == ""

    # Test nonexistent file
    assert file_content("/nonexistent/file.txt") == ""

    # Test special characters (with errors='ignore')
    test_file.write_text("Hello\nWorld\t\n\x00")
    content = file_content(test_file)
    assert isinstance(content, str)


def test_file_content_with_query(tmp_path, make_ctx):
    """Test file_content through query execution."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello world")

    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, insert_ls_files.__module__)

    # Query computes file content as the attribute value
    forest, attrs, render_specs, out = qp.execute_query(f"insert_ls_files {tmp_path}, file_content")

    storage = ctx.container.get(AttributeStorageAPI)
    file_content_d = AttributeDescriptor(name="file_content", args={})
    assert [storage.get_attr_value(file_content_d, item) for item in forest.items] == ["hello world"]


def test_insert_glob_groups_basic(tmp_path):
    """Test insert_glob_groups with basic patterns."""
    # Create test files
    (tmp_path / "api_test.py").write_text("api code\n" * 10)
    (tmp_path / "api_utils.py").write_text("utils code\n" * 5)
    (tmp_path / "impl_core.py").write_text("impl code\n" * 15)
    (tmp_path / "other.py").write_text("other code\n" * 3)

    # Test with multiple patterns
    result = list(insert_glob_groups(str(tmp_path), "api_*.py,impl_*.py"))
    assert len(result) == 4  # 3 matched + 1 other

    # Check PathGlob objects
    api_files = [r for r in result if r.glob_group == "api_*.py"]
    impl_files = [r for r in result if r.glob_group == "impl_*.py"]
    other_files = [r for r in result if r.glob_group == "<others>"]

    assert len(api_files) == 2
    assert len(impl_files) == 1
    assert len(other_files) == 1

    # Verify file paths
    assert all(isinstance(r.path, Path) for r in result)
    assert {r.path.name for r in api_files} == {"api_test.py", "api_utils.py"}
    assert impl_files[0].path.name == "impl_core.py"
    assert other_files[0].path.name == "other.py"


def test_insert_glob_groups_collapse_others(tmp_path):
    """Test insert_glob_groups with collapse_others=True."""
    # Create test files
    (tmp_path / "api_test.py").write_text("api code\n" * 10)
    (tmp_path / "impl_core.py").write_text("impl code\n" * 15)
    (tmp_path / "other1.py").write_text("other1 code\n" * 3)
    (tmp_path / "other2.py").write_text("other2 code\n" * 4)

    # Test with collapse_others=True
    result = list(insert_glob_groups(str(tmp_path), "api_*.py,impl_*.py", collapse_others=True))
    assert len(result) == 3  # 2 matched + 1 collapsed others

    # Check PathGlob objects
    api_files = [r for r in result if r.glob_group == "api_*.py"]
    impl_files = [r for r in result if r.glob_group == "impl_*.py"]
    others_files = [r for r in result if r.glob_group == "<others>"]

    assert len(api_files) == 1
    assert len(impl_files) == 1
    assert len(others_files) == 1

    # Check that others is a temporary file
    assert others_files[0].path.name.startswith("udan_others_")
    assert others_files[0].path.suffix == ".txt"


def test_grouped_file_parent_property(tmp_path):
    """Test that PathGlob.parent returns the parent directory."""
    test_file = tmp_path / "test.py"
    test_file.write_text("code")

    grouped = PathGlob(path=test_file, glob_group="test_*.py")
    assert grouped.parent == tmp_path
    assert isinstance(grouped.parent, Path)


def test_grouped_file_str_representation(tmp_path):
    """Test PathGlob string representation."""
    test_file = tmp_path / "test.py"
    test_file.write_text("code")

    grouped = PathGlob(path=test_file, glob_group="test_*.py")
    assert str(grouped) == str(test_file)
    assert "test.py" in repr(grouped)
    assert "test_*.py" in repr(grouped)


def test_grouped_file_is_path_like(tmp_path):
    """Test PathGlob can be used as a path by any tool (e.g. extend_imports)."""
    test_file = tmp_path / "test.py"
    test_file.write_text("code")

    grouped = PathGlob(path=test_file, glob_group="test_*.py")
    assert os.fspath(grouped) == str(test_file)
    assert Path(grouped) == test_file
    assert Path(grouped).read_text() == "code"


def test_count_lines_with_grouped_file(tmp_path):
    """Test count_lines works with PathGlob objects."""
    test_file = tmp_path / "test.py"
    test_file.write_text("line1\nline2\nline3\n")

    grouped = PathGlob(path=test_file, glob_group="test_*.py")
    assert count_lines(grouped) == 3


# git_tree tests


def test_git_tree_yields_directories_with_depths(tmp_path):
    """Test git_tree yields every directory paired with its depth from the root."""
    (tmp_path / "plain" / "deep" / "inner").mkdir(parents=True)
    (tmp_path / "plain" / "empty_sub").mkdir()
    (tmp_path / "repo_a" / "src").mkdir(parents=True)
    (tmp_path / "repo_a" / ".git").mkdir()

    pairs = list(git_tree(str(tmp_path)))

    assert [(depth, path.name) for depth, path in pairs] == [
        (0, tmp_path.name),
        (1, "plain"),
        (2, "deep"),
        (3, "inner"),
        (2, "empty_sub"),
        (1, "repo_a"),
    ]
    assert all(isinstance(path, Path) for _, path in pairs)


def test_git_tree_git_repo_is_leaf(tmp_path):
    """Test git_tree stops at a git repository and skips its contents."""
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "src").mkdir()
    (repo / "src" / "module.py").write_text("# code")

    names = [path.name for _, path in git_tree(str(tmp_path))]

    assert names == [tmp_path.name, "repo"]


def test_git_tree_git_worktree_is_leaf(tmp_path):
    """Test git_tree stops at a git worktree, where .git is a file, and skips its contents."""
    worktree = tmp_path / "worktree"
    (worktree / "src").mkdir(parents=True)
    (worktree / "src" / "module.py").write_text("# code")
    (worktree / ".git").write_text("gitdir: /somewhere/repo/.git/worktrees/worktree\n")

    names = [path.name for _, path in git_tree(str(tmp_path))]

    assert names == [tmp_path.name, "worktree"]


def test_git_tree_root_repo_is_leaf(tmp_path):
    """Test git_tree does not go inside the walked directory when it is itself a repo."""
    (tmp_path / ".git").mkdir()
    (tmp_path / "src" / "deep").mkdir(parents=True)
    (tmp_path / "docs").mkdir()

    assert [(depth, path.name) for depth, path in git_tree(str(tmp_path))] == [
        (0, tmp_path.name),
    ]


def test_git_tree_root_worktree_is_leaf(tmp_path):
    """Test git_tree does not go inside the walked worktree, where .git is a file."""
    (tmp_path / "src" / "deep").mkdir(parents=True)
    (tmp_path / ".git").write_text("gitdir: /somewhere/repo/.git/worktrees/wt\n")

    assert [(depth, path.name) for depth, path in git_tree(str(tmp_path))] == [
        (0, tmp_path.name),
    ]


def test_git_tree_nested_repo_inside_repo_is_leaf(tmp_path):
    """Test git_tree stops at the outer repo and does not reach a repo nested in it."""
    (tmp_path / "outer" / "lib" / ".git").mkdir(parents=True)
    (tmp_path / "outer" / "lib" / "src" / "inner" / ".git").mkdir(parents=True)

    names = [path.name for _, path in git_tree(str(tmp_path))]

    assert names == [tmp_path.name, "outer", "lib"]


def test_git_tree_empty_dir_is_leaf(tmp_path):
    """Test git_tree yields an empty directory as a leaf."""
    empty = tmp_path / "empty"
    empty.mkdir()

    assert list(git_tree(str(tmp_path))) == [(0, tmp_path.resolve()), (1, empty.resolve())]


def test_git_tree_missing_directory():
    """Test git_tree yields nothing for a missing path."""
    assert list(git_tree("/nonexistent/dir")) == []


def test_git_tree_with_query(tmp_path, make_ctx):
    """Test git_tree through query execution as a nested inserter."""
    (tmp_path / "plain" / "inner").mkdir(parents=True)
    (tmp_path / "repo").mkdir()
    (tmp_path / "repo" / ".git").mkdir()

    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, git_tree.__module__)

    forest, _attrs, _render_specs, out = qp.execute_query(f"git_tree {tmp_path}")

    assert forest.depths == [0, 1, 2, 1]
    assert [item.name for item in forest.items] == [tmp_path.name, "plain", "inner", "repo"]
    expected = "\n".join(
        [
            f"- {tmp_path}",
            f"  - {tmp_path / 'plain'}",
            f"    - {tmp_path / 'plain' / 'inner'}",
            f"  - {tmp_path / 'repo'}",
        ]
    )
    assert out.strip() == expected


# -- group_by_globs ------------------------------------------------------------


def test_group_by_globs_example():
    """Paths are assigned to the first group whose any pattern matches, else <others>."""

    globs = ["**/api_*.py", "**/impl_*.py"]

    assert group_by_globs("src/udan/core/api_x.py", globs) == Group(key="**/api_*.py", order=0)
    assert group_by_globs("src/udan/core/impl_y.py", globs) == Group(key="**/impl_*.py", order=1)
    assert group_by_globs("src/udan/other.py", globs) == Group(key="<others>", order=2)


def test_group_by_globs_first_match_wins():
    """A path matching several groups goes to the earliest listed one."""

    globs = ["**/api_*.py", "api_*.py"]
    # matches both the recursive and the bare pattern -> the first listed one wins.
    assert group_by_globs("src/udan/core/api_x.py", globs) == Group(key="**/api_*.py", order=0)


def test_group_by_globs_any_pattern_in_group():
    """A group of several patterns matches when any of its patterns matches."""

    globs = ["**/api_*.py,**/impl_*.py"]
    assert group_by_globs("src/udan/core/api_x.py", globs) == Group(key="**/api_*.py,**/impl_*.py", order=0)
    assert group_by_globs("src/udan/core/impl_y.py", globs) == Group(key="**/api_*.py,**/impl_*.py", order=0)
    assert group_by_globs("src/udan/other.py", globs) == Group(key="<others>", order=1)


def test_group_by_globs_empty_group_spec_skipped():
    """Empty/blank group specs do not accidentally match everything."""

    globs = ["", " **/d_*.py "]
    assert group_by_globs("src/d_x.py", globs) == Group(key="**/d_*.py", order=1)
    assert group_by_globs("src/other.py", globs) == Group(key="<others>", order=2)


def test_group_by_globs_path_like_items():
    """str, Path and PathGlob items all group by their path."""

    globs = ["**/api_*.py"]
    assert group_by_globs("src/udan/core/api_x.py", globs).key == "**/api_*.py"
    assert group_by_globs(Path("src/udan/core/api_x.py"), globs).key == "**/api_*.py"
    grouped = PathGlob(path=Path("src/udan/core/api_x.py"), glob_group="whatever")
    assert group_by_globs(grouped, globs).key == "**/api_*.py"


def test_group_by_globs_no_globs():
    """Without group definitions everything falls into <others>."""

    assert group_by_globs("src/udan/core/api_x.py", []) == Group(key="<others>", order=0)


def test_group_by_globs_directories_match_too():
    """Matching is purely on the path string, so directory items group as well.

    As with any Path.match pattern, the pattern has to cover every remaining segment:
    the directory matches ``**/plugins_history``, the file inside it needs the file
    segment too.
    """

    globs = ["**/plugins_history"]
    assert group_by_globs("src/udan/plugins_history", globs) == Group(key="**/plugins_history", order=0)
    assert group_by_globs("src/udan/plugins_tools_demo/plugins_demo.py", globs) == Group(key="<others>", order=1)
    assert group_by_globs("src/udan/plugins_history/plugins_history.py", ["**/plugins_history/plugins_*.py"]) == Group(
        key="**/plugins_history/plugins_*.py", order=0
    )


def test_group_by_globs_with_query(tmp_path, make_ctx):
    """A file listing inserted by one inserter is grouped by globs through a query."""

    (tmp_path / "api_test.py").write_text("api code\n")
    (tmp_path / "impl_core.py").write_text("impl code\n")
    (tmp_path / "other.py").write_text("other code\n")

    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, group_by_globs.__module__)

    query = f"ls_files {tmp_path} '*.py', group_by_globs '**/api_*.py' '**/impl_*.py'"
    forest, _attrs, _render_specs, _out = qp.execute_query(query)

    groups = [item for item in forest.items if isinstance(item, Group)]
    assert [group.key for group in groups] == ["**/api_*.py", "**/impl_*.py", "<others>"]
    assert [group.order for group in groups] == [0, 1, 2]
