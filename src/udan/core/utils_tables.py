"""Shared helpers for tabular row data.

Used by the tabular plugins (csv, sql) to convert raw rows
into dictionaries keyed by normalized column headers.
"""


def _row_columns(item: object) -> dict | None:
    """Get the columns of a row item.

    The row inserters (read_csv_rows, read_sql) declare
    `output_semantic: "row"`: their items carry the columns in a ``row_data``
    dict next to the row metadata (row number, origin file, rowid).

    Args:
        item: Item to inspect

    Returns:
        The columns dict when the item is a row, None otherwise
    """
    row_data = getattr(item, "row_data", None)
    return row_data if isinstance(row_data, dict) else None


def normalize_headers(headers: list) -> list[str]:
    """Normalize column headers: strip, lower, spaces to underscores."""
    return [str(h).strip().replace(" ", "_").lower() for h in headers]


def rows_to_dicts(rows: list[list], has_header: bool = True, header_row: int = 0) -> list[dict]:
    """Convert table rows to list of dictionaries.

    Args:
        rows: List of rows (list of cell values)
        has_header: If True, use header row as dictionary keys
        header_row: Row number to use as header (0-indexed)

    Returns:
        List of dictionaries with column headers as keys. If has_header is False,
        returns rows as dicts with column indices (as strings) as keys.

    Raises:
        ValueError: If header_row is out of range
    """
    if not rows:
        return []

    if has_header:
        if header_row >= len(rows):
            raise ValueError(f"header_row {header_row} >= total rows {len(rows)}")

        headers = normalize_headers(rows[header_row])

        result = []
        for i, row in enumerate(rows):
            if i == header_row:
                continue  # Skip header row
            # Create dict, handling rows with fewer columns than headers
            row_dict = {}
            for j, header in enumerate(headers):
                value = row[j] if j < len(row) else ""
                row_dict[header] = value
            result.append(row_dict)

        return result
    else:
        # No headers, return rows as dicts with column indices as keys
        return [{str(i): val for i, val in enumerate(row)} for row in rows]
