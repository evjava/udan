"""Tests for git plugin functionality."""

import os as _os
import subprocess

import pytest

from udan.plugins_tools_examples.plugins_git import (
    GitDiffFile,
    git_diff_file_size,
    insert_diff,
    insert_status,
    render_org_diff,
)

# Mark all tests in this module as xdist-incompatible
# Git tests interfere with each other when run in parallel
pytestmark = pytest.mark.xdist_group("git_test")


def subprocess_run_mock(cwd, cmd):
    """Mock subprocess.run for testing with GIT_DIR env isolation."""

    env = _os.environ.copy()
    env["GIT_DIR"] = str(cwd / ".git")
    env["GIT_WORK_TREE"] = str(cwd)
    env.pop("GIT_ALTERNATE_OBJECT_DIRECTORIES", None)
    env.pop("GIT_OBJECT_DIRECTORY", None)
    env.pop("GIT_INDEX_FILE", None)
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)


def test_insert_diff_in_git_repo(tmp_path):
    """Test insert_diff in a git repository with changes."""

    # Initialize git repo
    assert subprocess_run_mock(tmp_path, ["git", "init"]).returncode == 0

    # Configure git
    subprocess_run_mock(tmp_path, ["git", "config", "user.email", "test@example.com"])
    subprocess_run_mock(tmp_path, ["git", "config", "user.name", "Test User"])

    # Create a file and commit it
    test_file = tmp_path / "test.txt"
    test_file.write_text("original content\n")

    subprocess_run_mock(tmp_path, ["git", "add", "test.txt"])
    subprocess_run_mock(tmp_path, ["git", "commit", "-m", "Initial commit"])

    # Modify the file
    test_file.write_text("modified content\n")

    # Test insert_diff directly (use keyword arg for directory)
    diffs = list(insert_diff(directory=str(tmp_path)))

    assert len(diffs) == 1
    assert isinstance(diffs[0], GitDiffFile)
    assert diffs[0].file_path == "test.txt"
    assert "original content" in diffs[0].diff_content
    assert "modified content" in diffs[0].diff_content


def test_insert_diff_words(tmp_path):
    """Test insert_diff with words=True produces word-level diff markers."""

    # Initialize git repo
    assert subprocess_run_mock(tmp_path, ["git", "init"]).returncode == 0

    # Configure git
    subprocess_run_mock(tmp_path, ["git", "config", "user.email", "test@example.com"])
    subprocess_run_mock(tmp_path, ["git", "config", "user.name", "Test User"])

    # Create a file and commit it
    test_file = tmp_path / "test.txt"
    test_file.write_text("original content\n")

    subprocess_run_mock(tmp_path, ["git", "add", "test.txt"])
    subprocess_run_mock(tmp_path, ["git", "commit", "-m", "Initial commit"])

    # Modify a single word within the line
    test_file.write_text("modified content\n")

    # Default (line-based) diff has no word markers
    diffs = list(insert_diff(directory=str(tmp_path)))
    assert len(diffs) == 1
    assert "[-original-]" not in diffs[0].diff_content
    assert diffs[0].words is False

    # Word diff marks the changed word inline
    diffs = list(insert_diff(directory=str(tmp_path), words=True))
    assert len(diffs) == 1
    assert "[-original-]" in diffs[0].diff_content
    assert "{+modified+}" in diffs[0].diff_content
    assert diffs[0].words is True
    # Stats stay line-based
    assert diffs[0].additions == 1
    assert diffs[0].deletions == 1


def test_insert_diff_file_filter(tmp_path):
    """Test insert_diff with file= shows the diff only for that file."""

    # Initialize git repo
    assert subprocess_run_mock(tmp_path, ["git", "init"]).returncode == 0

    # Configure git
    subprocess_run_mock(tmp_path, ["git", "config", "user.email", "test@example.com"])
    subprocess_run_mock(tmp_path, ["git", "config", "user.name", "Test User"])

    # Create two files and commit them
    first_file = tmp_path / "first.txt"
    first_file.write_text("first original\n")
    second_file = tmp_path / "second.txt"
    second_file.write_text("second original\n")

    subprocess_run_mock(tmp_path, ["git", "add", "first.txt", "second.txt"])
    subprocess_run_mock(tmp_path, ["git", "commit", "-m", "Initial commit"])

    # Modify both files
    first_file.write_text("first modified\n")
    second_file.write_text("second modified\n")

    # Without file= both changed files are shown
    diffs = list(insert_diff(directory=str(tmp_path)))
    assert len(diffs) == 2

    # With file= only the requested file is shown
    diffs = list(insert_diff(directory=str(tmp_path), file="first.txt"))
    assert len(diffs) == 1
    assert diffs[0].file_path == "first.txt"
    assert "first original" in diffs[0].diff_content
    assert "first modified" in diffs[0].diff_content

    # An unchanged file yields no diff
    diffs = list(insert_diff(directory=str(tmp_path), file="missing.txt"))
    assert diffs == []


def test_insert_diff_in_non_git_repo(tmp_path):
    """Test insert_diff in a non-git directory."""
    # Just create a directory without git
    test_dir = tmp_path / "not_a_git_repo"
    test_dir.mkdir()

    diffs = list(insert_diff(directory=str(test_dir)))

    # Should return empty result
    assert diffs == []


def test_insert_status_in_git_repo(tmp_path):
    """Test insert_status in a git repository."""

    # Initialize git repo
    subprocess_run_mock(tmp_path, ["git", "init"])
    subprocess_run_mock(tmp_path, ["git", "config", "user.email", "test@example.com"])
    subprocess_run_mock(tmp_path, ["git", "config", "user.name", "Test User"])

    # Create and modify a file
    test_file = tmp_path / "test.txt"
    test_file.write_text("content\n")

    # Test insert_status directly
    status_list = list(insert_status(str(tmp_path)))

    # Should show status
    assert len(status_list) > 0
    # Check that we have dictionaries with status and path
    assert any("test.txt" in item.get("path", "") for item in status_list)
    # Check that each item has status and path keys
    for item in status_list:
        assert "status" in item
        assert "path" in item


def test_insert_status_with_dotfile(tmp_path):
    """Test insert_status correctly handles files starting with dot."""

    # Initialize git repo
    subprocess_run_mock(tmp_path, ["git", "init"])
    subprocess_run_mock(tmp_path, ["git", "config", "user.email", "test@example.com"])
    subprocess_run_mock(tmp_path, ["git", "config", "user.name", "Test User"])

    # Create and stage a dotfile
    dotfile = tmp_path / ".gitignore"
    dotfile.write_text("*.pyc")
    subprocess_run_mock(tmp_path, ["git", "add", ".gitignore"])

    # Test insert_status
    status_list = list(insert_status(str(tmp_path)))

    # Should show the dotfile with correct path (including leading dot)
    dotfile_items = [item for item in status_list if item.get("path") == ".gitignore"]
    assert len(dotfile_items) == 1
    # Check that status is correct (staged added = "A " or "M " after staging)
    assert "status" in dotfile_items[0]
    # Most importantly, verify the path starts with dot, not "gitignore"
    assert dotfile_items[0]["path"] == ".gitignore"


def test_insert_status_in_non_git_repo(tmp_path):
    """Test insert_status in a non-git directory."""
    test_dir = tmp_path / "not_a_git_repo"
    test_dir.mkdir()

    status_list = list(insert_status(str(test_dir)))

    # Should return empty result
    assert status_list == []


def test_render_org_diff():
    """Test render_org_diff function directly."""
    diff = GitDiffFile(file_path="test.txt", diff_content="- line1\n+ line2", additions=1, deletions=1)

    result = render_org_diff(diff)

    assert result == "** test.txt ( +1 -1 )\n#+begin_src diff\n- line1\n+ line2\n#+end_src"


def test_render_org_diff_words_uses_wdiff_block():
    """Test render_org_diff marks word-level diffs with a wdiff src block."""
    diff = GitDiffFile(file_path="test.txt", diff_content="[-old-]{+new+}", additions=1, deletions=1, words=True)

    result = render_org_diff(diff)

    assert result == "** test.txt ( +1 -1 )\n#+begin_src wdiff\n[-old-]{+new+}\n#+end_src"


def test_render_org_diff_with_non_diff_item():
    """Test render_org_diff with non-GitDiffFile item."""
    result = render_org_diff("not a diff")

    assert result == "- not a diff"


def test_git_diff_file_size():
    """Test git_diff_file_size sums additions and deletions."""
    diff = GitDiffFile(file_path="test.txt", diff_content="- a\n+ b", additions=3, deletions=7)

    assert git_diff_file_size(diff) == 10


def test_git_diff_file_size_without_changes():
    """Test git_diff_file_size with zero stats and non-GitDiffFile items."""
    assert git_diff_file_size(GitDiffFile(file_path="test.txt", diff_content="")) == 0
    assert git_diff_file_size("not a diff") == 0


def test_insert_status_modified_filter_only_modified(tmp_path):
    """Test insert_status with modified=True filters to only modified files."""
    # Initialize git repo
    subprocess_run_mock(tmp_path, ["git", "init"])
    subprocess_run_mock(tmp_path, ["git", "config", "user.email", "test@example.com"])
    subprocess_run_mock(tmp_path, ["git", "config", "user.name", "Test User"])

    # Create and stage a file (will show as "A " for added)
    added_file = tmp_path / "added.txt"
    added_file.write_text("new content\n")
    subprocess_run_mock(tmp_path, ["git", "add", "added.txt"])

    # Create a modified file (first commit it, then modify)
    modified_file = tmp_path / "modified.txt"
    modified_file.write_text("original\n")
    subprocess_run_mock(tmp_path, ["git", "add", "modified.txt"])
    subprocess_run_mock(tmp_path, ["git", "commit", "-m", "Initial commit"])
    modified_file.write_text("changed\n")

    # Create an untracked file (will show as "??")
    untracked_file = tmp_path / "untracked.txt"
    untracked_file.write_text("untracked\n")

    # Test with modified=True
    status_modified = list(insert_status(str(tmp_path), modified=True))

    # Should only contain files with 'M' in status (modified.txt with "M " or
    # "MM")
    assert len(status_modified) == 1
    assert status_modified[0]["path"] == "modified.txt"
    assert "M" in status_modified[0]["status"]


def test_insert_status_modified_filter_false(tmp_path):
    """Test insert_status with modified=False returns all files."""
    # Initialize git repo
    subprocess_run_mock(tmp_path, ["git", "init"])
    subprocess_run_mock(tmp_path, ["git", "config", "user.email", "test@example.com"])
    subprocess_run_mock(tmp_path, ["git", "config", "user.name", "Test User"])

    # Create various types of files
    added_file = tmp_path / "added.txt"
    added_file.write_text("new content\n")
    subprocess_run_mock(tmp_path, ["git", "add", "added.txt"])

    untracked_file = tmp_path / "untracked.txt"
    untracked_file.write_text("untracked\n")

    # Test with modified=False
    status_all = list(insert_status(str(tmp_path), modified=False))

    # Should return all files (added and untracked)
    assert len(status_all) == 2
    paths = {item["path"] for item in status_all}
    assert "added.txt" in paths
    assert "untracked.txt" in paths


def test_insert_status_modified_filter_none(tmp_path):
    """Test insert_status with modified=None (default) returns all files."""
    # Initialize git repo
    subprocess_run_mock(tmp_path, ["git", "init"])
    subprocess_run_mock(tmp_path, ["git", "config", "user.email", "test@example.com"])
    subprocess_run_mock(tmp_path, ["git", "config", "user.name", "Test User"])

    # Create various types of files
    added_file = tmp_path / "added.txt"
    added_file.write_text("new content\n")
    subprocess_run_mock(tmp_path, ["git", "add", "added.txt"])

    untracked_file = tmp_path / "untracked.txt"
    untracked_file.write_text("untracked\n")

    # Test with modified=None (default behavior)
    status_default = list(insert_status(str(tmp_path), modified=None))

    # Should return all files
    assert len(status_default) == 2
    paths = {item["path"] for item in status_default}
    assert "added.txt" in paths
    assert "untracked.txt" in paths
