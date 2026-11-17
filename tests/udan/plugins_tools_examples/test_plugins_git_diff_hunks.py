"""Tests for git diff hunk extension and rendering."""

import os as _os
import subprocess

import pytest

from tests.conftest import make_qp, register_tools_from_module
from udan.plugins_tools_examples import plugins_git
from udan.plugins_tools_examples.plugins_git import (
    DiffHunk,
    _parse_hunk_header,
    extend_diff_hunks,
    insert_diff,
    render_org_diff_hunk,
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


def test_parse_hunk_header():
    """Test parsing git diff hunk headers."""
    # Standard hunk header
    result = _parse_hunk_header("@@ -1,3 +1,4 @@")
    assert result == (1, 3, 1, 4)

    # Hunk header without counts (defaults to 1)
    result = _parse_hunk_header("@@ -5 +7 @@")
    assert result == (5, 1, 7, 1)

    # Hunk header with function context
    result = _parse_hunk_header("@@ -10,5 +10,6 @@ function_name")
    assert result == (10, 5, 10, 6)


def test_insert_diff_with_repo_path(tmp_path):
    """Test that insert_diff includes repo_path in GitDiffFile."""
    # Initialize git repo
    assert subprocess_run_mock(tmp_path, ["git", "init"]).returncode == 0
    subprocess_run_mock(tmp_path, ["git", "config", "user.email", "test@example.com"])
    subprocess_run_mock(tmp_path, ["git", "config", "user.name", "Test User"])

    # Create and commit a file
    test_file = tmp_path / "test.txt"
    test_file.write_text("line1\nline2\nline3\n")
    subprocess_run_mock(tmp_path, ["git", "add", "test.txt"])
    subprocess_run_mock(tmp_path, ["git", "commit", "-m", "Initial"])

    # Modify the file
    test_file.write_text("line1\nline2-modified\nline3\n")

    # Get diffs (use keyword arg for directory)
    diffs = list(insert_diff(directory=str(tmp_path)))

    assert len(diffs) == 1
    assert diffs[0].file_path == "test.txt"
    assert diffs[0].repo_path == str(tmp_path)
    assert "line2-modified" in diffs[0].diff_content


def test_extend_diff_hunks_single_hunk(tmp_path):
    """Test extending a GitDiffFile with hunks."""
    # Initialize git repo
    assert subprocess_run_mock(tmp_path, ["git", "init"]).returncode == 0
    subprocess_run_mock(tmp_path, ["git", "config", "user.email", "test@example.com"])
    subprocess_run_mock(tmp_path, ["git", "config", "user.name", "Test User"])

    # Create and commit a file
    test_file = tmp_path / "test.txt"
    test_file.write_text("line1\nline2\nline3\n")
    subprocess_run_mock(tmp_path, ["git", "add", "test.txt"])
    subprocess_run_mock(tmp_path, ["git", "commit", "-m", "Initial"])

    # Modify the file
    test_file.write_text("line1\nline2-modified\nline3\n")

    # Get diffs and extend with hunks (use keyword arg for directory)
    diffs = list(insert_diff(directory=str(tmp_path)))
    assert len(diffs) == 1

    hunks = list(extend_diff_hunks(diffs[0]))
    assert len(hunks) == 1

    hunk = hunks[0]
    assert isinstance(hunk, DiffHunk)
    assert hunk.file_path == "test.txt"
    assert hunk.repo_path == str(tmp_path)
    assert hunk.old_start == 1
    assert hunk.new_start == 1
    assert hunk.hunk_index == 0
    assert "line2" in hunk.removed_lines
    assert "line2-modified" in hunk.added_lines


def test_extend_diff_hunks_multiple_hunks(tmp_path):
    """Test extending a GitDiffFile with multiple hunks."""
    # Initialize git repo
    assert subprocess_run_mock(tmp_path, ["git", "init"]).returncode == 0
    subprocess_run_mock(tmp_path, ["git", "config", "user.email", "test@example.com"])
    subprocess_run_mock(tmp_path, ["git", "config", "user.name", "Test User"])

    # Create and commit a file with multiple lines
    test_file = tmp_path / "test.txt"
    test_file.write_text("\n".join([f"line{i}" for i in range(1, 11)]))
    subprocess_run_mock(tmp_path, ["git", "add", "test.txt"])
    subprocess_run_mock(tmp_path, ["git", "commit", "-m", "Initial"])

    # Modify multiple locations
    test_file.write_text("line1\nline2-modified\nline3\nline4\nline5-changed\nline6\nline7\nline8\nline9\nline10\n")

    # Get diffs and extend with hunks (use keyword arg for directory)
    diffs = list(insert_diff(directory=str(tmp_path)))
    assert len(diffs) == 1

    hunks = list(extend_diff_hunks(diffs[0]))
    assert len(hunks) >= 1

    # Check that hunk indices are sequential
    for i, hunk in enumerate(hunks):
        assert hunk.hunk_index == i


def test_render_org_diff_hunk():
    """Test rendering DiffHunk in org format."""
    # Create a test hunk
    hunk = DiffHunk(
        file_path="test.txt",
        repo_path="/tmp/repo",
        hunk_header="@@ -1,3 +1,4 @@",
        old_start=1,
        old_count=3,
        new_start=1,
        new_count=4,
        hunk_content="@@ -1,3 +1,4 @@\n line1\n-line2\n+line2-modified\n line3\n+new line\n",
        context_before=["line1"],
        removed_lines=["line2"],
        added_lines=["line2-modified"],
        context_after=["line3"],
        hunk_index=0,
    )

    result = render_org_diff_hunk(hunk)

    assert "*** test.txt (hunk 0)" in result
    assert ":path: test.txt" in result
    assert ":repo_path: /tmp/repo" in result
    assert ":hunk_index: 0" in result
    assert "#+begin_src diff" in result
    assert "#+end_src" in result


def test_render_org_diff_hunk_with_non_hunk_item():
    """Test render_org_diff_hunk with non-DiffHunk item."""

    result = render_org_diff_hunk("not a hunk")
    assert result == "- not a hunk"


def test_render_org_diff_hunk_words_uses_wdiff_block():
    """Test render_org_diff_hunk marks word-level hunks with a wdiff src block."""
    hunk = DiffHunk(
        file_path="test.txt",
        repo_path="/tmp/repo",
        hunk_header="@@ -1,3 +1,3 @@",
        old_start=1,
        old_count=3,
        new_start=1,
        new_count=3,
        hunk_content="@@ -1,3 +1,3 @@\n line1\n[-line2-]{+line2-modified+}\n line3",
        context_before=["line1"],
        removed_lines=["line2"],
        added_lines=["line2-modified"],
        context_after=["line3"],
        hunk_index=0,
        words=True,
    )

    result = render_org_diff_hunk(hunk)

    assert "#+begin_src wdiff" in result
    assert "#+begin_src diff" not in result


def test_diff_hunk_workflow_with_query(make_ctx, tmp_path):
    """Test full diff hunk workflow using query."""
    # Initialize git repo
    ctx = make_ctx(plugins_git)
    qp = make_qp(ctx)
    assert subprocess_run_mock(tmp_path, ["git", "init"]).returncode == 0
    subprocess_run_mock(tmp_path, ["git", "config", "user.email", "test@example.com"])
    subprocess_run_mock(tmp_path, ["git", "config", "user.name", "Test User"])

    # Create and commit a file
    test_file = tmp_path / "test.txt"
    test_file.write_text("line1\nline2\nline3\n")
    subprocess_run_mock(tmp_path, ["git", "add", "test.txt"])
    subprocess_run_mock(tmp_path, ["git", "commit", "-m", "Initial"])

    # Modify the file
    test_file.write_text("line1\nline2-modified\nline3\n")

    # Register git plugin

    register_tools_from_module(ctx, plugins_git.__name__)

    # Query: get diffs, extend with hunks, render in org format
    # Use space-separated args (commas are pipeline separators in udan)
    forest, attrs, render_specs, out = qp.execute_query(
        f'git.insert_diff HEAD "{tmp_path}", extend_diff_hunks, :org-diff-hunk'
    )

    # Should contain hunk information
    assert "*** test.txt (hunk 0)" in out
    assert ":path: test.txt" in out
    assert "#+begin_src diff" in out
