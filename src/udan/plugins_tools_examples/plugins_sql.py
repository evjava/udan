"""SQL database plugin for reading SQL table data.

This plugin provides inserters for listing tables of sqlite databases
and reading table rows as row items rendered by render_sql_row.

Supports:
- Listing tables of a database
- Reading table rows via rowid
- Design allows adding other database backends later (currently sqlite only)
"""

import sqlite3
from collections.abc import Iterable
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from udan.core.api_exec_context import ExecContextAPI
from udan.core_tools_loading.api_annotated import annotated

DOMAIN = "sql"


@dataclass
class SqlRow:
    """Structured row from a SQL database table.

    Represents a single row from a database table, with the metadata that
    identifies its origin.
    """

    db_path: str  # Path to the database file
    table: str  # Table name the row belongs to
    row_id: int  # sqlite rowid of the row
    row_data: dict  # Row data as dictionary (column names as keys)

    def __str__(self) -> str:
        # Format as "| col1 | col2 | col3 |" for table display
        values = [str(self.row_data.get(k, ""))[:30] for k in self.row_data]
        return "| " + " | ".join(values) + " |"


def quote_identifier(identifier: str) -> str:
    """Quote a SQL identifier (table or column name).

    Args:
        identifier: Identifier name to quote

    Returns:
        Quoted identifier safe for interpolation into SQL
    """
    escaped = identifier.replace('"', '""')
    return f'"{escaped}"'


def connect_sql(filepath: str) -> sqlite3.Connection:
    """Connect to a sqlite database file.

    Args:
        filepath: Path to the database file

    Returns:
        Open sqlite3 connection

    Raises:
        FileNotFoundError: If database file doesn't exist
    """
    path = Path(filepath).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"SQL database not found: {filepath}")
    return sqlite3.connect(path)


def _select_statement(table: str, where: str, limit: int) -> str:
    """Build a SELECT statement for a table with rowid.

    Args:
        table: Table name
        where: Optional WHERE condition (without the WHERE keyword)
        limit: Maximum number of rows (0 means no limit)

    Returns:
        SELECT statement string
    """
    sql = f"SELECT rowid, * FROM {quote_identifier(table)}"
    if where:
        sql += f" WHERE {where}"
    if limit > 0:
        sql += f" LIMIT {int(limit)}"
    return sql


@annotated(meta={"tool_type": "inserter", "output_type": "str"})
def show_sql_tables(
    filepath: str,
    ctx: ExecContextAPI | None = None,
) -> list[str]:
    """Show tables of a SQL database.

    Lists table names of a sqlite database in alphabetical order.
    Internal sqlite tables (sqlite_*) are excluded.

    Args:
        filepath: Path to the sqlite database file
        ctx: Optional execution context for logging

    Returns:
        List of table names

    Raises:
        FileNotFoundError: If database file doesn't exist

    Example:
        >>> show_sql_tables "data.db"
        # Returns: ["orders", "users"]
    """
    if ctx:
        ctx.debug(f"Listing SQL tables in: {filepath}")

    with closing(connect_sql(filepath)) as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_schema WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]

    if ctx:
        ctx.debug(f"Found {len(tables)} tables")

    return tables


@annotated(
    meta={
        "tool_type": "inserter",
        "output_type": "dict",
        "output_semantic": "row",
    }
)
def read_sql(
    filepath: str,
    table: str,
    where: str = "",
    limit: int = 0,
    ctx: ExecContextAPI | None = None,
) -> Iterable[SqlRow]:
    """Read rows from a SQL table as SqlRow objects.

    Yields SqlRow objects that include the
    rowid, table name and database path the row came from.

    Args:
        filepath: Path to the sqlite database file
        table: Table name to read from
        where: Optional WHERE condition (without the WHERE keyword)
        limit: Maximum number of rows to read (0 means no limit)
        ctx: Optional execution context for logging

    Returns:
        Iterable of SqlRow objects with db_path, table, row_id and row_data

    Example:
        >>> # Read table rows with the rowid metadata
        >>> read_sql "data.db", table=users
        # Yields: SqlRow(db_path="data.db", table="users", row_id=1, row_data={"id": 1, ...}), ...

    Notes:
        - Requires the table to have rowid (not WITHOUT ROWID tables)
    """
    if ctx:
        ctx.debug(f"Reading SQL rows from table {table} in: {filepath}")

    sql = _select_statement(table, where, limit)
    db_path = str(Path(filepath).expanduser())
    with closing(connect_sql(filepath)) as conn:
        cursor = conn.execute(sql)
        columns = [d[0] for d in cursor.description][1:]  # Skip rowid column
        for row in cursor.fetchall():
            row_id = row[0]
            row_data = dict(zip(columns, row[1:], strict=True))
            yield SqlRow(db_path=db_path, table=table, row_id=row_id, row_data=row_data)


@annotated(meta={"attribute_type": "simple"})
def sql_row_content(item: SqlRow) -> str:
    """Get the content from a SQL table row as formatted table row.

    Args:
        item: A SqlRow dataclass from read_sql inserter.

    Returns:
        The formatted row as "| val1 | val2 | val3 |"
    """
    if isinstance(item, SqlRow):
        return str(item)
    return ""


@annotated(meta={"item_type": "dict", "item_semantic": "row", "tool_type": "render"})
def render_sql_row(item: SqlRow, indent: str = "") -> str:
    """Render SqlRow dataclass as table row with rowid prefix.

    Args:
        item: A SqlRow dataclass with row_id and row_data.
        indent: Indentation string (default: "").

    Returns:
        Formatted string like "- 1 | val1 | val2 | val3 |"
    """
    if isinstance(item, SqlRow):
        # Format: "- {row_id} | col1 | col2 | col3 |"
        values = [str(item.row_data.get(k, ""))[:30] for k in item.row_data]
        return f"{indent}- {item.row_id} | " + " | ".join(values) + " |"
    return f"{indent}- {str(item)}"
