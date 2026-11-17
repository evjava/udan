"""SQLite-backed saved queries storage for udan.

Stores saved queries in a SQLite database. It is selected by the history
plugin when the configured saved path ends with ".db".
"""

import sqlite3
import threading
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from udan.plugins_history.api_history import SavedQueriesAPI
from udan.plugins_history.impl_saved_tags import join_tags, split_tags

SAVED_QUERIES_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS saved_queries ("
    " id INTEGER PRIMARY KEY,"
    " pattern TEXT NOT NULL,"
    " query TEXT NOT NULL,"
    " tags TEXT NOT NULL DEFAULT '',"
    " create_date TEXT NOT NULL,"
    " history_id INTEGER)"
)

# Speeds up delete-by-pattern and future pattern lookups.
SAVED_QUERIES_INDEX = "CREATE INDEX IF NOT EXISTS idx_saved_queries_pattern ON saved_queries(pattern)"

_SAVED_SELECT_COLUMNS = "pattern, query, tags, create_date, history_id"

# Pre-rename storage: a favorites.db next to the saved db is migrated once.
_LEGACY_FAVORITES_NAME = "favorites.db"
_LEGACY_FAVORITES_MIGRATED_NAME = "favorites.db.migrated"
_LEGACY_FAVORITES_SELECT = "SELECT pattern, query, create_date, history_id FROM favorites"


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Create table/index if needed and add the tags column to pre-existing dbs."""
    conn.execute(SAVED_QUERIES_SCHEMA)
    conn.execute(SAVED_QUERIES_INDEX)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(saved_queries)")}
    if "tags" not in columns:
        conn.execute("ALTER TABLE saved_queries ADD COLUMN tags TEXT NOT NULL DEFAULT ''")


def _row_to_saved(row: tuple) -> dict:
    """Convert a database row to a saved query dict."""
    pattern, query, tags, create_date, history_id = row
    return {
        "pattern": pattern,
        "query": query,
        "tags": split_tags(tags),
        "create_date": create_date,
        "history_id": history_id,
    }


def _migrate_legacy_favorites(conn: sqlite3.Connection, saved_path: Path) -> int:
    """Copy rows from a legacy favorites.db next to the saved db, then park it.

    Runs at most once per database file: callers invoke it only when the saved
    db did not exist yet, so the copy cannot duplicate rows. The legacy file is
    renamed after a successful copy so a later open never re-reads it.

    Returns:
        Number of migrated rows.
    """
    legacy_path = saved_path.parent / _LEGACY_FAVORITES_NAME
    if not legacy_path.exists():
        return 0
    legacy_conn = sqlite3.connect(legacy_path)
    try:
        rows = legacy_conn.execute(_LEGACY_FAVORITES_SELECT).fetchall()
    except sqlite3.Error:
        rows = []
    finally:
        legacy_conn.close()
    if not rows:
        return 0
    conn.executemany(
        "INSERT INTO saved_queries (pattern, query, tags, create_date, history_id) VALUES (?, ?, '', ?, ?)", rows
    )
    conn.commit()
    legacy_path.rename(saved_path.parent / _LEGACY_FAVORITES_MIGRATED_NAME)
    return len(rows)


class SavedQueriesSqlite(SavedQueriesAPI):
    """Saved queries storage in a SQLite database.

    The connection is opened once per thread and reused, and the (small)
    saved queries table is cached in memory keyed by the database file mtime:
    the history render checks the saved status per entry, so without the
    cache every rendered line would reopen the database. Writes through this
    instance and external file changes refresh the cache.

    A legacy favorites.db sitting next to the saved db is migrated into it
    the first time the saved db is opened (see _migrate_legacy_favorites).
    """

    def __init__(self, saved_path: str | None = None) -> None:
        """Initialize saved queries storage.

        Args:
            saved_path: Path to SQLite saved queries database. If None, storage is disabled.
        """
        self._saved_path = Path(saved_path).expanduser() if saved_path else None
        self._local = threading.local()
        self._cache: list[dict] | None = None
        self._cache_stamp: int | None = None

    @property
    def saved_path(self) -> Path | None:
        """Get the saved queries database path.

        Returns:
            Path to saved queries database, or None if storage is disabled
        """
        return self._saved_path

    def close(self) -> None:
        """Close this thread's live connection, if one is open.

        Idempotent: a second call, and a close before the first use, do
        nothing. The in-memory cache is dropped with it - a later read
        reopens the database and re-reads it.
        """
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
        self._cache = None
        self._cache_stamp = None

    def _connection(self, create: bool = False) -> sqlite3.Connection | None:
        """Return this thread's connection, opening it (and the schema) on first use.

        Args:
            create: When True, create the database file if missing (writes);
                when False, return None for a missing file so reads never
                create it - except to absorb a legacy favorites database.

        Returns:
            Open connection with the schema ensured, or None when storage is
            disabled or the database file does not exist.
        """
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            return conn
        saved_path = self._saved_path
        if not saved_path:
            return None
        was_missing = not saved_path.exists()
        if was_missing and not create and not (saved_path.parent / _LEGACY_FAVORITES_NAME).exists():
            return None
        if was_missing:
            saved_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(saved_path)
        _ensure_schema(conn)
        if was_missing:
            _migrate_legacy_favorites(conn, saved_path)
        self._local.conn = conn
        return conn

    def _saved(self) -> list[dict]:
        """Get all saved queries in insertion order, cached between calls.

        Returns:
            Cached saved query dicts; refreshed when the database file changed
            on disk or was written through this instance.
        """
        saved_path = self._saved_path
        if not saved_path:
            self._cache = None
            return []
        if not saved_path.exists():
            if not (saved_path.parent / _LEGACY_FAVORITES_NAME).exists():
                self._cache = None
                return []
            # First touch with a legacy favorites db next to it: absorb it.
            self._read_saved()
        stamp = saved_path.stat().st_mtime_ns
        if self._cache is None or self._cache_stamp != stamp:
            self._cache = self._read_saved()
            self._cache_stamp = stamp
        return self._cache

    def _read_saved(self) -> list[dict]:
        """Read all saved queries rows as dicts, empty list on database errors."""
        conn = self._connection()
        if conn is None:
            return []
        try:
            rows = conn.execute(f"SELECT {_SAVED_SELECT_COLUMNS} FROM saved_queries ORDER BY id").fetchall()
        except sqlite3.Error:
            return []
        return [_row_to_saved(row) for row in rows]

    def list_saved(self) -> Iterable[dict]:
        """Get all saved queries in insertion order.

        Returns:
            Iterable of saved query dicts with keys: pattern, query, tags, create_date, history_id
        """
        return list(self._saved())

    def add(self, pattern: str, query: str, history_id: int | None = None, tags: list[str] | None = None) -> None:
        """Save a query.

        Args:
            pattern: Short name/pattern for the saved query.
            query: The full udan query text.
            history_id: Optional id of the history entry this query was saved from.
            tags: Optional tags for the saved query.
        """
        if not self._saved_path:
            return
        try:
            conn = self._connection(create=True)
            if conn is None:
                return
            conn.execute(
                "INSERT INTO saved_queries (pattern, query, tags, create_date, history_id) VALUES (?, ?, ?, ?, ?)",
                (pattern, query, join_tags(tags), datetime.now(UTC).isoformat(), history_id),
            )
            conn.commit()
        except sqlite3.Error:
            # Fail silently if saved queries write fails
            pass
        finally:
            self._cache = None

    def delete(self, pattern: str) -> int:
        """Delete saved queries by exact pattern name.

        Args:
            pattern: Exact pattern name of the saved query(ies) to delete.

        Returns:
            Number of removed entries.
        """
        if not self._saved_path or not self._saved_path.exists():
            return 0
        try:
            conn = self._connection()
            if conn is None:
                return 0
            cursor = conn.execute("DELETE FROM saved_queries WHERE pattern = ?", (pattern,))
            conn.commit()
            removed = cursor.rowcount
        except sqlite3.Error:
            return 0
        finally:
            self._cache = None
        return max(removed, 0)

    def get_by_history_id(self, history_id: int) -> dict | None:
        """Get the first saved query linked to a history entry.

        Args:
            history_id: Id of the history entry.

        Returns:
            Saved query dict with keys: pattern, query, tags, create_date, history_id,
            or None if no saved query is linked to this history entry.
        """
        if history_id is None:
            return None
        for saved in self._saved():
            if saved.get("history_id") == history_id:
                return saved
        return None

    def update_tags(self, history_id: int, tags: list[str]) -> int:
        """Update the tags of the saved queries linked to a history entry.

        Args:
            history_id: Id of the history entry the saved queries link to.
            tags: New tags (stored normalized as a space-separated string).

        Returns:
            Number of updated entries.
        """
        if history_id is None:
            return 0
        if not self._saved_path or not self._saved_path.exists():
            return 0
        try:
            conn = self._connection()
            if conn is None:
                return 0
            cursor = conn.execute(
                "UPDATE saved_queries SET tags = ? WHERE history_id = ?",
                (join_tags(tags), history_id),
            )
            conn.commit()
            updated = cursor.rowcount
        except sqlite3.Error:
            return 0
        finally:
            self._cache = None
        return max(updated, 0)

    def update_tags_by_pattern(self, pattern: str, tags: list[str]) -> int:
        """Update the tags of the saved queries with a pattern name.

        Args:
            pattern: Exact pattern name of the saved queries to update.
            tags: New tags (stored normalized as a space-separated string).

        Returns:
            Number of updated entries.
        """
        if not self._saved_path or not self._saved_path.exists():
            return 0
        try:
            conn = self._connection()
            if conn is None:
                return 0
            cursor = conn.execute(
                "UPDATE saved_queries SET tags = ? WHERE pattern = ?",
                (join_tags(tags), pattern),
            )
            conn.commit()
            updated = cursor.rowcount
        except sqlite3.Error:
            return 0
        finally:
            self._cache = None
        return max(updated, 0)

    def delete_by_history_id(self, history_id: int) -> int:
        """Delete saved queries linked to a history entry.

        Args:
            history_id: Id of the history entry.

        Returns:
            Number of removed entries.
        """
        if not self._saved_path or not self._saved_path.exists():
            return 0
        try:
            conn = self._connection()
            if conn is None:
                return 0
            cursor = conn.execute("DELETE FROM saved_queries WHERE history_id = ?", (history_id,))
            conn.commit()
            removed = cursor.rowcount
        except sqlite3.Error:
            return 0
        finally:
            self._cache = None
        return max(removed, 0)
