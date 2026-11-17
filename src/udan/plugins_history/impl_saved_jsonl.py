"""JSONL-backed saved queries storage for udan.

Stores saved queries in a JSONL file with one JSON object per line:
{"pattern": ..., "query": ..., "create_date": ...}
"""

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from udan.plugins_history.api_history import SavedQueriesAPI
from udan.plugins_history.impl_saved_tags import join_tags, split_tags


class SavedQueriesJsonl(SavedQueriesAPI):
    """Saved queries storage in a JSONL file.

    The parsed file is cached in memory keyed by the file mtime: the history
    render checks the saved status per entry, so without the cache every
    rendered line would re-read the whole file. Writes through this instance
    and external file changes refresh the cache.
    """

    def __init__(self, saved_path: str | None = None) -> None:
        """Initialize saved queries storage.

        Args:
            saved_path: Path to saved queries JSONL file. If None, storage is disabled.
        """
        self._saved_path = Path(saved_path).expanduser() if saved_path else None
        self._cache: list[dict] | None = None
        self._cache_stamp: int | None = None

    @property
    def saved_path(self) -> Path | None:
        """Get the saved queries file path.

        Returns:
            Path to saved queries JSONL file, or None if storage is disabled
        """
        return self._saved_path

    def _saved(self) -> list[dict]:
        """Get all saved queries in file order, cached between calls.

        Returns:
            Cached saved query dicts (without the guaranteed history_id key);
            refreshed when the file changed on disk or was written through
            this instance.
        """
        saved_path = self._saved_path
        if not saved_path or not saved_path.exists():
            self._cache = None
            return []
        stamp = saved_path.stat().st_mtime_ns
        if self._cache is None or self._cache_stamp != stamp:
            self._cache = self._read()
            self._cache_stamp = stamp
        return self._cache

    def _iter_entries(self) -> Iterable[dict]:
        """Yield saved queries from the JSONL file in file order, skipping bad lines."""
        if not self._saved_path or not self._saved_path.exists():
            return
        for line in self._saved_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict):
                yield entry

    def _read(self) -> list[dict]:
        """Read all saved queries from the JSONL file."""
        return list(self._iter_entries())

    def _write(self, entries: list[dict]) -> None:
        """Write all saved queries to the JSONL file."""
        if not self._saved_path:
            return
        self._saved_path.parent.mkdir(parents=True, exist_ok=True)
        self._saved_path.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in entries) + "\n")

    def _with_defaults(self, entry: dict) -> dict:
        """Guarantee the history_id and tags keys on a raw file entry."""
        return dict(entry, history_id=entry.get("history_id"), tags=split_tags(entry.get("tags")))

    def list_saved(self) -> Iterable[dict]:
        """Get all saved queries in insertion order.

        Returns:
            Iterable of saved query dicts with keys: pattern, query, tags, create_date, history_id
        """
        return [self._with_defaults(entry) for entry in self._saved()]

    def add(self, pattern: str, query: str, history_id: int | None = None, tags: list[str] | None = None) -> None:
        """Save a query.

        Args:
            pattern: Short name/pattern for the saved query.
            query: The full udan query text.
            history_id: Optional id of the history entry this query was saved from.
            tags: Optional tags for the saved query.
        """
        entries = list(self._saved())
        entry: dict = {
            "pattern": pattern,
            "query": query,
            "create_date": datetime.now(UTC).isoformat(),
        }
        if history_id is not None:
            entry["history_id"] = history_id
        if tags:
            entry["tags"] = join_tags(tags)
        entries.append(entry)
        self._write(entries)
        self._cache = None

    def delete(self, pattern: str) -> int:
        """Delete saved queries by exact pattern name.

        Args:
            pattern: Exact pattern name of the saved query(ies) to delete.

        Returns:
            Number of removed entries.
        """
        entries = list(self._saved())
        remaining = [e for e in entries if e.get("pattern") != pattern]
        removed = len(entries) - len(remaining)
        if removed:
            self._write(remaining)
            self._cache = None
        return removed

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
        for entry in self._saved():
            if entry.get("history_id") == history_id:
                return self._with_defaults(entry)
        return None

    def update_tags(self, history_id: int, tags: list[str]) -> int:
        """Update the tags of the saved queries linked to a history entry.

        Args:
            history_id: Id of the history entry the saved queries link to.
            tags: New tags (stored normalized as a space-separated string).

        Returns:
            Number of updated entries.
        """
        entries = list(self._saved())
        updated = 0
        for entry in entries:
            if entry.get("history_id") == history_id:
                entry["tags"] = join_tags(tags)
                updated += 1
        if updated:
            self._write(entries)
            self._cache = None
        return updated

    def update_tags_by_pattern(self, pattern: str, tags: list[str]) -> int:
        """Update the tags of the saved queries with a pattern name.

        Args:
            pattern: Exact pattern name of the saved queries to update.
            tags: New tags (stored normalized as a space-separated string).

        Returns:
            Number of updated entries.
        """
        entries = list(self._saved())
        updated = 0
        for entry in entries:
            if entry.get("pattern") == pattern:
                entry["tags"] = join_tags(tags)
                updated += 1
        if updated:
            self._write(entries)
            self._cache = None
        return updated

    def delete_by_history_id(self, history_id: int) -> int:
        """Delete saved queries linked to a history entry.

        Args:
            history_id: Id of the history entry.

        Returns:
            Number of removed entries.
        """
        entries = list(self._saved())
        remaining = [e for e in entries if e.get("history_id") != history_id]
        removed = len(entries) - len(remaining)
        if removed:
            self._write(remaining)
            self._cache = None
        return removed
