"""CSV file plugin for reading and parsing CSV data.

This plugin provides inserters for reading CSV files from the filesystem
and converting rows to dictionaries or flat lists.

Supports:
- Reading CSV files with customizable delimiters
- Converting rows to dictionaries using headers
- Reading files as flat lists of values
- Skipping header rows or metadata
"""

import csv
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from udan.core.api_exec_context import ExecContextAPI
from udan.core.utils_tables import rows_to_dicts
from udan.core_tools_loading.api_annotated import annotated

DOMAIN = "csv"


@dataclass
class CsvRow:
    """Structured row from a CSV file.

    Represents a single row from a CSV file, with the row metadata that
    identifies its origin.

    read_csv_rows yields it and the render side formats it.
    """

    row_number: int  # 0-based row number (excluding header row if has_header=True)
    row_data: dict  # Row data as dictionary (column headers as keys)

    def __str__(self) -> str:
        # Format as "| col1 | col2 | col3 |" for table display
        values = [str(self.row_data.get(k, ""))[:30] for k in self.row_data]
        return "| " + " | ".join(values) + " |"


def _read_csv_file(
    filepath: str, delimiter: str = ",", quotechar: str = '"', skip_rows: int = 0, encoding: str = "utf-8"
) -> list[list[str]]:
    """Read CSV file and return rows.

    Args:
        filepath: Path to CSV file
        delimiter: Column delimiter (default: comma)
        quotechar: Quote character (default: double quote)
        skip_rows: Number of rows to skip from beginning
        encoding: File encoding (default: utf-8)

    Returns:
        List of rows (each row is a list of string values)

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file cannot be parsed
    """
    path = Path(filepath).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {filepath}")

    try:
        with open(path, encoding=encoding, newline="") as f:
            reader = csv.reader(f, delimiter=delimiter, quotechar=quotechar)
            rows = [row for row in reader if row]  # Skip empty rows
    except Exception as e:
        raise ValueError(f"Error reading CSV file: {e}")

    # Skip specified number of rows
    if skip_rows > 0:
        rows = rows[skip_rows:]

    return rows


@annotated(meta={"tool_type": "inserter", "output_type": "dict"})
def insert_csv_rows(
    filepath: str,
    has_header: bool = True,
    header_row: int = 0,
    delimiter: str = ",",
    encoding: str = "utf-8",
    ctx: ExecContextAPI | None = None,
) -> list[dict]:
    """Insert rows from a CSV file as dictionaries.

    Reads a CSV file from the filesystem and converts rows to dictionaries
    using column headers as keys.

    Args:
        filepath: Path to CSV file
            Example: "data.csv" or "~/Documents/data.csv"
        has_header: If True (default), use first row as dictionary keys.
            If False, use column indices (0, 1, 2, ...) as keys.
        header_row: Row number to use as header (0-indexed, default: 0).
            Use this if your CSV has metadata rows before the header.
        delimiter: Column delimiter (default: comma ",")
            Use "\\t" for tab-separated values, "|" for pipe-separated, etc.
        encoding: File encoding (default: "utf-8")
        ctx: Optional execution context for logging

    Returns:
        List of dictionaries representing CSV rows.
        Each dictionary has column headers as keys and cell values as values.

    Raises:
        FileNotFoundError: If CSV file doesn't exist
        ValueError: If file cannot be parsed or header_row out of range

    Example:
        >>> # CSV file with headers (data.csv)
        >>> # id,name,age
        >>> # 1,Alice,30
        >>> # 2,Bob,25
        >>> insert_csv_rows "data.csv"
        # Returns: [{"id": "1", "name": "Alice", "age": "30"}, {"id": "2", "name": "Bob", "age": "25"}]

        >>> # TSV file (tab-separated)
        >>> insert_csv_rows "data.tsv", delimiter="\\t"

        >>> # CSV with metadata rows before header
        >>> insert_csv_rows "data.csv", header_row=2

    Notes:
        - File paths can be absolute or relative to current directory
        - ~ is expanded to home directory
        - Empty cells are returned as empty strings
        - Headers are normalized: stripped, lowercased, spaces replaced with underscores
    """
    if ctx:
        ctx.debug(f"Reading CSV file: {filepath}")

    rows = _read_csv_file(filepath, delimiter=delimiter, encoding=encoding)
    dicts = rows_to_dicts(rows, has_header=has_header, header_row=header_row)

    if ctx:
        ctx.debug(f"Read {len(dicts)} rows from CSV file")

    return dicts


@annotated(meta={"tool_type": "inserter", "output_type": "str"})
def insert_csv_values(
    filepath: str,
    delimiter: str = ",",
    skip_rows: int = 0,
    encoding: str = "utf-8",
    ctx: ExecContextAPI | None = None,
) -> list:
    """Insert raw cell values from a CSV file.

    Reads a CSV file and returns cell values as a flat list.
    Useful when you just need the raw values without dictionary structure.

    Args:
        filepath: Path to CSV file
        delimiter: Column delimiter (default: comma ",")
        skip_rows: Number of rows to skip from beginning (default: 0)
        encoding: File encoding (default: "utf-8")
        ctx: Optional execution context for logging

    Returns:
        Flat list of all cell values (row-major order)

    Example:
        >>> # CSV file (data.csv)
        >>> # id,name,age
        >>> # 1,Alice,30
        >>> insert_csv_values "data.csv"
        # Returns: ["id", "name", "age", "1", "Alice", "30"]
    """
    if ctx:
        ctx.debug(f"Reading CSV values from: {filepath}")

    rows = _read_csv_file(filepath, delimiter=delimiter, skip_rows=skip_rows, encoding=encoding)

    # Flatten to list of values
    result = [cell for row in rows for cell in row]

    if ctx:
        ctx.debug(f"Read {len(result)} cell values from CSV file")

    return result


@annotated(meta={"tool_type": "inserter", "output_type": "dict"})
def read_csv(
    filepath: str,
    has_header: bool = True,
    header_row: int = 0,
    ctx: ExecContextAPI | None = None,
) -> list[dict]:
    """Read rows from a CSV file as dictionaries (alias for insert_csv_rows).

    This is a convenience alias for insert_csv_rows with a simpler name.
    Use this when you want a more intuitive name for reading CSV files.

    Args:
        filepath: Path to CSV file
        has_header: If True (default), use first row as dictionary keys
        header_row: Row number to use as header (0-indexed, default: 0)
        ctx: Optional execution context for logging

    Returns:
        List of dictionaries representing CSV rows

    Example:
        >>> # Read CSV file
        >>> read_csv "data.csv"
    """
    return insert_csv_rows(filepath, has_header=has_header, header_row=header_row, ctx=ctx)


@annotated(
    meta={
        "tool_type": "inserter",
        "output_type": "dict",
        "output_semantic": "row",
    }
)
def read_csv_rows(
    filepath: str,
    has_header: bool = True,
    header_row: int = 0,
    ctx: ExecContextAPI | None = None,
) -> Iterable[CsvRow]:
    """Read rows from a CSV file as CsvRow objects.

    Similar to read_csv but yields CsvRow objects that include row number
    and support table rendering.

    Args:
        filepath: Path to CSV file
        has_header: If True (default), use first row as dictionary keys
        header_row: Row number to use as header (0-indexed, default: 0)
        ctx: Optional execution context for logging

    Returns:
        Iterable of CsvRow objects with row_number and row_data

    Example:
        >>> # Read CSV file with row numbers
        >>> read_csv_rows "data.csv"
        # Yields: CsvRow(row_number=0, row_data={"id": "1", "name": "Alice"}), ...
    """
    if ctx:
        ctx.debug(f"Reading CSV rows from: {filepath}")

    rows = _read_csv_file(filepath)

    if has_header:
        if header_row >= len(rows):
            raise ValueError(f"header_row {header_row} >= total rows {len(rows)}")
        # Get headers from specified row
        headers = rows[header_row]
        headers = [h.strip().replace(" ", "_").lower() for h in headers]

        # Convert remaining rows to CsvRow objects
        row_num = 0
        for i, row in enumerate(rows):
            if i == header_row:
                continue  # Skip header row
            # Create dict, handling rows with fewer columns than headers
            row_dict = {}
            for j, header in enumerate(headers):
                value = row[j] if j < len(row) else ""
                row_dict[header] = value
            yield CsvRow(row_number=row_num, row_data=row_dict)
            row_num += 1
    else:
        # No headers, use column indices as keys
        row_num = 0
        for row in rows:
            row_dict = {str(i): val for i, val in enumerate(row)}
            yield CsvRow(row_number=row_num, row_data=row_dict)
            row_num += 1


@annotated(meta={"attribute_type": "simple"})
def csv_row_content(item: CsvRow) -> str:
    """Get the content from a CSV row as formatted table row.

    Args:
        item: A CsvRow dataclass from read_csv_rows inserter.

    Returns:
        The formatted row as "| val1 | val2 | val3 |"
    """
    if isinstance(item, CsvRow):
        return str(item)
    return ""


@annotated(meta={"attribute_type": "simple"})
def csv_cell_content(item: CsvRow | dict, row: int | None = None, column: str | None = None) -> str:
    """Get one cell of a CSV row.

    Works for both row kinds: a CsvRow from read_csv_rows (values in row_data)
    and a plain dict row from read_csv.

    Args:
        item: A CsvRow dataclass or a row dict.
        row: Data row index (supplied by the edit pipeline for dict rows; the
            item itself already carries the values, so this is not used).
        column: Column name; when given, return only that cell value
            (the entries edit pipeline reads the old cell value this way).

    Returns:
        The cell value, or "" for a missing column.
    """
    values = item.row_data if isinstance(item, CsvRow) else item
    if column is not None and isinstance(values, dict):
        return str(values.get(column, ""))
    return str(item)


@annotated(meta={"item_type": "dict", "item_semantic": "row", "tool_type": "render"})
def render_csv_row(item: CsvRow, indent: str = "") -> str:
    """Render CsvRow dataclass as table row with row number prefix.

    Args:
        item: A CsvRow dataclass with row_number and row_data.
        indent: Indentation string (default: "").

    Returns:
        Formatted string like "- 0 | val1 | val2 | val3 |"
    """
    if isinstance(item, CsvRow):
        # Format: "- {row_number} | col1 | col2 | col3 |"
        values = [str(item.row_data.get(k, ""))[:30] for k in item.row_data]
        return f"{indent}- {item.row_number} | " + " | ".join(values) + " |"
    return f"{indent}- {str(item)}"
