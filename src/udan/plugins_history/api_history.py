"""Public API for command history and saved queries.

This module defines the API interfaces for history logging and saved
queries storage, plus no-op dummy implementations used when the storages
are disabled.
"""

from collections.abc import Iterable

from udan.core.api_forests import Forest


class HistoryLoggerAPI:
    """API interface for command history logging.

    This class defines the public API for accessing command execution history.
    """

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
        raise NotImplementedError

    def get_history(
        self,
        pattern: str | None = None,
        limit: int | None = None,
        success: bool | None = None,
        min_command_length: int | None = None,
    ) -> Iterable[dict]:
        """Get recent command execution history.

        Implementations apply the filters natively (e.g. SQL WHERE/LIMIT for
        SQLite), so callers should forward filters here instead of filtering
        the returned iterable themselves.

        Args:
            limit: Maximum number of entries to return (default: None = all entries).
                   Pass a positive integer to limit results. A negative value is
                   treated as no limit.
            pattern: Optional regex pattern to filter history entries by command text.
                     Only entries whose command matches the pattern are returned.
            success: Optional success status to filter by; only entries with this
                     status are returned (default: None = any status).
            min_command_length: Optional minimum command length; only entries whose
                     command is at least this many characters are returned
                     (default: None = no minimum).

        Returns:
            Iterable of history entry dictionaries, newest first. Implementations
            may return a lazy iterable that reads entries on demand, so entries
            beyond `limit` are never produced.

            Each entry dict has keys:
            - history_id: Row id of the entry in the history storage
            - timestamp: ISO timestamp string
            - command: Query/command that was executed
            - success: Boolean indicating success
            - total_items: Total number of items in result
            - depth_zero_items: Number of items at depth 0
        """
        raise NotImplementedError

    def close(self) -> None:
        """Release what the backend holds open.

        A no-op on the base: a backend that holds nothing open (the dummy, the
        jsonl file-per-access ones) inherits it, and a backend with a live
        resource overrides it. Called by the plugin's detach.
        """


class SavedQueriesAPI:
    """API interface for saved queries storage.

    Each saved query is a dict with keys: pattern (short name), query (full
    query text), tags (list of tag strings), create_date (ISO timestamp),
    history_id (optional link to the history entry this query was saved
    from, None if unset).
    """

    def list_saved(self) -> Iterable[dict]:
        """Get all saved queries in insertion order.

        Returns:
            Iterable of saved query dicts with keys: pattern, query, tags, create_date, history_id
        """
        raise NotImplementedError

    def add(self, pattern: str, query: str, history_id: int | None = None, tags: list[str] | None = None) -> None:
        """Save a query.

        Args:
            pattern: Short name/pattern for the saved query.
            query: The full udan query text.
            history_id: Optional id of the history entry this query was saved from.
            tags: Optional tags for the saved query.
        """
        raise NotImplementedError

    def delete(self, pattern: str) -> int:
        """Delete saved queries by exact pattern name.

        Args:
            pattern: Exact pattern name of the saved query(ies) to delete.

        Returns:
            Number of removed entries.
        """
        raise NotImplementedError

    def get_by_history_id(self, history_id: int) -> dict | None:
        """Get the first saved query linked to a history entry.

        Args:
            history_id: Id of the history entry.

        Returns:
            Saved query dict with keys: pattern, query, tags, create_date, history_id,
            or None if no saved query is linked to this history entry.
        """
        raise NotImplementedError

    def update_tags(self, history_id: int, tags: list[str]) -> int:
        """Update the tags of the saved queries linked to a history entry.

        Args:
            history_id: Id of the history entry the saved queries link to.
            tags: New tags (normalized to a space-separated string in storage).

        Returns:
            Number of updated entries.
        """
        raise NotImplementedError

    def update_tags_by_pattern(self, pattern: str, tags: list[str]) -> int:
        """Update the tags of the saved queries with a pattern name.

        The tags counterpart of delete(pattern): records without a history
        link are identified by their pattern name.

        Args:
            pattern: Exact pattern name of the saved queries to update.
            tags: New tags (normalized to a space-separated string in storage).

        Returns:
            Number of updated entries.
        """
        raise NotImplementedError

    def delete_by_history_id(self, history_id: int) -> int:
        """Delete saved queries linked to a history entry.

        Args:
            history_id: Id of the history entry.

        Returns:
            Number of removed entries.
        """
        raise NotImplementedError

    def close(self) -> None:
        """Release what the backend holds open.

        A no-op on the base, like HistoryLoggerAPI.close: called by the
        plugin's detach, which closes every storage its factories opened.
        """


class DummyHistoryLogger(HistoryLoggerAPI):
    """No-op history logger.

    Used when history is disabled (no path configured) or when the
    history path extension is not recognized by any implementation.
    """

    def log(
        self,
        command: str,
        success: bool,
        forest: Forest,
        error: str | None = None,
        comment: str | None = None,
    ) -> None:
        """Do nothing - history logging is disabled."""

    def get_history(
        self,
        pattern: str | None = None,
        limit: int | None = None,
        success: bool | None = None,
        min_command_length: int | None = None,
    ) -> Iterable[dict]:
        """Return empty history.

        Args:
            pattern: Optional regex pattern (ignored)
            limit: Maximum number of entries (ignored)
            success: Optional success status filter (ignored)
            min_command_length: Optional minimum command length filter (ignored)

        Returns:
            Empty iterable
        """
        return []


class DummySavedQueries(SavedQueriesAPI):
    """No-op saved queries storage.

    Used when saved queries are disabled (no path configured) or when the
    saved path extension is not recognized by any implementation.
    """

    def list_saved(self) -> Iterable[dict]:
        """Return empty saved queries.

        Returns:
            Empty iterable
        """
        return []

    def add(self, pattern: str, query: str, history_id: int | None = None, tags: list[str] | None = None) -> None:
        """Do nothing - saved queries storage is disabled."""

    def delete(self, pattern: str) -> int:
        """Do nothing - saved queries storage is disabled.

        Returns:
            0
        """
        return 0

    def get_by_history_id(self, history_id: int) -> dict | None:
        """Do nothing - saved queries storage is disabled.

        Returns:
            None
        """
        return None

    def update_tags(self, history_id: int, tags: list[str]) -> int:
        """Do nothing - saved queries storage is disabled.

        Returns:
            0
        """
        return 0

    def update_tags_by_pattern(self, pattern: str, tags: list[str]) -> int:
        """Do nothing - saved queries storage is disabled.

        Returns:
            0
        """
        return 0

    def delete_by_history_id(self, history_id: int) -> int:
        """Do nothing - saved queries storage is disabled.

        Returns:
            0
        """
        return 0
