"""SQLite-backed command history logging for udan.

This module provides history logging to a SQLite database file.
It is selected by the history plugin when the configured history path ends with ".db".
"""

import re
import sqlite3
import threading
from collections.abc import Iterable
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from udan.core.api_forests import Forest
from udan.plugins_history.api_history import HistoryLoggerAPI


@lru_cache(maxsize=32)
def _compile_pattern(pattern: str) -> re.Pattern:
    """Compile a regex pattern with IGNORECASE flag (cached)."""
    return re.compile(pattern, re.IGNORECASE)


def _regexp_matches(pattern: str, value: str | None) -> int:
    """REGEXP implementation for SQLite: 1 if value matches pattern, else 0."""
    if value is None:
        return 0
    return 1 if _compile_pattern(pattern).search(value) else 0


HISTORY_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS history ("
    " id INTEGER PRIMARY KEY,"
    " timestamp TEXT NOT NULL,"
    " command TEXT NOT NULL,"
    " success INTEGER NOT NULL,"
    " total_items INTEGER NOT NULL,"
    " depth_zero_items INTEGER NOT NULL,"
    " error TEXT,"
    " comment TEXT)"
)

# Covers "ORDER BY timestamp DESC, id DESC": SQLite scans this index backwards,
# so get_history with LIMIT reads only the needed entries instead of sorting
# the whole table, and REGEXP queries stop as soon as LIMIT rows matched.
HISTORY_INDEX_NAME = "idx_history_ts_id"
HISTORY_INDEX = f"CREATE INDEX IF NOT EXISTS {HISTORY_INDEX_NAME} ON history(timestamp, id)"

_HISTORY_SELECT_COLUMNS = "id, timestamp, command, success, total_items, depth_zero_items, error, comment"
_ORDER = "ORDER BY timestamp DESC, id DESC"


def _row_to_entry(row: tuple) -> dict[str, Any]:
    """Convert a database row to a history entry dict."""
    history_id, timestamp, command, success, total_items, depth_zero_items, error, comment = row
    entry: dict[str, Any] = {
        "history_id": history_id,
        "timestamp": timestamp,
        "command": command,
        "success": bool(success),
        "total_items": total_items,
        "depth_zero_items": depth_zero_items,
    }
    if error is not None:
        entry["error"] = error
    if comment is not None:
        entry["comment"] = comment
    return entry


class HistoryLoggerSqlite(HistoryLoggerAPI):
    """Logger for udan command execution history stored in SQLite.

    Logs each command execution with timestamp, command, success status,
    and statistics about the results (total items, depth-0 items).
    Pattern, visibility and limit filtering are pushed down to SQL, so
    queries do not need to load the whole history into memory.

    The connection is opened once per thread and reused, with the schema,
    the index and the regexp helper created at connection setup - so reads
    and logs do not repeat that work per call.
    """

    def __init__(self, history_path: str | None = None) -> None:
        """Initialize history logger.

        Args:
            history_path: Path to SQLite history database. If None, history logging is disabled.
        """
        self._history_path = Path(history_path).expanduser() if history_path else None
        self._local = threading.local()

    def _connection(self, create: bool = False) -> sqlite3.Connection | None:
        """Return this thread's connection, opening it (and the schema) on first use.

        Args:
            create: When True, create the database file if missing (log writes);
                when False, return None for a missing file so reads never create it.

        Returns:
            Open connection with schema, index and regexp helper in place,
            or None when history is disabled or the database does not exist.
        """
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            return conn
        history_path = self._history_path
        if not history_path:
            return None
        if not history_path.exists():
            if not create:
                return None
            history_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(history_path)
        # The index must exist before queries: _query_history uses INDEXED BY,
        # which raises on a missing index and would turn every read into a
        # silent failure on legacy storages that predate the index.
        conn.execute(HISTORY_SCHEMA)
        conn.execute(HISTORY_INDEX)
        conn.create_function("regexp", 2, _regexp_matches)
        self._local.conn = conn
        return conn

    @property
    def history_path(self) -> Path | None:
        """Get the history database path.

        Returns:
            Path to history database, or None if history is disabled
        """
        return self._history_path

    def close(self) -> None:
        """Close this thread's live connection, if one is open.

        Idempotent: a second call, and a close before the first use, do
        nothing. Other threads' connections are theirs to close.
        """
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    def log(
        self,
        command: str,
        success: bool,
        forest: Forest,
        error: str | None = None,
        comment: str | None = None,
    ) -> None:
        """Log a command execution to history.

        Args:
            command: The query/command that was executed
            success: Whether the command executed successfully
            forest: The resulting Forest (even on error, may be partial)
            error: Error message if command failed, None otherwise
            comment: Optional comment describing the purpose/goal of the command
        """
        if not self._history_path:
            return

        # Calculate statistics
        total_items = len(forest.items)
        depth_zero_items = sum(1 for depth, _ in forest.as_pairs() if depth == 0)

        try:
            conn = self._connection(create=True)
            if conn is None:
                return
            conn.execute(
                "INSERT INTO history (timestamp, command, success, total_items, depth_zero_items, error, comment)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    datetime.now().isoformat(),
                    command,
                    1 if success else 0,
                    total_items,
                    depth_zero_items,
                    error,
                    comment,
                ),
            )
            conn.commit()
        except sqlite3.Error:
            # Fail silently if history write fails
            pass

    def get_history(
        self,
        pattern: str | None = None,
        limit: int | None = None,
        success: bool | None = None,
        min_command_length: int | None = None,
    ) -> Iterable[dict[str, Any]]:
        """Read recent history entries, newest first.

        Rows are streamed from the database cursor, so a consumer that stops
        iterating early never materializes the remaining entries. Pattern,
        visibility and limit filtering are pushed down to SQL.

        Args:
            limit: Maximum number of entries to return (most recent first).
                   If None, returns all entries. A negative value is treated as
                   no limit.
            pattern: Optional regex pattern to filter entries by command text.
                     Only entries whose command matches the pattern are returned.
            success: Optional success status to filter by; only entries with this
                     status are returned (default: None = any status).
            min_command_length: Optional minimum command length; only entries whose
                     command is at least this many characters are returned
                     (default: None = no minimum).

        Returns:
            Iterable of history entry dictionaries (with history_id key), sorted
            by timestamp (newest first)
        """
        history_path = self._history_path
        if not history_path or not history_path.exists():
            return []

        # Compile pattern first so invalid regex raises here (like jsonl impl)
        if pattern is not None:
            _compile_pattern(pattern)

        return self._query_history(pattern, limit, success, min_command_length)

    def _query_history(
        self,
        pattern: str | None,
        limit: int | None,
        success: bool | None,
        min_command_length: int | None,
    ) -> Iterable[dict[str, Any]]:
        """Stream history rows as entry dicts, newest first."""
        conditions: list[str] = []
        params: list[Any] = []
        if pattern is not None:
            conditions.append("command REGEXP ?")
            params.append(pattern)
        if success is not None:
            conditions.append("success = ?")
            params.append(1 if success else 0)
        if min_command_length is not None:
            conditions.append("length(command) >= ?")
            params.append(min_command_length)
        query = f"SELECT {_HISTORY_SELECT_COLUMNS} FROM history INDEXED BY {HISTORY_INDEX_NAME}"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += f" {_ORDER}"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        conn = self._connection()
        if conn is None:
            return
        try:
            # The WHERE conditions (success, length(command)) are not sargable,
            # so without the INDEXED BY hint sqlite plans a full table scan plus
            # a temp B-tree sort, defeating the index (see HISTORY_INDEX). Forcing
            # the index keeps the rows arriving already ordered, so the filters
            # run per scanned row and LIMIT stops the scan as soon as enough rows
            # matched. The index itself is ensured by _connection().
            for row in conn.execute(query, params):
                yield _row_to_entry(row)
        except sqlite3.Error:
            return
