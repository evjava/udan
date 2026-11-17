"""Utility functions for parsing file:line references."""

from pathlib import Path

# Number of parts expected in a "file:line" reference
FILE_LINE_PARTS = 2


# todo fix: introduce later some registry to types_coercions
def parse_file_line_reference(item: str) -> tuple[Path, int] | None:
    """Parse a file:line reference string.

    Args:
        item: A file:line reference string (e.g., "path/to/file.py:42")

    Returns:
        Tuple of (file_path, line_number) or None if parsing fails
    """
    if not isinstance(item, str) or ":" not in item:
        return None

    parts = item.rsplit(":", 1)
    if len(parts) != FILE_LINE_PARTS:
        return None

    file_path, line_str = parts
    try:
        line_num = int(line_str)
    except ValueError:
        return None

    return Path(file_path), line_num
