"""Filesystem operators: inserters, extenders, filters and attributes.

Reads and renders files, directories, .env entries and file lines.
"""

import os
import re
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Annotated, TypedDict

from udan.core_tools_loading.api_annotated import annotated
from udan.core_tools_loading.api_types import Group

DOMAIN = "fs"

# File size constants for conversion (powers of 2)
_BYTES_PER_KB = 2**10
_BYTES_PER_MB = 2**20
_BYTES_PER_GB = 2**30

ENV_ENTRY_LIST_LEN = 2
"""Length of a parsed .env entry: the entry list is ``[key, value]``."""


class EnvEntryOrComment(TypedDict):
    """Structured entry from .env file."""

    type: str  # "entry" or "comment"
    entry: list[str] | None  # [key, value] for entries, None for comments
    comment: str | None  # comment text for comments, None for entries


@dataclass
class PathGlob:
    """A file with a group attribute indicating which glob pattern matched."""

    path: Path
    glob_group: str

    @property
    def parent(self) -> Path:
        """Return the parent directory of the file."""
        return self.path.parent

    def __fspath__(self) -> str:
        """Allow using the item as a path, e.g. Path(item), open(item) in any tool."""
        return str(self.path)

    def __str__(self) -> str:
        """Return string representation using the path."""
        return str(self.path)

    def __repr__(self) -> str:
        """Return detailed representation for debugging."""
        return f"PathGlob(path={self.path!r}, glob_group={self.glob_group!r})"


@dataclass
class FileLine:
    """Structured line from a file.

    Represents a single line from a file, with the line metadata that
    identifies its origin.
    """

    line_number: int  # 0-based line number
    content: str  # Line content (without trailing newline)

    def __str__(self) -> str:
        return f"{self.line_number} :: {self.content}"


@annotated(meta={"tool_type": "inserter", "aliases": ["ls_files"], "output_type": "Path"})
def insert_ls_files(directory: str = ".", pattern: str = "*") -> Iterable:
    """
    List files in a directory matching a glob pattern.

    Args:
        directory (str): Existing directory path.
        pattern (str): Glob pattern to match files.
    """
    path = Path(directory).expanduser()
    return path.glob(pattern=pattern)


@annotated(meta={"tool_type": "inserter", "output_type": "EnvEntryOrComment"})
def read_env(filepath: str) -> Iterable[EnvEntryOrComment]:
    """
    Read an environment file (.env) and yield structured entries.

    Preserves comments and empty lines in the output.

    Args:
        filepath (str): Path to the .env file.

    Yields:
        EnvEntryOrComment: Structured entries with format:
            - For entries: {"type": "entry", "entry": [key, value], "comment": None}
            - For comments/empty lines: {"type": "comment", "entry": None, "comment": str}
    """
    path = Path(filepath).expanduser()
    if not path.is_file():
        return

    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                stripped = line.strip()
                # Empty line - treat as comment
                if not stripped:
                    yield {"type": "comment", "entry": None, "comment": ""}
                    continue
                # Comment line
                if stripped.startswith("#"):
                    yield {"type": "comment", "entry": None, "comment": stripped}
                    continue
                # Parse KEY=VALUE format
                if "=" in stripped:
                    key, value = stripped.split("=", 1)
                    # Remove quotes if present
                    value = value.strip()
                    if (value.startswith('"') and value.endswith('"')) or (
                        value.startswith("'") and value.endswith("'")
                    ):
                        value = value[1:-1]
                    yield {
                        "type": "entry",
                        "entry": [key.strip(), value],
                        "comment": None,
                    }
    except OSError:
        return


@annotated(meta={"tool_type": "inserter", "output_type": "FileLine", "supported_renders": ["file-line"]})
def read_file(filepath: str) -> Iterable[FileLine]:
    """Read a file and yield structured lines.

    Each line is yielded as a FileLine dataclass with line_number and content.
    Preserves all lines including empty lines. The default render is ``file-line``,
    so a query with no render of its own shows the bare content of the file.

    Args:
        filepath: Path to the file.

    Yields:
        FileLine: Structured lines with 0-based line numbers.
    """
    path = Path(filepath).expanduser()
    if not path.is_file():
        return

    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            for line_number, line in enumerate(f, start=0):
                # Remove trailing newline but preserve other whitespace
                content = line.rstrip("\r\n")
                yield FileLine(line_number=line_number, content=content)
    except OSError:
        return


@annotated(meta={"item_type": "FileLine", "tool_type": "render", "aliases": ["file-line"]})
def render_file_line(item: FileLine, numbers: bool = False, indent: str = "", trim: bool = False) -> str:
    """Render FileLine dataclass as the bare line content.

    With ``numbers`` the 0-based line number comes before the content:
    ``{line_number} :: {content}``. ``numbers`` sits before ``indent`` so a query
    can pass it positionally (``:file-line numbers``), the way :fmt takes its format.

    Args:
        item: A FileLine dataclass with line_number and content.
        numbers: Show the 0-based line number before the content (default: False).
        indent: Indentation string (default: "").
        trim: Strip surrounding whitespace from the content (default: False).

    Returns:
        Formatted string like "hello world" or, with numbers, "0 :: hello world".
    """
    if isinstance(item, FileLine):
        content = item.content.strip() if trim else item.content
        if numbers:
            return f"{indent}{item.line_number} :: {content}"
        return f"{indent}{content}"
    return f"{indent}{item}"


@annotated(meta={"tool_type": "extender", "item_type": "any", "output_type": "str"})
def extend_file_lines(item: str | Path) -> Iterable[str]:
    # Convert strings to Path objects
    if isinstance(item, str):
        item = Path(item)
    if not isinstance(item, Path):
        return
    if not item.is_file():
        return
    with open(item) as fin:
        for ln in fin:
            yield ln.strip()


@annotated(meta={"tool_type": "inserter", "is_nested": True, "output_type": "Path"})
def git_tree(directory: str = ".") -> Iterable[tuple[int, Path]]:
    """Insert the tree of directories under a directory, git repos as leafs.

    Walks the directory with os.walk and yields (depth, path) pairs for every
    directory on the way: the directory itself is the root of the tree (depth
    0), its subdirectories sit at depth 1, and so on. A directory becomes a
    leaf of the tree when it is empty or when it is a git repository (has a
    .git entry, a directory or a file - worktrees and submodules keep .git as
    a file): the walk does not descend into git repositories, so their
    contents stay out of the tree - the walked directory itself included,
    so a repository given as the directory is the whole tree. The .git
    directory of a repository is skipped the same way - the walk goes through
    the working tree, not through the git bookkeeping.

    Args:
        directory: Directory to walk (default: current directory).

    Yields:
        (depth, Path) pairs: the directory itself at depth 0, its
        subdirectories at depth 1, and so on.
    """
    base = Path(directory).expanduser().resolve()
    if not base.is_dir():
        return

    for root, dirs, _files in os.walk(str(base)):
        path = Path(root)
        dirs[:] = [] if (path / ".git").exists() else [name for name in dirs if name != ".git"]
        dirs.sort()
        yield (len(path.relative_to(base).parts), path)


@annotated(meta={"tool_type": "extender", "item_type": "Path", "output_type": "Path"})
def extend_dir(item: Path, pattern: str = "*") -> Iterable[Path] | None:
    """Extend a directory with the entries to walk into.

    Files are yielded when they match ``pattern``. Directories are always yielded, so the
    extension can walk deeper - but only when something matching lives inside them, so a
    branch without matches disappears instead of ending in an empty directory.

    Args:
        item: Directory path.
        pattern: Glob for the files to stop at (default: '*' = every file, as before).

    Returns:
        The directory entries, or None for non-Path items.

    Examples:
        ``ls_files src 'udan', extend_dir '*.py' --max-depth=5``
        # udan, its subdirectories, and the .py files inside them
    """
    if not isinstance(item, Path):
        return None
    entries = list(item.glob("*"))
    matched_dirs = {entry for entry in entries if entry.is_dir() and any(entry.glob(f"**/{pattern}"))}
    return [entry for entry in entries if entry in matched_dirs or (entry.is_file() and entry.match(pattern))]


@annotated(meta={"tool_type": "extender", "item_type": "any", "output_type": "str"})
def extend_rg(item: str | Path, pattern: str, o: bool = False) -> Iterable[str]:
    """Extend file with lines matching regexp (like ripgrep).

    Similar to 'rg' command - reads a file and yields lines (or matching parts)
    that match the given regular expression pattern.

    Args:
        item: File path (str or Path)
        pattern: Regular expression pattern to match
        o: If True, yield only the matching parts (like 'rg -o').
           If False, yield the full lines that contain matches.

    Yields:
        Full lines containing matches (o=False) or matching parts only (o=True)
    """
    # Convert to Path
    if isinstance(item, str):
        item = Path(item)
    if not isinstance(item, Path):
        return
    if not item.is_file():
        return

    try:
        with open(item, encoding="utf-8", errors="ignore") as f:
            if o:
                # Yield only matching parts (like rg -o)
                for line in f:
                    line = line.rstrip("\n\r")
                    matches = re.findall(pattern, line)
                    yield from matches
            else:
                # Yield full lines that contain at least one match
                for line in f:
                    line = line.rstrip("\n\r")
                    if re.search(pattern, line):
                        yield line
    except OSError, re.error:
        return


@annotated(meta={"tool_type": "filter", "item_type": "Path"})
def greps_in(item: str | Path | PathGlob, tokens: Annotated[list[str], "vararg"]) -> bool:
    """Filter files by presence and absence of tokens in their content.

    Port of the greps-in shell function: each file from the input is kept only
    when it contains every plain token and none of the '-'-prefixed tokens.

    Args:
        item: File path as str, Path or PathGlob.
        tokens: Tokens to check; a leading '-' marks an absence requirement.

    Returns:
        True when the file satisfies all token conditions, False otherwise.

    Examples:
        ls_files src, greps_in TODO FIXME -test
        # Keeps files containing both 'TODO' and 'FIXME' but not 'test'
    """
    path = item.path if isinstance(item, PathGlob) else Path(item)
    if not path.is_file():
        return False
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False

    for token in tokens:
        if token.startswith("-"):
            if token[1:] in content:
                return False
        elif token not in content:
            return False
    return True


@annotated(meta={"attribute_type": "simple"})
def count_lines(item: str | Path | PathGlob) -> int:
    # Handle PathGlob objects
    if isinstance(item, PathGlob):
        path = item.path
    elif isinstance(item, (str, Path)):
        path = item
    else:
        return -1
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


@annotated(meta={"attribute_type": "simple"})
def modification_date(item: str | Path) -> str:
    path = item
    path = Path(path) if isinstance(path, str) else path
    if not path.exists():
        return ""
    return str(datetime.fromtimestamp(path.stat().st_mtime))


@annotated(meta={"attribute_type": "simple"})
def get_synchronization_type(item: str | Path) -> str:
    """
    Returns the synchronization type based on the presence of specific directories.

    Returns:
    - ".git" if the item has a .git directory
    - ".stfolder" if the item has a .stfolder directory
    - "nothing" if there is no synchronization
    """
    item_path = Path(item)

    try:
        if (item_path / ".git").is_dir():
            return "git"
        elif (item_path / ".stfolder").is_dir():
            return "syncthing"
        else:
            return "UNK"
    except PermissionError:
        return "ERROR"


def _format_size_human(total_size: int) -> str:
    """Formats a byte count as a pretty human string, mb/kb/etc."""
    if total_size < _BYTES_PER_KB:
        return f"{total_size} B"
    elif total_size < _BYTES_PER_MB:
        return f"{total_size / _BYTES_PER_KB:.2f} KB"
    elif total_size < _BYTES_PER_GB:
        return f"{total_size / _BYTES_PER_MB:.2f} MB"
    else:
        return f"{total_size / _BYTES_PER_GB:.2f} GB"


@annotated(meta={"attribute_type": "simple"})
def get_directory_size(item: str | Path) -> str:
    """
    Returns size in pretty format, mb/kb/etc.
    """
    path = Path(item)
    total_size = sum(file.stat().st_size for file in path.glob("**/*") if file.is_file())
    return _format_size_human(total_size)


@annotated(meta={"attribute_type": "simple"})
def size(item: str | Path) -> int:
    """Returns file size in bytes.

    For files, returns the actual file size.
    For directories, returns the total size of all contained files.
    """
    path = Path(item) if isinstance(item, str) else item

    try:
        if path.is_file():
            return path.stat().st_size
        elif path.is_dir():
            return sum(f.stat().st_size for f in path.glob("**/*") if f.is_file())
        else:
            return 0
    except OSError, FileNotFoundError:
        return 0


@annotated(meta={"attribute_type": "simple"})
def size_human(item: str | Path) -> str:
    """Returns file size in pretty format, mb/kb/etc.

    For files, returns the actual file size.
    For directories, returns the total size of all contained files.
    """
    return _format_size_human(size(item))


@annotated(meta={"attribute_type": "simple"})
def is_empty_dir(item: str | Path) -> int:
    if not Path(item).exists() or Path(item).is_file():
        return 0
    children = os.listdir(item)
    return int(not children)


@annotated(meta={"attribute_type": "simple"})
def total_files_count(item: str | Path, links: bool = False) -> int:
    """Returns the count of nodes inside a directory.

    For files, returns 1.
    For directories, returns the count of all items (files and directories)
    contained recursively.

    Args:
        item: Path to the file or directory.
        links: If True, follow symbolic links when counting. If False (default),
               don't traverse into symlinked directories.
    """
    path = Path(item) if isinstance(item, str) else item

    if not path.exists():
        return 0

    if path.is_file():
        return 1

    # If path is a symlink and we don't want to follow links, count it as 1
    if not links and path.is_symlink():
        return 1

    # For directories, count all items recursively
    count = 0
    for root, dirs, files in os.walk(str(path), followlinks=links):
        count += len(dirs) + len(files)
        if not links:
            # Remove symlinked directories to prevent traversal into them
            dirs[:] = [d for d in dirs if not Path(root, d).is_symlink()]
    return count


@annotated(meta={"attribute_type": "simple"})
def fpath_content_hash(item: str | Path) -> str | None:
    """Get content hash of a file for caching purposes.

    This attribute extracts the file path from the item and returns
    a SHA256 hash of the file's content. This is useful for cache invalidation.

    Args:
        item: File path as str/Path, or a reference in format "path:line"

    Returns:
        SHA256 hash of file content as hex string, or None if file doesn't exist
    """
    # Extract file path from item
    if isinstance(item, str) and ":" in item:
        # Handle "path:line" format - extract just the path
        file_path: str | Path = item.rsplit(":", 1)[0]
    elif isinstance(item, (str, Path)):
        file_path = item
    else:
        return None

    path = Path(file_path) if isinstance(file_path, str) else file_path

    # Check if file exists
    if not path.is_file():
        return None

    try:
        content = path.read_bytes()
        return sha256(content).hexdigest()
    except OSError:
        return None


@annotated(meta={"attribute_type": "simple", "aliases": ["fpath_update_date", "fs.fpath_update_date"]})
def fpath_update_date(item: str | Path) -> str | None:
    """Get file modification timestamp for cache invalidation.

    This attribute extracts the file path from the item and returns
    the file's modification time as a Unix timestamp.

    Args:
        item: File path as str/Path, or a reference in format "path:line"

    Returns:
        File modification time as Unix timestamp string, or None if file doesn't exist
    """
    # Extract file path from item
    if isinstance(item, str) and ":" in item:
        # Handle "path:line" format - extract just the path
        file_path: str | Path = item.rsplit(":", 1)[0]
    elif isinstance(item, (str, Path)):
        file_path = item
    else:
        return None

    path = Path(file_path) if isinstance(file_path, str) else file_path

    # Check if file exists
    if not path.is_file():
        return None

    try:
        return str(path.stat().st_mtime)
    except OSError:
        return None


@annotated(meta={"attribute_type": "simple"})
def file_name(item: str | Path) -> str:
    """Return the name of a file or directory.

    Args:
        item: File path as str or Path

    Returns:
        The base name of the file or directory (e.g., "file.txt" from "/path/to/file.txt")
    """
    path = Path(item) if isinstance(item, str) else item
    return path.name


@annotated(meta={"attribute_type": "simple"})
def file_created(item: str | Path | dict, fmt: str = "%Y-%m-%d--%H-%M--%f") -> str:
    """Return file creation/modification time formatted as string.

    Uses st_ctime (platform-dependent: birth time on some systems, metadata change on others).
    Handles dict items (from peval) by extracting _path.

    Args:
        item: File path as str/Path, or dict with '_path' key
        fmt: strftime format string. Default: "%Y-%m-%d--%H-%M--%f" (millis as microseconds).

    Returns:
        Formatted timestamp string.
    """
    if isinstance(item, dict):
        item = item.get("_path", "")
    path = Path(item) if isinstance(item, str) else item
    if not path.exists():
        return ""
    ts = path.stat().st_ctime
    return datetime.fromtimestamp(ts).strftime(fmt)


@annotated(meta={"attribute_type": "simple"})
def relative_path(item: str | Path, base_path: str | Path) -> str:
    """Return the relative path of item from base_path.

    Calculates the relative path from base_path to the item.
    For example, if item is "/a/b/c/d.txt" and base_path is "/a/",
    returns "b/c/d.txt".

    Args:
        item: File path as str or Path
        base_path: Base directory path as str or Path

    Returns:
        Relative path from base_path to item.
        If item is not relative to base_path, returns the absolute path.

    Examples:
        >>> relative_path("/a/b/c/d.txt", "/a/")
        "b/c/d.txt"
        >>> relative_path("/a/b/c/d.txt", "/a/b")
        "c/d.txt"
        >>> relative_path("/x/y/z.txt", "/a/")
        "/x/y/z.txt"  # not relative, returns absolute path
    """
    item_path = Path(item) if isinstance(item, str) else item
    base = Path(base_path).expanduser() if isinstance(base_path, str) else base_path.expanduser()

    try:
        return str(item_path.relative_to(base))
    except ValueError:
        # Item is not relative to base_path, return the absolute path
        return str(item_path.absolute())


@annotated(meta={"attribute_type": "simple"})
def env_entry_value(item: EnvEntryOrComment) -> str:
    """Get the value from an env entry.

    Args:
        item: A structured dict from read_env inserter with format:
              {"type": "entry", "entry": [key, value], "comment": None}

    Returns:
        The value part of the env entry, or empty string for comments/non-entries.
    """
    if isinstance(item, dict) and item.get("type") == "entry":
        entry = item.get("entry")
        if isinstance(entry, list) and len(entry) == ENV_ENTRY_LIST_LEN:
            return entry[1]
    return ""


@annotated(meta={"attribute_type": "simple"})
def file_line_content(item: FileLine) -> str:
    """Get the content from a file line.

    Args:
        item: A FileLine dataclass from read_file inserter.

    Returns:
        The line content.
    """
    if isinstance(item, FileLine):
        return item.content
    return ""


@annotated(meta={"attribute_type": "simple"})
def file_content(item: str | Path) -> str:
    """Read and return full file content.

    Args:
        item: File path as str or Path.

    Returns:
        Full file content as string, or empty string if file doesn't exist.
    """
    path = Path(item) if isinstance(item, str) else item
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


@annotated(meta={"tool_type": "inserter", "output_type": "grouped_file"})
def insert_glob_groups(directory: str = ".", globs: str = "*", collapse_others: bool = False) -> Iterable:  # noqa: C901, PLR0912
    """Insert files matching glob patterns with group attributes.

    For each glob pattern in globs (comma-separated), finds matching files
    in the directory and yields them with a glob_group attribute indicating
    which pattern matched. Files not matching any glob can be collapsed
    into a single "others" entry.

    Args:
        directory: Directory path to search in.
        globs: Comma-separated glob patterns (e.g., 'api_*.py,impl_*.py,plugins_*').
        collapse_others: If True, files not matching any glob are shown as
            a single "others" entry. If False, all files are shown individually.
            Default is False.

    Yields:
        File paths (Path objects) with glob_group attribute set to the matched
        pattern name (e.g., 'api_*') or '<others>' for unmatched files.

    Examples:
        # Insert all Python files matching specific patterns from src/udan
        fs.insert_glob_groups src/udan 'api_*.py,impl_*.py,plugins_*.py'

        # Collapse unmatched files into "others"
        fs.insert_glob_groups src/udan 'api_*.py,impl_*.py' --collapse_others=True
    """
    path = Path(directory).expanduser()

    # Parse comma-separated globs
    glob_patterns = [g.strip() for g in globs.split(",") if g.strip()]
    if not glob_patterns:
        glob_patterns = ["*"]

    # Extract the base pattern from globs (e.g., '*.py' from 'api_*.py')
    # This is used to determine which files to consider for "others"
    base_patterns = set()
    for glob_pattern in glob_patterns:
        # Extract the extension/pattern after the first wildcard
        if "*" in glob_pattern:
            # Get everything after the first *
            parts = glob_pattern.split("*", 1)
            if len(parts) > 1:
                base_patterns.add("*" + parts[1])
            else:
                base_patterns.add("*")
        else:
            base_patterns.add(glob_pattern)

    # If no base patterns found, use '*'
    if not base_patterns:
        base_patterns.add("*")

    # Get all files matching the base patterns
    all_files = set()
    for base_pattern in base_patterns:
        for match in path.glob(base_pattern):
            if match.is_file():
                all_files.add(match)

    # Match each file to a pattern and determine its group
    matched_files: dict[Path, str] = {}
    for file_path in all_files:
        for glob_pattern in glob_patterns:
            if file_path.match(glob_pattern):
                matched_files[file_path] = glob_pattern
                break

    # Separate matched and unmatched files
    others = [f for f in all_files if f not in matched_files]

    # Yield matched files with their group attribute
    for file_path, group_name in sorted(matched_files.items()):
        yield PathGlob(path=file_path, glob_group=group_name)

    # Handle "others" based on collapse_others flag
    if others:
        if collapse_others:
            # For collapse mode, create a temporary file containing the paths
            # of unmatched files. This allows count_lines to work properly.
            with tempfile.NamedTemporaryFile(mode="w", prefix="udan_others_", suffix=".txt", delete=False) as tmp:
                for other_file in sorted(others):
                    tmp.write(str(other_file) + "\n")
                tmp_path = Path(tmp.name)
            yield PathGlob(path=tmp_path, glob_group="<others>")
        else:
            # Show each unmatched file individually
            for other_file in sorted(others):
                yield PathGlob(path=other_file, glob_group="<others>")


@annotated(meta={"tool_type": "grouper", "item_type": "any"})
def group_by_globs(item: str | Path | PathGlob, globs: Annotated[list[str], "vararg"]) -> Group:
    """Assign a path-like item to the first user-specified glob group, with a fallback "others".

    This is the query-level counterpart of :func:`insert_glob_groups`: the grouping does not
    depend on the inserter, so any file listing (ls_files, insert_glob_groups, git_tree, ...)
    can be grouped afterwards, at any position (--position).

    Args:
        item: The path-like item to assign to a group (str, Path or PathGlob).
        globs: Group definitions passed as positional strings, each listing one or more
            comma-separated glob patterns (e.g. ``"**/api_*.py,**/impl_*.py"``). An item
            belongs to the first group, in the order the groups are given, whose any
            pattern matches the item's path.

    Returns:
        A :class:`~udan.core_tools_loading.api_types.Group` whose key is the normalized comma-joined group
        spec (or ``"<others>"``) and whose ``order`` reflects the position of the matching
        spec in ``globs`` (the fallback sorts last).

    Examples:
        ``group_by_globs '**/api_*.py' '**/impl_*.py'`` groups ``src/udan/core/api_x.py`` into
        ``"**/api_*.py"``, ``src/udan/core/impl_y.py`` into ``"**/impl_*.py"`` and everything
        else into ``"<others>"``. Patterns follow ``Path.match``: a leading ``**/`` matches
        any depth, an embedded ``**`` does not.
    """
    path = item.path if isinstance(item, PathGlob) else Path(item)
    for order, group_spec in enumerate(globs):
        wanted = [w for w in (g.strip() for g in group_spec.split(",")) if w]
        if wanted and any(path.match(glob) for glob in wanted):
            return Group(key=",".join(wanted), order=order)
    return Group(key="<others>", order=len(globs))
