import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from udan.core.api_forests import Item
from udan.core.utils_binding import convert_boolean_string
from udan.core_tools_loading.api_annotated import annotated
from udan.plugins_tools_examples.api_types import ASTChunk
from udan.plugins_tools_examples.plugins_dev import Duplication
from udan.plugins_tools_examples.plugins_org import _get_dict_title
from udan.plugins_tools_examples.plugins_org_parser import OrgItem
from udan.plugins_tools_examples.utils_file_line import parse_file_line_reference

DOMAIN = "markdown"

# Minimum lines for a markdown table block: header, delimiter and one body row
TABLE_MIN_BLOCK_LINES = 3

# Unescaped pipe: a column separator (\| escapes a literal pipe inside a cell)
TABLE_CELL_SEPARATOR = re.compile(r"(?<!\\)\|")


@annotated(meta={"tool_type": "inserter", "output_type": "Path"})
def md_files(directory: str = ".") -> Iterable[Path]:
    """
    List markdown files in a directory.

    Args:
        directory (str): Existing directory path to search for markdown files.

    Yields:
        Path: Markdown file paths.
    """
    path = Path(directory).expanduser()
    if not path.is_dir():
        return
    for md_file in path.glob("*.md"):
        if md_file.is_file():
            yield md_file


@annotated(meta={"tool_type": "extender", "item_type": "any", "output_type": "str"})
def md_search(item: Path, pattern: str = r".", limit: int = 200) -> Iterable[str]:
    """
    Extend a markdown file with lines matching a pattern.

    Args:
        item (Any): A Path object pointing to a markdown file.
        pattern (str): Regular expression pattern to match lines.
        limit (int): Maximum number of matching lines to return. Use 0 for unlimited.

    Yields:
        str: Formatted string in the format "{path}:{line} :: {match}".
    """
    if not isinstance(item, Path):
        return
    if not item.is_file():
        return

    # Compile regex pattern
    regex = re.compile(pattern)

    count = 0
    with open(item, encoding="utf-8", errors="ignore") as f:
        for line_number, line in enumerate(f, start=1):
            if limit > 0 and count >= limit:
                break
            if regex.search(line):
                match = line.rstrip("\n")
                yield f"{item}:{line_number} :: {match}"
                count += 1


@annotated(meta={"tool_type": "inserter", "output_type": "str"})
def md_lines(directory: str = ".", pattern: str = r".", limit: int = 200) -> Iterable[str]:
    """
    Find lines matching a pattern in markdown files within a directory.

    This is a convenience function that combines md_files + md_search.

    Args:
        directory (str): Existing directory path to search for markdown files.
        pattern (str): Regular expression pattern to match lines.
        limit (int): Maximum number of matching lines to return. Use 0 for unlimited.

    Yields:
        str: Formatted string in the format "{path}:{line} :: {match}".
    """
    path = Path(directory).expanduser()
    if not path.is_dir():
        return

    # Compile regex pattern
    regex = re.compile(pattern)

    count = 0
    # Find all markdown files in directory (non-recursive)
    for md_file in path.glob("*.md"):
        if not md_file.is_file():
            continue

        # Stop if limit reached (0 means unlimited)
        if limit > 0 and count >= limit:
            break

        # Read file and yield matching lines
        with open(md_file, encoding="utf-8", errors="ignore") as f:
            for line_number, line in enumerate(f, start=1):
                if limit > 0 and count >= limit:
                    break
                if regex.search(line):
                    match = line.rstrip("\n")
                    yield f"{md_file}:{line_number} :: {match}"
                    count += 1


# Markdown table prettifying


def _split_table_row(line: str) -> list[str]:
    """Split a markdown table row line into trimmed cell values.

    An escaped pipe (\\|) is a literal pipe inside a cell, not a column separator.
    """
    stripped = line.strip()
    cells = TABLE_CELL_SEPARATOR.split(stripped)
    if len(cells) > 1 and cells[0] == "":
        cells = cells[1:]  # leading delimiter pipe
    if len(cells) > 1 and cells[-1] == "":
        cells = cells[:-1]  # trailing delimiter pipe
    return [cell.strip() for cell in cells]


def _is_table_row(line: str) -> bool:
    """Check if a line looks like a markdown table row (pipe-delimited cells)."""
    return bool(TABLE_CELL_SEPARATOR.search(line))


def _is_table_delimiter_row(line: str) -> bool:
    """Check if a line is a markdown table delimiter row like | --- | :---: |."""
    cells = _split_table_row(line)
    return bool(cells) and all(re.fullmatch(r":?-+:?", cell) for cell in cells)


def _find_table_block(lines: list[str], index: int) -> list[str] | None:
    """Return the contiguous table block of lines containing the given 0-based index.

    A table block is a header row, a delimiter row and body rows. Returns None
    when the lines around the index do not form a table.
    """
    start = index
    while start > 0 and _is_table_row(lines[start - 1]):
        start -= 1
    end = index
    while end + 1 < len(lines) and _is_table_row(lines[end + 1]):
        end += 1
    block = lines[start : end + 1]
    if len(block) < TABLE_MIN_BLOCK_LINES or not _is_table_delimiter_row(block[1]):
        return None
    return block


def _read_table_grid(block: list[str]) -> tuple[list[str], list[list[str]]]:
    """Read a table block into a header row and body rows of cells, padded to the header width."""
    header = _split_table_row(block[0])
    rows = [
        [(cells[i] if i < len(cells) else "") for i in range(len(header))]
        for cells in (_split_table_row(row_line) for row_line in block[2:])
    ]
    return header, rows


def _transpose_table_grid(header: list[str], rows: list[list[str]]) -> tuple[list[str], list[list[str]]]:
    """Transpose a table grid: the header becomes the first data column, the first data column the header."""
    transposed = [[header[i], *(row[i] for row in rows)] for i in range(len(header))]
    return transposed[0], transposed[1:]


def _table_block_to_dicts(block: list[str], transpose: bool = False) -> list[dict[str, str]]:
    """Convert a table block (header, delimiter, body rows) to dicts keyed by column names."""
    header, rows = _read_table_grid(block)
    if transpose:
        header, rows = _transpose_table_grid(header, rows)
    return [dict(zip(header, row)) for row in rows]


def _as_bool(value: bool | str) -> bool:
    """Coerce a bool parameter that may arrive as a flag string from named args."""
    if not isinstance(value, str):
        return bool(value)
    converted = convert_boolean_string(value)
    return converted if converted is not None else False


@annotated(meta={"tool_type": "inserter", "output_type": "dict"})
def md_table(
    location: str,
    line: int | str | None = None,
    transpose: bool | str = False,
    t: bool | str = False,
) -> Iterable[dict]:
    """
    Insert the rows of the markdown table at the given location as dicts.

    Detects the table containing the referenced line (header, delimiter or any
    body row) and yields one dict per body row, keyed by column names. Use the
    universal :entries render to prettify the rows. An escaped pipe (\\|) inside
    a cell is a literal pipe, not a column separator.

    With transpose, rows become columns and columns become rows: the header row
    turns into the first data column and the first data column into the keys.

    Args:
        location (str): File path, either "path:line" or just "path".
        line (int | str): Optional line number, when location is passed without one.
        transpose (bool | str): Transpose the table before inserting.
        t (bool | str): Short alias for transpose.

    Yields:
        dict: One entry per table row, e.g. {"a": "1", "b": "2"}.

    Examples:
        md_table "notes.md:3", :entries
        md_table "notes.md" 3, :entries
        md_table "notes.md" 3 --transpose, :entries
        md_table "notes.md" 3 --t, :entries
    """
    do_transpose = _as_bool(transpose) or _as_bool(t)
    if line is None:
        parsed = parse_file_line_reference(location)
        if parsed is None:
            return
        file_path, line_number = parsed
    else:
        file_path, line_number = Path(location), int(line)

    if not file_path.is_file():
        return

    lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    index = line_number - 1
    if not 0 <= index < len(lines):
        return
    block = _find_table_block(lines, index)
    if block is None:
        return
    yield from _table_block_to_dicts(block, transpose=do_transpose)


# Markdown render tools


def _render_markdown_item(item: OrgItem, indent: str) -> str:
    """Render an OrgItem in markdown format."""
    heading = "#" * item.level
    lines = [f"{indent}{heading} {item.title}"]
    if item.date:
        lines.append(f"{indent}date: {item.date}")
    if item.tags:
        lines.append(f"{indent}tags: {', '.join(item.tags)}")
    if item.content and item.content.strip():
        lines.append(f"{indent}{item.content}")
    return "\n".join(lines)


def _render_markdown_astchunk(item: ASTChunk, depth: int) -> str:
    """Render an ASTChunk in markdown format with metadata list and code fence."""
    heading = "#" * (depth + 1)
    if item.type == "duplication":
        title = f"{item.source_file}:{item.line_start_number}-{item.line_end_number}"
    else:
        type_symbol = "def" if item.type == "function" else "class"
        title = f"{type_symbol} {item.name}"
    lines = [f"{heading} {title}"]
    lines.append(f"- **source_file**: {item.source_file}:{item.line_start_number}-{item.line_end_number}")
    if item.docstring:
        first_line = item.docstring.split("\n")[0]
        lines.append(f"- **docstring**: {first_line}")
    lines.append("")
    lines.append("```python")
    for code_line in item.full_code.splitlines():
        lines.append(f"  {code_line}")
    lines.append("```")
    return "\n".join(lines)


def _render_markdown_duplication(item: Duplication, depth: int) -> str:
    """Render a Duplication as markdown heading with summary."""
    heading = "#" * (depth + 1)
    return f"{heading} {item}"


def _render_markdown_dict(item: dict, indent: str, heading: str) -> str:
    """Render a dict in markdown format with metadata list."""
    title = _get_dict_title(item)
    lines = []

    if title:
        lines.append(f"{heading} {title}")

    # Add metadata list if we have properties
    if item:
        for key, value in item.items():
            lines.append(f"{indent}- **{key}**: {value}")

    return "\n".join(lines)


def _render_markdown_item_content(item: Item, indent: str, depth: int = 0) -> str:
    """Render the content of a markdown item (without attribute name prefix)."""
    # Handle OrgItem objects
    if isinstance(item, OrgItem):
        return _render_markdown_item(item, indent)

    # Handle ASTChunk objects
    if isinstance(item, ASTChunk):
        return _render_markdown_astchunk(item, depth)

    # Handle Duplication objects
    if isinstance(item, Duplication):
        return _render_markdown_duplication(item, depth)

    # Determine heading level based on depth
    heading = "#" * (depth + 1)

    if isinstance(item, dict):
        return _render_markdown_dict(item, indent, heading)

    # Non-dict items: heading line has no indent
    return f"{heading} {str(item)}"


@annotated(meta={"tool_type": "render", "aliases": ["markdown"]})
def render_markdown_generic(item: Item, indent: str = "", depth: int = 0, attrs: dict[str, Any] | None = None) -> str:
    """Render item in markdown format with # heading and metadata list.

    Uses depth parameter to determine heading level:
    - depth 0: # (top level)
    - depth 1: ## (second level)
    - depth 2: ### (third level)
    etc.

    When attrs is provided (for single attribute display), shows:
    - attr_identity
    <markdown item content>
    """
    # Support both direct item and dict format for compatibility
    if isinstance(item, dict) and "item" in item:
        actual_item = item["item"]
        if attrs is None:
            attrs = item.get("attrs")
    else:
        actual_item = item

    # When rendering with an attribute, show attribute identity first
    if attrs:
        attr_identity = list(attrs.keys())[0]
        return f"{indent}- {attr_identity}\n{_render_markdown_item_content(actual_item, indent, depth)}"

    return _render_markdown_item_content(actual_item, indent, depth)
