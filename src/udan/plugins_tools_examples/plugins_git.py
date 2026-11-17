"""Git plugin for udan.

Provides inserters, extenders, attributes and renders for working with git
repositories through the `git` CLI: commits, diffs, status, untracked files
and the org-diff render family.
"""

import os
import re
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict

from udan.core.api_forests import Item
from udan.core_tools_loading.api_annotated import annotated


def _run_git_command(
    cmd: list[str], cwd: Path, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run a git command with explicit environment to avoid repository detection issues.

    During pre-commit hooks, subprocess.run can inherit environment variables
    that cause git to detect the main repository instead of the target directory.
    This function explicitly sets GIT_DIR and GIT_WORK_TREE to ensure
    git commands only see the specified directory.

    Args:
        cmd: Git command to run (without 'git' prefix)
        cwd: Directory to run the command in

    Returns:
        CompletedProcess with command result
    """
    env = os.environ.copy()
    env["GIT_DIR"] = str(cwd / ".git")
    env["GIT_WORK_TREE"] = str(cwd)
    env.pop("GIT_ALTERNATE_OBJECT_DIRECTORIES", None)
    env.pop("GIT_OBJECT_DIRECTORY", None)
    env.pop("GIT_INDEX_FILE", None)
    if extra_env:
        env.update(extra_env)

    full_cmd = ["git"] + cmd
    return subprocess.run(
        full_cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
    )


DOMAIN = "git"

# Git status parsing constants
_GIT_STATUS_MIN_LENGTH = 3  # Minimum length for a valid git status line
_GIT_STATUS_CODES_LENGTH = 2  # Length of status codes (XY)
_GIT_STATUS_SEPARATOR_POSITION = 3  # Position where separator space might be

# Git log format parsing
_GIT_LOG_FORMAT_PARTS = 6  # Expected parts in "commit|tree|parent|author|date" format

# Git diff numstat parsing
_NUMSTAT_MIN_PARTS = 2  # Minimum parts in numstat output (additions, deletions)


class GitStatus(TypedDict):
    """TypedDict for git status entries.

    Returned by insert_status, contains status code and file path.
    """

    status: str
    path: str


class CommitInfo(TypedDict):
    """TypedDict for commit information.

    Returned by commits inserter, contains repository path and commit hash.
    """

    repo_path: str
    commit_hash: str


@dataclass
class GitDiffFile:
    """Represents a git diff for a single file."""

    file_path: str
    diff_content: str
    repo_path: str = ""  # Track repo root for path resolution
    additions: int = 0  # Number of lines added
    deletions: int = 0  # Number of lines deleted
    words: bool = False  # Diff content uses word-level markers (--word-diff)


@dataclass(frozen=True)
class DiffHunk:
    """Represents a single hunk within a git diff."""

    file_path: str  # Relative to repo root
    repo_path: str  # Absolute path to repo root
    hunk_header: str  # e.g., "@@ -1,3 +1,4 @@"
    old_start: int  # Old file start line
    old_count: int  # Old file line count
    new_start: int  # New file start line
    new_count: int  # New file line count
    hunk_content: str  # Full hunk content including header
    context_before: tuple[str, ...]  # Context lines before changes (tuple for hashability)
    removed_lines: tuple[str, ...]  # Lines starting with - (tuple for hashability)
    added_lines: tuple[str, ...]  # Lines starting with + (tuple for hashability)
    context_after: tuple[str, ...]  # Context lines after changes (tuple for hashability)
    hunk_index: int = 0  # Index of hunk within the file
    node_id: str = ""  # Unique identifier for matching edited items
    words: bool = False  # Hunk content uses word-level markers (--word-diff)


@dataclass
class GitCommit:
    """Represents a git commit."""

    hash: str
    short_hash: str
    author: str
    date: str
    message: str
    body: str


# The empty tree object: diffing a root commit means diffing against it, since a
# root commit has no parent ref ({ref}^ fails) and diff-tree hides its files
# without --root
_EMPTY_TREE_SHA1 = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def _is_root_commit(ref: str, path: Path) -> bool:
    """Check whether ref names a valid commit that has no parent.

    Args:
        ref: Git revision
        path: Path to git repository

    Returns:
        True when the ref resolves to a commit without a parent (the initial commit)
    """
    commit_result = _run_git_command(["rev-parse", "--verify", "--quiet", ref], path)
    if commit_result.returncode != 0:
        return False
    return _run_git_command(["rev-parse", "--verify", "--quiet", f"{ref}^"], path).returncode != 0


def _root_aware_commit_arg(commit_arg: str, path: Path, staged: bool = False) -> str:
    """Rewrite the per-commit range form so a root commit diffs against the empty tree.

    The range {ref}^..{ref} describes one commit's changes, but a root commit has
    no parent ref: its base does not resolve and the range shows nothing. When the
    base names a parentless commit, the range is rewritten to diff the commit from
    the empty tree object. Single-ref and staged forms mean "working tree vs base",
    so they pass through untouched.

    Args:
        commit_arg: Git revision or range as given by the caller
        path: Path to git repository
        staged: When True the commit_arg is a base for --staged diffing, not a
            commit to describe, so it passes through untouched

    Returns:
        commit_arg, or "{empty tree}..{ref}" when the range describes a root commit
    """
    if staged or commit_arg.count("..") != 1:
        return commit_arg

    base, _, tip = commit_arg.partition("..")
    # {h}^..{h} is the per-commit form: its base names the commit's parent,
    # which does not resolve exactly when {h} is a root commit
    if not base.endswith("^"):
        return commit_arg

    described = base[:-1]
    if _is_root_commit(described, path):
        empty_result = _run_git_command(["rev-parse", "--verify", "--quiet", _EMPTY_TREE_SHA1], path)
        if empty_result.returncode == 0:
            return f"{_EMPTY_TREE_SHA1}..{tip}"
    return commit_arg


def _build_diff_cmd(*extra: str, commit_arg: str = "HEAD", staged: bool = False, words: bool = False) -> list[str]:
    """Build a git diff command with common flags.

    Args:
        *extra: Additional arguments before the file separator
        commit_arg: Git revision or range
        staged: If True, include --staged flag
        words: If True, include --word-diff flag (inline word-level change markers)

    Returns:
        Complete git diff command as a list of strings
    """
    cmd = ["diff"]
    cmd.extend(extra)
    if staged:
        cmd.append("--staged")
    if words:
        cmd.append("--word-diff")
    cmd.append(commit_arg)
    return cmd


def _get_changed_files(commit_arg: str, path: Path, staged: bool = False, file_path: str = "") -> list[str]:
    """Get list of changed files for a git diff.

    Args:
        commit_arg: Git revision or range
        path: Path to git repository
        staged: If True, use --staged flag
        file_path: Optional pathspec limiting the diff to a single file

    Returns:
        List of changed file paths
    """
    cmd = _build_diff_cmd("--name-only", commit_arg=commit_arg, staged=staged)
    if file_path:
        cmd.extend(["--", file_path])

    result = _run_git_command(cmd, path)

    if result.returncode != 0:
        return []

    return [line for line in result.stdout.splitlines() if line.strip()]


def _parse_numstat(numstat_output: str) -> tuple[int, int]:
    """Parse git diff --numstat output to get additions and deletions.

    Args:
        numstat_output: Output from git diff --numstat

    Returns:
        (additions, deletions) tuple
    """
    lines = numstat_output.splitlines()
    numstat_lines = [line for line in lines if "\t" in line]

    if not numstat_lines:
        return (0, 0)

    parts = numstat_lines[0].split("\t")
    if len(parts) < _NUMSTAT_MIN_PARTS:
        return (0, 0)

    additions = 0
    deletions = 0

    try:
        if parts[0] != "-":
            additions = int(parts[0])
        if parts[1] != "-":
            deletions = int(parts[1])
    except ValueError:
        pass

    return (additions, deletions)


def _get_file_diff(
    commit_arg: str, path: Path, file_path: str, staged: bool = False, words: bool = False
) -> tuple[str, int, int] | None:
    """Get diff content and stats for a single file.

    Args:
        commit_arg: Git revision or range
        path: Path to git repository
        file_path: Path to the file to diff
        staged: If True, use --staged flag
        words: If True, use --word-diff for the diff content (stats stay line-based)

    Returns:
        (diff_content, additions, deletions) tuple or None if diff failed
    """
    # Build commands
    numstat_cmd = _build_diff_cmd("--numstat", commit_arg=commit_arg, staged=staged) + ["--", file_path]
    diff_cmd = _build_diff_cmd(commit_arg=commit_arg, staged=staged, words=words) + ["--", file_path]

    # Get numstat for stats
    result = _run_git_command(numstat_cmd, path)

    if result.returncode != 0:
        return None

    additions, deletions = _parse_numstat(result.stdout)

    # Get actual diff content
    result = _run_git_command(diff_cmd, path)

    if result.returncode != 0:
        return None

    diff_content = result.stdout.strip()
    if not diff_content:
        return None

    return (diff_content, additions, deletions)


@annotated(meta={"tool_type": "inserter", "supported_renders": ["org-diff"], "output_type": "GitDiffFile"})
def insert_diff(
    commit_arg: str = "HEAD", directory: str = "", staged: bool = False, words: bool = False, file: str = ""
) -> Iterable[GitDiffFile]:
    """Insert git diffs for modified files in a directory.

    Args:
        commit_arg: Git revision or range (default: "HEAD"). Examples: "HEAD~1", "HEAD~5..HEAD", "main".
                    The per-commit range form "{hash}^..{hash}" shows the root commit's files too
                    (diffed against the empty tree)
        directory: Path to git repository (default: udan repository root)
        staged: If True, show staged changes (git diff --staged <commit_arg>) instead of working tree vs commit_arg
        words: If True, use word-level diff (git diff --word-diff); additions/deletions stats stay line-based
        file: Path of a file to show the diff for (git pathspec). When empty, all changed files are shown

    Returns:
        Iterable of GitDiffFile objects containing file paths, diffs, and stats
    """
    if not directory:
        path = Path.cwd()
    else:
        path = Path(directory).expanduser().resolve()

    result = _run_git_command(["rev-parse", "--git-dir"], path)
    if result.returncode != 0:
        return iter([])

    commit_arg = _root_aware_commit_arg(commit_arg, path, staged=staged)
    changed_files = _get_changed_files(commit_arg, path, staged=staged, file_path=file)

    for file_path in changed_files:
        diff_result = _get_file_diff(commit_arg, path, file_path, staged=staged, words=words)
        if diff_result is None:
            continue

        diff_content, additions, deletions = diff_result
        yield GitDiffFile(
            file_path=file_path,
            diff_content=diff_content,
            repo_path=str(path),
            additions=additions,
            deletions=deletions,
            words=words,
        )


@annotated(
    meta={
        "tool_type": "inserter",
        "supported_renders": ["status-full", "status-path"],
        "output_type": "GitStatus",
    }
)
def insert_status(directory: str = "", modified: bool | None = None) -> Iterable[GitStatus]:
    """Insert git status for a directory as dictionaries.

    Args:
        directory: Path to git repository (default: udan repository root)
        modified: If True, show only modified files (containing 'M' in status).
                  If False or None, show all files.

    Returns:
        Iterable of dictionaries with {status: str, path: str}
        Status codes: ?? (untracked), M (modified), A (added), D (deleted), etc.
    """
    # If no directory specified, use current directory
    # Check explicitly for empty string, not just falsy value
    if directory == "":
        path = Path.cwd()
    else:
        path = Path(directory).expanduser().resolve()  # Use resolve() to get absolute path

    # Check if we're in a git repository
    result = _run_git_command(["rev-parse", "--git-dir"], path)
    if result.returncode != 0:
        return []

    # Get git status
    result = _run_git_command(["status", "--short"], path)

    if result.returncode != 0:
        return []

    status_lines = result.stdout.strip().split("\n")
    result_list: list[GitStatus] = []

    for line in status_lines:
        if not line:
            continue

        # Parse status line: XY filename or XYfilename
        # X = staged status (position 0)
        # Y = unstaged status (position 1)
        # Separator space is at position 2 if present (most common case)
        # But for files like ".gitignore" with status "M ", format is "M .gitignore" (no separator space)
        # Don't strip the line as it removes significant leading spaces in status codes
        if len(line) >= _GIT_STATUS_MIN_LENGTH:
            status = line[0] + line[1]  # First two characters are status codes

            # Check if position 2 is a separator space (most common case)
            # Position 2 is a separator if: it's a space AND position 3 exists AND is not a space
            # This distinguishes "MM  file" (separator) from "M .gitignore" (no separator, dotfile)
            if line[_GIT_STATUS_CODES_LENGTH] == " " and (
                len(line) < _GIT_STATUS_SEPARATOR_POSITION + 1 or line[_GIT_STATUS_SEPARATOR_POSITION] != " "
            ):
                # Format: "XY filename" with separator space at position 2
                file_path = line[_GIT_STATUS_SEPARATOR_POSITION:]  # Skip "XY " (3 characters)
            else:
                # Format: "XYfilename" without separator space
                # This happens when position 1 is a space (e.g., "M " for staged modified)
                # and position 2 is the filename itself (e.g., "M .gitignore")
                file_path = line[_GIT_STATUS_CODES_LENGTH:]  # Skip "XY" (2 characters)

            # Apply modified filter if requested
            if modified is True:
                # Show only files that have M in status (either position)
                if "M" not in status:
                    continue

            result_list.append({"status": status, "path": file_path})

    return result_list


# ============================================================================
# Diff hunk parsing and extension
# ============================================================================


def _parse_hunk_header(header: str) -> tuple[int, int, int, int] | None:
    """Parse git diff hunk header.

    Args:
        header: Hunk header line like "@@ -1,3 +1,4 @@ function"

    Returns:
        (old_start, old_count, new_start, new_count) or None
    """
    # Pattern: @@ -old_start,old_count +new_start,new_count @@
    match = re.match(r"@@\s*-(\d+)(?:,(\d+))?\s*\+(\d+)(?:,(\d+))?\s*@@", header)
    if match:
        old_start = int(match.group(1))
        old_count = int(match.group(2)) if match.group(2) else 1
        new_start = int(match.group(3))
        new_count = int(match.group(4)) if match.group(4) else 1
        return (old_start, old_count, new_start, new_count)
    return None


@annotated(meta={"tool_type": "extender", "item_type": "GitDiffFile", "output_type": "DiffHunk"})
def extend_diff_hunks(item: GitDiffFile) -> Iterable[DiffHunk]:
    """Extend a GitDiffFile object with individual hunks.

    Args:
        item: GitDiffFile object to extract hunks from

    Yields:
        DiffHunk objects, one per hunk in the diff
    """
    if not isinstance(item, GitDiffFile):
        return

    lines = item.diff_content.splitlines()
    i = 0
    hunk_index = 0

    while i < len(lines):
        line = lines[i]

        # Look for hunk header
        if line.startswith("@@"):
            header_info = _parse_hunk_header(line)
            if not header_info:
                i += 1
                continue

            old_start, old_count, new_start, new_count = header_info

            # Collect hunk content
            hunk_lines = [line]
            context_before = []
            removed_lines = []
            added_lines = []
            context_after = []

            i += 1
            in_hunk = True

            while i < len(lines) and in_hunk:
                hunk_line = lines[i]

                # End of hunk (next hunk or end of diff)
                is_end = (
                    hunk_line.startswith("@@")
                    or hunk_line.startswith("diff")
                    or hunk_line.startswith("---")
                    or hunk_line.startswith("+++")
                )
                if is_end:
                    in_hunk = False
                    break

                hunk_lines.append(hunk_line)

                # Parse hunk content
                if hunk_line.startswith("-"):
                    removed_lines.append(hunk_line[1:])
                elif hunk_line.startswith("+"):
                    added_lines.append(hunk_line[1:])
                elif hunk_line.startswith(" "):
                    # Context line
                    if not removed_lines and not added_lines:
                        context_before.append(hunk_line[1:])
                    else:
                        context_after.append(hunk_line[1:])

                i += 1

            hunk_content = "\n".join(hunk_lines)

            # Create node_id for matching edited items
            node_id = f"{item.file_path}::hunk:{hunk_index}"

            yield DiffHunk(
                file_path=item.file_path,
                repo_path=item.repo_path,
                hunk_header=line,
                old_start=old_start,
                old_count=old_count,
                new_start=new_start,
                new_count=new_count,
                hunk_content=hunk_content,
                context_before=tuple(context_before),
                removed_lines=tuple(removed_lines),
                added_lines=tuple(added_lines),
                context_after=tuple(context_after),
                hunk_index=hunk_index,
                node_id=node_id,
                words=item.words,
            )
            hunk_index += 1
        else:
            i += 1


@annotated(meta={"attribute_type": "simple"})
def git_diff_file_size(item: GitDiffFile) -> int:
    """Return the change size of a git diff (additions + deletions).

    Args:
        item: GitDiffFile object

    Returns:
        Total number of changed lines, 0 for non-GitDiffFile items
    """
    if not isinstance(item, GitDiffFile):
        return 0

    return item.additions + item.deletions


@annotated(
    meta={
        "tool_type": "inserter",
        "output_type": "CommitInfo",
        "supported_renders": ["commit-log"],
        "aliases": ["log"],
    }
)
def commits(directory: str = "", limit: int = 10) -> Iterable[CommitInfo]:
    """Insert git commits from repository history.

    Args:
        directory: Path to git repository (default: current directory)
        limit: Maximum number of commits to return (default: 10)

    Returns:
        Iterable of dictionaries with {repo_path: str, commit_hash: str}
    """
    # If no directory specified, use current directory
    if not directory:
        path = Path.cwd()
    else:
        path = Path(directory).expanduser()

    # Check if we're in a git repository
    result = _run_git_command(["rev-parse", "--git-dir"], path)
    if result.returncode != 0:
        return iter([])

    # Get commit log with formatted output
    # Format: %H full hash, %h short hash, %an author name, %ad date, %s subject, %b body
    result = _run_git_command(["log", f"-{limit}", "--format=%H|%h|%an|%ad|%s|%b", "--date=short"], path)

    if result.returncode != 0:
        return iter([])

    # Parse commit data
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue

        parts = line.split("|", 5)
        if len(parts) == _GIT_LOG_FORMAT_PARTS:
            full_hash = parts[0]
            yield {"repo_path": str(path), "commit_hash": full_hash}


@annotated(meta={"tool_type": "extender", "item_type": "CommitInfo", "output_type": "str"})
def extend_commit_files(item: GitCommit | dict | str) -> Iterable[str]:
    """Extend a commit with its changed files.

    Args:
        item: GitCommit object, commit dict with commit_hash, commit hash string,
              or {commit_hash}:{fpath} format

    Yields:
        File paths changed in the commit (optionally filtered by fpath)
    """
    # Get commit hash and optional filter path
    if isinstance(item, GitCommit):
        commit_hash = item.hash
        filter_path = None
        repo_path = None
    elif isinstance(item, dict):
        commit_hash = item.get("commit_hash", "")
        repo_path = item.get("repo_path")
        filter_path = None
    elif isinstance(item, str):
        # Check if it's in {commit_hash}:{fpath} format
        if ":" in item:
            commit_hash, filter_path = item.split(":", 1)
        else:
            commit_hash = item
            filter_path = None
        repo_path = None
    else:
        return

    # Determine the directory for git commands
    if repo_path:
        path = Path(repo_path)
    else:
        path = Path.cwd()

    # Get list of files changed in the commit
    result = _run_git_command(["diff-tree", "--no-commit-id", "--name-only", "-r", commit_hash], path)

    if result.returncode != 0:
        return

    # Yield each file path, optionally filtered
    for file_path in result.stdout.strip().split("\n"):
        if file_path:  # Skip empty lines
            # Apply filter if specified
            if filter_path:
                # Check if file path starts with filter_path
                # Normalize paths to handle leading/trailing slashes
                normalized_filter = filter_path.strip("/")
                normalized_file = file_path.strip("/")
                if normalized_file.startswith(normalized_filter + "/") or normalized_file == normalized_filter:
                    yield file_path
            else:
                yield file_path


@annotated(meta={"attribute_type": "simple"})
def commit_message(item: dict[str, Any] | GitCommit | str) -> str:
    """Get commit message for a commit.

    Args:
        item: Commit dict with commit_hash, GitCommit object, or commit hash string

    Returns:
        Commit message subject line, or empty string if not found
    """
    commit_hash, repo_path = _extract_commit_ref(item)

    if not commit_hash:
        return ""

    # Determine the directory for git commands
    if repo_path:
        path = Path(repo_path)
    else:
        path = Path.cwd()

    # Get commit message subject
    result = _run_git_command(["log", "-1", "--format=%s", commit_hash], path)

    if result.returncode != 0:
        return ""

    return result.stdout.strip()


@annotated(meta={"attribute_type": "simple"})
def push_status(item: dict[str, Any] | GitCommit | str) -> str:
    """Check if commit has been pushed to remote.

    Args:
        item: Commit dict with commit_hash, GitCommit object, or commit hash string

    Returns:
        "UNPUSHED" if commit is not in any remote branch, "" if pushed or invalid
    """
    # Extract commit hash
    commit_hash, repo_path = _extract_commit_ref(item)

    if not commit_hash:
        return ""

    # Determine the directory for git commands
    if repo_path:
        path = Path(repo_path)
    else:
        path = Path.cwd()

    # First verify it's a valid commit hash
    verify_result = _run_git_command(["rev-parse", "--verify", commit_hash + "^{commit}"], path)

    if verify_result.returncode != 0:
        # Not a valid commit hash
        return ""

    # Check if commit exists in any remote branch
    result = _run_git_command(["branch", "-r", "--contains", commit_hash], path)

    if result.returncode != 0:
        # If command fails, assume unpushed
        return "UNPUSHED"

    # If any remote branches contain the commit, it's pushed
    if result.stdout.strip():
        return ""
    else:
        return "UNPUSHED"


# Git commit log format parsing
_GIT_COMMIT_INFO_PARTS = 4  # Expected parts in "short hash|timestamp|subject|body" format
_GIT_COMMIT_INFO_FORMAT = "%h|%at|%s|%b"  # Short hash, unix timestamp, subject, body
_COMMIT_DATE_FORMAT = "%Y-%m-%d--%H-%M"  # Date prefix format for commit-log render
_MESSAGE_CONTINUATION = " ..."  # Marks a commit message with more lines than the subject
_UNPUSHED_SUFFIX = " / UNPUSHED"  # Marks a commit that is missing from remote branches

_DIFF_SRC_LANG = "diff"  # Org src block language for line-based diffs
_WDIFF_SRC_LANG = "wdiff"  # Org src block language for word-level diffs (--word-diff)


def _diff_src_lang(words: bool) -> str:
    """Return the org src block language for a diff.

    Args:
        words: Whether the diff content uses word-level markers (--word-diff)

    Returns:
        "wdiff" for word-level diffs, "diff" otherwise
    """
    return _WDIFF_SRC_LANG if words else _DIFF_SRC_LANG


def _extract_commit_ref(item: Item) -> tuple[str, Path | None]:
    """Extract commit hash and repository path from a commit item.

    Args:
        item: Commit dict with {commit_hash, repo_path}, GitCommit object, or commit hash string

    Returns:
        (commit_hash, repo_path) tuple, where repo_path is None when not known
    """
    if isinstance(item, dict):
        return (item.get("commit_hash", ""), item.get("repo_path"))
    if isinstance(item, GitCommit):
        return (item.hash, None)
    if isinstance(item, str):
        return (item, None)
    return ("", None)


def _get_commit_info(repo_path: Path, commit_hash: str) -> dict[str, str] | None:
    """Get display info for a single commit.

    Args:
        repo_path: Path to the git repository
        commit_hash: Commit hash (full or abbreviated)

    Returns:
        Dict with {short_hash, date, subject, body}, or None if the commit was not found
    """
    result = _run_git_command(["log", "-1", f"--format={_GIT_COMMIT_INFO_FORMAT}", commit_hash], repo_path)

    if result.returncode != 0:
        return None

    parts = result.stdout.strip("\n").split("|", 3)
    if len(parts) != _GIT_COMMIT_INFO_PARTS:
        return None

    try:
        date = datetime.fromtimestamp(int(parts[1])).strftime(_COMMIT_DATE_FORMAT)
    except ValueError:
        return None

    return {"short_hash": parts[0], "date": date, "subject": parts[2], "body": parts[3]}


@annotated(meta={"item_type": "dict", "item_semantic": "CommitInfo", "tool_type": "render", "aliases": ["commit-log"]})
def render_commit_log(item: dict, indent: str = "") -> str:
    """Render a commit as a single log line.

    Format: "<date> <short hash> :: <message>". When the commit message has more
    lines than the subject, " ..." is appended. When the commit is not present in
    any remote branch, " / UNPUSHED" is appended.

    Args:
        item: Commit dict with {repo_path, commit_hash}
        indent: Indentation string

    Returns:
        Formatted commit log line
    """
    if isinstance(item, dict) and item.get("commit_hash"):
        repo_path = Path(item.get("repo_path") or Path.cwd())
        info = _get_commit_info(repo_path, item["commit_hash"])

        if info is not None:
            message = info["subject"]
            if info["body"].strip():
                message += _MESSAGE_CONTINUATION

            line = f"{indent}{info['date']} {info['short_hash']} :: {message}"
            if push_status(item) == "UNPUSHED":
                line += _UNPUSHED_SUFFIX
            return line

    return f"{indent}{str(item)}"


@annotated(meta={"item_type": "GitDiffFile|str", "tool_type": "render", "aliases": ["org-stash-diff"]})
def render_org_stash_diff(item: GitDiffFile | str, indent: str = "") -> str:
    """Render stash list with GitDiffFile children in org-mode format.

    Stash names get `* ` prefix, GitDiffFile children get `** ` prefix
    with diff content in source blocks.

    Args:
        item: GitDiffFile object or stash name string
        indent: Indentation string (ignored -- org headings manage their own prefix)

    Returns:
        Formatted org-mode string
    """
    _ = indent  # org-style headings manage their own prefix
    if isinstance(item, GitDiffFile):
        stats = f" ( +{item.additions} -{item.deletions} )" if item.additions or item.deletions else ""
        lines = [
            f"** {item.file_path}{stats}",
            "#+begin_src diff",
            item.diff_content,
            "#+end_src",
        ]
        return "\n".join(lines)
    if isinstance(item, str):
        return f"* {item}"
    return f"- {str(item)}"


@annotated(meta={"item_type": "GitDiffFile", "tool_type": "render", "aliases": ["org-diff"]})
def render_org_diff(item: GitDiffFile, indent: str = "") -> str:
    """Render GitDiffFile in org-mode format with source block.

    Args:
        item: GitDiffFile object to render
        indent: Indentation string

    Returns:
        Formatted org-mode string with file name (with stats) and diff in source block
    """
    if isinstance(item, GitDiffFile):
        # Format: ** file.py ( + additions - deletions )
        stats = f" ( +{item.additions} -{item.deletions} )" if item.additions or item.deletions else ""
        lines = [
            f"{indent}** {item.file_path}{stats}",
            f"{indent}#+begin_src {_diff_src_lang(item.words)}",
            f"{indent}{item.diff_content}",
            f"{indent}#+end_src",
        ]
        return "\n".join(lines)
    return f"{indent}- {str(item)}"


@annotated(
    meta={
        "item_type": "GitDiffFile|DiffHunk",
        "item_semantic": "DiffHunk",
        "tool_type": "render",
        "aliases": ["org-diff-hunk"],
    }
)
def render_org_diff_hunk(item: GitDiffFile | DiffHunk, indent: str = "") -> str:
    """Render DiffHunk in org-mode format.

    Args:
        item: DiffHunk or GitDiffFile object to render
        indent: Indentation string

    Returns:
        Formatted org-mode string with file path, hunk info, and editable content
        For GitDiffFile items, returns empty string (they will be extended to hunks)
    """
    if isinstance(item, GitDiffFile):
        # GitDiffFile items are extended to DiffHunk items, don't render them directly
        return ""
    if isinstance(item, DiffHunk):
        lines = [
            f"{indent}*** {item.file_path} (hunk {item.hunk_index})",
            f"{indent}:PROPERTIES:",
            f"{indent}:path: {item.file_path}",
            f"{indent}:repo_path: {item.repo_path}",
            f"{indent}:hunk_index: {item.hunk_index}",
            f"{indent}:old_start: {item.old_start}",
            f"{indent}:new_start: {item.new_start}",
            f"{indent}:END:",
            f"{indent}#+begin_src {_diff_src_lang(item.words)}",
        ]
        # Add hunk content line by line WITHOUT indent (src block content should not be indented)
        for line in item.hunk_content.splitlines():
            lines.append(line)
        lines.append(f"{indent}#+end_src")
        return "\n".join(lines)
    return f"{indent}- {str(item)}"


@annotated(
    meta={
        "item_type": "dict|GitDiffFile|DiffHunk",
        "item_semantic": "CommitInfo",
        "tool_type": "render",
        "aliases": ["org-commit-diff"],
    }
)
def render_org_commit_diff(item: dict | GitDiffFile | DiffHunk, indent: str = "") -> str:
    """Render the commits -> files structure in org-mode format.

    One render for both levels: the commit as a level-1 heading (its commit-log
    line) and the file as a level-2 heading with change stats followed by the
    full per-commit diff in a source block -- what
    `git diff {hash}^..{hash} -- {file}` prints. GitDiffFile already carries the
    whole diff, so no hunk level is needed for the view; hunks appear only when
    extend_diff_hunks is added to the chain explicitly, each as its own heading.

    Args:
        item: Commit dict with {repo_path, commit_hash}, GitDiffFile, or DiffHunk
        indent: Indentation string (ignored -- org headings manage their own prefix)

    Returns:
        Formatted org-mode string for the item
    """
    _ = indent  # org-style headings manage their own prefix
    if isinstance(item, DiffHunk):
        return render_org_diff_hunk(item, indent)
    if isinstance(item, GitDiffFile):
        return render_org_diff(item)
    if isinstance(item, dict) and item.get("commit_hash"):
        return f"* {render_commit_log(item)}"
    return f"- {str(item)}"


@annotated(meta={"item_type": "dict", "item_semantic": "GitStatus", "tool_type": "render", "aliases": ["status-path"]})
def render_status_path(item: dict, indent: str = "") -> str:
    """Render git status item showing just the file path.

    Args:
        item: Git status dict with {status: str, path: str}
        indent: Indentation string

    Returns:
        Formatted string showing just the file path
    """
    if isinstance(item, dict) and "path" in item:
        return f"{indent}{item['path']}"
    return f"{indent}{str(item)}"


@annotated(meta={"item_type": "dict", "item_semantic": "GitStatus", "tool_type": "render", "aliases": ["status-full"]})
def render_status_full(item: dict, indent: str = "") -> str:
    """Render git status item showing both status and path.

    Args:
        item: Git status dict with {status: str, path: str}
        indent: Indentation string

    Returns:
        Formatted string showing status and path
    """
    if isinstance(item, dict) and "status" in item and "path" in item:
        return f"{indent}{item['status']} {item['path']}"
    return f"{indent}{str(item)}"


def _get_untracked_files(repo_path: str | Path) -> list[Path]:
    """Get list of untracked files in a git repository.

    Args:
        repo_path: Path to the git repository

    Returns:
        List of Path objects for untracked files (not including ignored files)
    """
    path = Path(repo_path).expanduser().resolve()

    # Set up environment to ensure git runs in the specified directory only
    env = os.environ.copy()
    env["GIT_DIR"] = str(path / ".git")
    env["GIT_WORK_TREE"] = str(path)
    env.pop("GIT_ALTERNATE_OBJECT_DIRECTORIES", None)
    env.pop("GIT_OBJECT_DIRECTORY", None)
    env.pop("GIT_INDEX_FILE", None)

    # Check if we're in a git repository
    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=path,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []

    # Get untracked files using git ls-files
    # --others: show untracked files
    # --exclude-standard: respect .gitignore and other exclusion files
    result = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=path,
        env=env,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return []

    untracked_files = []
    for line in result.stdout.strip().split("\n"):
        if line:
            untracked_files.append(path / line)

    return untracked_files


@annotated(meta={"tool_type": "inserter", "output_type": "str"})
def git_repos(directory: str = ".") -> Iterable[str]:
    """Insert all git repositories found within a directory.

    A git repository is identified as a directory containing a '.git' subdirectory.
    Searches recursively through all subdirectories.

    Args:
        directory: Root directory to search for git repositories (default: current directory)

    Yields:
        Paths to directories containing git repositories
    """
    root_path = Path(directory).expanduser().resolve()

    if not root_path.exists() or not root_path.is_dir():
        return

    # Walk through directory tree
    for root, dirs, _ in os.walk(str(root_path)):
        root_path = Path(root)
        git_dir = root_path / ".git"

        # Check if this directory contains a .git subdirectory
        if git_dir.exists() and git_dir.is_dir():
            yield str(root_path)

            # Don't traverse into nested repos (optional, but usually desired)
            # Remove subdirectories from the walk to avoid descending into nested repos
            dirs[:]


@annotated(meta={"tool_type": "extender", "item_type": "any", "output_type": "str"})
def untracked(item: dict | str | Path) -> Iterable[str]:
    """Extend a git repository with its untracked files.

    Args:
        item: Path to a git repository (str or Path), or an item with repo_path

    Yields:
        Paths to untracked files in the repository
    """
    # Extract repo path
    if isinstance(item, dict) and "repo_path" in item:
        repo_path = item["repo_path"]
    elif isinstance(item, (str, Path)):
        repo_path = item
    else:
        return

    untracked_files = _get_untracked_files(repo_path)
    for file_path in untracked_files:
        yield str(file_path)


@annotated(meta={"attribute_type": "simple"})
def untracked_count(item: dict | str | Path) -> int:
    """Return the count of untracked files in a git repository.

    Args:
        item: Path to a git repository (str or Path), or an item with repo_path

    Returns:
        Number of untracked files in the repository
    """
    # Extract repo path
    if isinstance(item, dict) and "repo_path" in item:
        repo_path = item["repo_path"]
    elif isinstance(item, (str, Path)):
        repo_path = item
    else:
        return 0

    untracked_files = _get_untracked_files(repo_path)
    return len(untracked_files)


@annotated(meta={"attribute_type": "simple"})
def untracked_size(item: dict | str | Path) -> int:
    """Return the total size of untracked files in a git repository.

    Args:
        item: Path to a git repository (str or Path), or an item with repo_path

    Returns:
        Total size in bytes of all untracked files in the repository
    """
    # Extract repo path
    if isinstance(item, dict) and "repo_path" in item:
        repo_path = item["repo_path"]
    elif isinstance(item, (str, Path)):
        repo_path = item
    else:
        return 0

    untracked_files = _get_untracked_files(repo_path)
    total_size = 0

    for file_path in untracked_files:
        try:
            if file_path.is_file():
                total_size += file_path.stat().st_size
        except OSError, FileNotFoundError:
            # Skip files that can't be accessed
            continue

    return total_size


# ============================================================================
# Git stash operations
# ============================================================================


def _parse_stash_ref(stash_line: str) -> str | None:
    """Extract stash reference (e.g. 'stash@{0}') from a stash list line.

    Args:
        stash_line: Line from 'git stash list', e.g. 'stash@{0}: WIP on dev: ...'

    Returns:
        Stash reference string, or None if the line doesn't match
    """
    match = re.match(r"(stash@\{\d+\})", stash_line)
    return match.group(1) if match else None


@annotated(meta={"tool_type": "inserter", "output_type": "str", "supported_renders": ["org-stash-diff"]})
def insert_stash_list(directory: str = "") -> list[str]:
    """Insert list of git stash entries.

    Args:
        directory: Path to git repository (default: current directory)

    Returns:
        List of stash entries from 'git stash list'
    """
    path = Path(directory).expanduser().resolve() if directory else Path.cwd()

    result = _run_git_command(["stash", "list"], path)
    if result.returncode != 0:
        return []

    return [line for line in result.stdout.splitlines() if line.strip()]


@annotated(
    meta={
        "tool_type": "extender",
        "item_type": "str",
        "output_type": "GitDiffFile",
        "supported_renders": ["org-stash-diff"],
    }
)
def extend_stash_show(item: str) -> Iterable[GitDiffFile]:
    """Extend a stash list entry with full file diffs.

    Each line from git stash list is extended with GitDiffFile objects
    for each changed file in that stash. Uses the range ``stash@{N}^..stash@{N}``
    to diff between the stash's base commit and the stash itself.

    Args:
        item: A stash line from git stash list (e.g. 'stash@{0}: WIP on dev: ...')

    Yields:
        GitDiffFile objects for each file changed in the stash
    """
    if not isinstance(item, str):
        return

    stash_ref = _parse_stash_ref(item)
    if not stash_ref:
        return

    commit_arg = f"{stash_ref}^..{stash_ref}"
    path = Path.cwd()

    for file_path in _get_changed_files(commit_arg, path):
        diff_result = _get_file_diff(commit_arg, path, file_path)
        if diff_result is None:
            continue
        diff_content, additions, deletions = diff_result
        yield GitDiffFile(
            file_path=file_path,
            diff_content=diff_content,
            repo_path=str(path),
            additions=additions,
            deletions=deletions,
        )


# ============================================================================
# Diff hunk content
# ============================================================================


@annotated(meta={"attribute_type": "simple"})
def hunk_content(item: DiffHunk) -> str:
    """Get the hunk content from a DiffHunk.

    Args:
        item: DiffHunk object

    Returns:
        The hunk content (diff text)
    """
    return item.hunk_content
