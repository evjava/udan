"""Tests for the git commits inserter and the commit renders."""

import os as _os
import re
import subprocess
from pathlib import Path

import pytest

from tests.conftest import make_qp
from udan.attributes import plugins_operators_attribute
from udan.plugins_tools_examples import plugins_builtins, plugins_git
from udan.plugins_tools_examples.plugins_git import (
    DiffHunk,
    GitDiffFile,
    commits,
    insert_diff,
    render_commit_log,
    render_org_commit_diff,
)

# Mark all tests in this module as xdist-incompatible
# Git tests interfere with each other when run in parallel
pytestmark = pytest.mark.xdist_group("git_test")

_COMMIT_LINE_PATTERN = r"^\d{4}-\d{2}-\d{2}--\d{2}-\d{2} [0-9a-f]+ :: .+$"


def _run_git(cwd: Path, *args: str, work_tree: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a git command in the given directory with GIT_DIR env isolation."""
    env = _os.environ.copy()
    env["GIT_DIR"] = str(cwd / ".git")
    if work_tree:
        env["GIT_WORK_TREE"] = str(cwd)
    else:
        env.pop("GIT_WORK_TREE", None)
    env.pop("GIT_ALTERNATE_OBJECT_DIRECTORIES", None)
    env.pop("GIT_OBJECT_DIRECTORY", None)
    env.pop("GIT_INDEX_FILE", None)
    return subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True)


def _init_repo(tmp_path: Path) -> Path:
    """Create a git repository with user identity configured."""
    repo = tmp_path / "repo"
    repo.mkdir()

    assert _run_git(repo, "init").returncode == 0
    assert _run_git(repo, "config", "user.email", "test@example.com").returncode == 0
    assert _run_git(repo, "config", "user.name", "Test User").returncode == 0

    return repo


def _commit_all(repo: Path, message: str) -> None:
    """Commit the working file with the given message."""
    (repo / "file.txt").write_text(f"content for {message}\n")

    assert _run_git(repo, "add", "file.txt").returncode == 0
    assert _run_git(repo, "commit", "-m", message).returncode == 0


def _push_to_bare_remote(tmp_path: Path, repo: Path) -> None:
    """Push the repository history to a bare remote, marking commits as pushed."""
    remote = tmp_path / "remote.git"
    assert _run_git(tmp_path, "init", "--bare", remote.name, work_tree=False).returncode == 0
    assert _run_git(repo, "remote", "add", "origin", str(remote)).returncode == 0
    assert _run_git(repo, "push", "origin", "HEAD").returncode == 0


def test_render_commit_log_unpushed(tmp_path):
    """Test render_commit_log shows date, hash, message and UNPUSHED marker."""
    repo = _init_repo(tmp_path)
    _commit_all(repo, "initial commit")

    items = list(commits(directory=str(repo)))
    assert len(items) == 1

    result = render_commit_log(items[0])

    assert re.match(_COMMIT_LINE_PATTERN, result)
    assert result.endswith(" :: initial commit / UNPUSHED")


def test_render_commit_log_pushed(tmp_path):
    """Test render_commit_log has no UNPUSHED marker for pushed commits."""
    repo = _init_repo(tmp_path)
    _commit_all(repo, "pushed commit")
    _push_to_bare_remote(tmp_path, repo)

    items = list(commits(directory=str(repo)))
    assert len(items) == 1

    result = render_commit_log(items[0])

    assert re.match(_COMMIT_LINE_PATTERN, result)
    assert result.endswith(" :: pushed commit")
    assert "UNPUSHED" not in result


def test_render_commit_log_multiline_message(tmp_path):
    """Test render_commit_log marks multi-line messages with ' ...' and hides the body."""
    repo = _init_repo(tmp_path)
    (repo / "file.txt").write_text("content\n")
    assert _run_git(repo, "add", "file.txt").returncode == 0
    assert _run_git(repo, "commit", "-m", "commit subject", "-m", "body line").returncode == 0

    items = list(commits(directory=str(repo)))
    assert len(items) == 1

    result = render_commit_log(items[0])

    assert result.endswith(" :: commit subject ... / UNPUSHED")


def test_render_commit_log_single_line_message_has_no_continuation(tmp_path):
    """Test render_commit_log has no ' ...' marker for single-line messages."""
    repo = _init_repo(tmp_path)
    _commit_all(repo, "initial commit")

    items = list(commits(directory=str(repo)))

    result = render_commit_log(items[0])

    assert " ..." not in result


def test_render_commit_log_non_commit_item():
    """Test render_commit_log falls back to plain string for non-commit items."""
    assert render_commit_log("just a string") == "just a string"
    assert render_commit_log("just a string", indent="  ") == "  just a string"


def test_insert_diff_shows_root_commit_files(tmp_path):
    """The per-commit range form {hash}^..{hash} shows the root commit's files."""
    repo = _init_repo(tmp_path)
    _commit_all(repo, "root commit")
    root_hash = _run_git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "file.txt").write_text("modified content\n")
    assert _run_git(repo, "add", "file.txt").returncode == 0
    assert _run_git(repo, "commit", "-m", "second commit").returncode == 0

    diffs = list(insert_diff(commit_arg=f"{root_hash}^..{root_hash}", directory=str(repo)))

    assert [diff.file_path for diff in diffs] == ["file.txt"]
    assert "+content for root commit" in diffs[0].diff_content


def test_insert_diff_single_ref_keeps_working_tree_semantics(tmp_path):
    """A single ref still means working tree vs that ref, even when it is the root commit."""
    repo = _init_repo(tmp_path)
    _commit_all(repo, "root commit")
    (repo / "file.txt").write_text("modified content\n")

    diffs = list(insert_diff(directory=str(repo)))

    assert [diff.file_path for diff in diffs] == ["file.txt"]
    assert "+modified content" in diffs[0].diff_content
    assert "new file mode" not in diffs[0].diff_content


def test_render_org_commit_diff_levels(tmp_path):
    """One render covers the levels: * commit, ** file with its full diff, *** hunk when extended."""
    repo = _init_repo(tmp_path)
    _commit_all(repo, "subject for render")
    commit_hash = _run_git(repo, "rev-parse", "HEAD").stdout.strip()

    commit = {"repo_path": str(repo), "commit_hash": commit_hash}
    diff_file = GitDiffFile(
        file_path="f.txt", diff_content="full diff body", repo_path=str(repo), additions=2, deletions=1
    )
    hunk = DiffHunk(
        file_path="f.txt",
        repo_path=str(repo),
        hunk_header="@@ -1,2 +1,2 @@",
        old_start=1,
        old_count=2,
        new_start=1,
        new_count=2,
        hunk_content="@@ -1,2 +1,2 @@\n-old\n+new",
        context_before=(),
        removed_lines=("old",),
        added_lines=("new",),
        context_after=(),
        hunk_index=0,
    )

    assert render_org_commit_diff(commit).startswith("* ")
    assert "subject for render" in render_org_commit_diff(commit)
    rendered_file = render_org_commit_diff(diff_file)
    assert rendered_file.startswith("** f.txt ( +2 -1 )")
    assert "#+begin_src diff" in rendered_file  # the file carries the whole diff, no hunk level needed
    assert "full diff body" in rendered_file
    assert "*** f.txt (hunk 0)" in render_org_commit_diff(hunk)
    assert "#+begin_src diff" in render_org_commit_diff(hunk)


def _commit_chain_query(repo: Path, extra_chain: str = "") -> str:
    """Build the commits -> per-commit insert_diff query with an optional tail."""
    return (
        f'git.commits "{repo}" --limit=5, '
        "extend_by_inserter 'git.insert_diff' "
        "'commit_arg=$commit_hash^..$commit_hash' 'directory=$repo_path'"
        f"{extra_chain}, :org-commit-diff"
    )


def test_commits_extended_with_insert_diff_shows_files(make_ctx, tmp_path):
    """commits extended by insert_diff per item renders * commit and ** file levels with full diffs."""
    repo = _init_repo(tmp_path)
    _commit_all(repo, "first subject")
    (repo / "file.txt").write_text("changed content\n")
    assert _run_git(repo, "add", "file.txt").returncode == 0
    assert _run_git(repo, "commit", "-m", "second subject").returncode == 0

    ctx = make_ctx(plugins_git, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    _forest, _attrs, _render_specs, out = qp.execute_query(_commit_chain_query(repo))

    assert ":: first subject" in out
    assert ":: second subject" in out
    assert out.count("** file.txt") == 2  # both commits changed file.txt (root commit included)
    assert out.count("#+begin_src diff") == 2  # each file section carries its full diff
    assert "+changed content" in out
    assert "***" not in out  # no hunk level: insert_diff already yields the whole diff per file


def test_commits_files_hunks_three_level_chain(make_ctx, tmp_path):
    """Adding extend_diff_hunks --on-depth=1 yields *** hunk blocks under each file."""
    repo = _init_repo(tmp_path)
    _commit_all(repo, "first subject")
    (repo / "file.txt").write_text("changed content\n")
    assert _run_git(repo, "add", "file.txt").returncode == 0
    assert _run_git(repo, "commit", "-m", "second subject").returncode == 0

    ctx = make_ctx(plugins_git, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    _forest, _attrs, _render_specs, out = qp.execute_query(
        _commit_chain_query(repo, ", extend_diff_hunks --on-depth=1")
    )

    assert "*** file.txt (hunk 0)" in out
    assert "#+begin_src diff" in out
