"""History and saved queries plugins for Udan.

Provides the history and saved queries inserters, the history-item and
saved-item renders, and the saved-status/tag attributes of both item
kinds.

The plugin owns its configuration (``CONFIG``) and its storage backends: the
``PLUGIN`` declaration below is the package's container contribution, whose
factories select the storage implementation from the configured path
extension, so neither the config fields nor the selection logic leak into
udan core. ``SUBSCRIBE`` declares that the history logger records
CommandExecutedEvent; udan core resolves the service (the container first)
and wires that subscription on the bus.
"""

from collections.abc import Iterable
from datetime import datetime
from itertools import islice
from typing import Annotated

from udan.core.api_event_bus import CommandExecutedEvent
from udan.core.api_forests import Item
from udan.core.impl_constants import _NESTED_ITEM_TUPLE_SIZE
from udan.core_tools_loading.api_annotated import annotated
from udan.core_tools_loading.utils_str import cut_if_needed
from udan.decompof import Plugin, provide
from udan.plugins_history.api_history import DummyHistoryLogger, DummySavedQueries, HistoryLoggerAPI, SavedQueriesAPI
from udan.plugins_history.history_config import HistoryConfig
from udan.plugins_history.impl_history_jsonl import HistoryLogger
from udan.plugins_history.impl_history_sqlite import HistoryLoggerSqlite
from udan.plugins_history.impl_saved_jsonl import SavedQueriesJsonl
from udan.plugins_history.impl_saved_sqlite import SavedQueriesSqlite
from udan.plugins_tools_examples.plugins_builtins import greps

# ============ STORAGE SELECTION ============


def create_history_storage(history_path: str | None) -> HistoryLoggerAPI:
    """Select history storage implementation based on path extension.

    - ".jsonl" -> JSONL file-backed HistoryLogger
    - ".db" -> SQLite-backed HistoryLoggerSqlite
    - otherwise (or no path) -> DummyHistoryLogger (does nothing)
    """
    if history_path is None:
        return DummyHistoryLogger()
    if history_path.endswith(".jsonl"):
        return HistoryLogger(history_path=history_path)
    if history_path.endswith(".db"):
        return HistoryLoggerSqlite(history_path=history_path)
    return DummyHistoryLogger()


def create_saved_storage(saved_path: str | None) -> SavedQueriesAPI:
    """Select saved queries storage implementation based on path extension.

    - ".jsonl" -> JSONL file-backed SavedQueriesJsonl
    - ".db" -> SQLite-backed SavedQueriesSqlite
    - otherwise (or no path) -> DummySavedQueries (does nothing)
    """
    if saved_path is None:
        return DummySavedQueries()
    if saved_path.endswith(".jsonl"):
        return SavedQueriesJsonl(saved_path=saved_path)
    if saved_path.endswith(".db"):
        return SavedQueriesSqlite(saved_path=saved_path)
    return DummySavedQueries()


# ============ THE PACKAGE'S CONTRIBUTION ============


class HistoryPlugin(Plugin):
    """The history package's services, and the two verbs.

    The config is not a factory here: the container synthesizes one from the
    ``CONFIG`` declaration, so the config this plugin's factories read is the
    same instance a tool and ``udan config`` see. The storages are singletons,
    built on the first request and handed back unchanged after.
    """

    @provide
    def history_logger(self, config: HistoryConfig) -> HistoryLoggerAPI:
        """History storage selected by the configured path extension.

        - ".jsonl" -> JSONL file-backed HistoryLogger
        - ".db" -> SQLite-backed HistoryLoggerSqlite
        - otherwise -> DummyHistoryLogger (does nothing)
        """
        return create_history_storage(str(config.path))

    @provide
    def saved_storage(self, config: HistoryConfig) -> SavedQueriesAPI:
        """Saved queries storage selected by the configured path extension.

        - ".jsonl" -> JSONL file-backed SavedQueriesJsonl
        - ".db" -> SQLite-backed SavedQueriesSqlite
        - otherwise -> DummySavedQueries (does nothing)
        """
        return create_saved_storage(str(config.saved_path))

    def detach(self, history_logger: HistoryLoggerAPI, saved_storage: SavedQueriesAPI) -> None:
        """Close what the factories opened.

        The annotated parameters are dependencies: the container resolves them
        (building them if never built), the signature was validated at build.
        """
        history_logger.close()
        saved_storage.close()


DOMAIN = "history"
CONFIG = HistoryConfig
PLUGIN = HistoryPlugin
SUBSCRIBE = {CommandExecutedEvent: HistoryLoggerAPI}


# Constants
_HISTORY_COMMAND_TRUNCATION_LENGTH = 60  # Max length for failed commands in history display
_HISTORY_MIN_COMMAND_LENGTH = 5  # Commands shorter than this are hidden unless --all


def _tags_group(tags: list[str]) -> str:
    """Format tags as the bracketed comma-separated group used in renders"""
    return f" [{', '.join(tags)}]"


def _saved_entry(item: Item) -> dict | None:
    """Unwrap a saved query item (bare or nested ``(depth, dict)``) to its entry dict.

    Returns:
        The entry dict, or None when the item is not one.
    """
    if isinstance(item, tuple) and len(item) == _NESTED_ITEM_TUPLE_SIZE:
        _depth, item = item
    return item if isinstance(item, dict) else None


def _format_timestamp(timestamp: str | None) -> str:
    """Format an ISO timestamp as "YYYY-MM-DD HH:MM:SS"; fall back to the raw text."""
    timestamp = timestamp or ""
    try:
        dt = datetime.fromisoformat(timestamp)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return timestamp.split(".")[0] if "." in timestamp else timestamp


def _entry_text(entry: dict) -> str:
    """Text of a saved query record searched by the token filter: pattern name and query."""
    return " ".join(str(entry.get(field, "")) for field in ("pattern", "query"))


def _matches_tokens(entry: dict, tokens: list[str]) -> bool:
    """Check a saved query against vararg token conditions.

    A plain token must match the record: it is either one of its tags (exact)
    or is contained in its text (pattern name and query). A '-token' is
    negated - the record must neither have the tag nor contain the text.
    All conditions must hold (AND).
    """
    text = _entry_text(entry)
    tags = entry.get("tags", [])
    for token in tokens:
        if token.startswith("-"):
            token = token[1:]
            if token in tags or token in text:
                return False
        elif token not in tags and token not in text:
            return False
    return True


@annotated(
    meta={
        "tool_type": "inserter",
        "output_type": "saved_query",
        "supported_renders": ["saved-item"],
    }
)
def saved(
    patterns: Annotated[list[str] | None, "vararg"] = None,
    saved_storage: SavedQueriesAPI | None = None,
) -> Iterable[dict]:
    """Insert saved queries.

    Without arguments: list all saved queries.

    Positional patterns are interpreted as a filter, following the same '-'
    convention as the history inserter's patterns: a plain pattern must match
    the record, a '-pattern' must not; multiple patterns AND together. A
    pattern matches a record when it is one of its tags (exact - "demo" does
    not match "demo-run") or is contained in its text - the pattern name and
    the query. The saved-tags inserter lists the tags available for
    filtering; a pure text search over the raw records is available through
    the standard grep filter: ``saved, grep my-sort``.

    Entries are the stored saved query dicts; the saved-item render formats
    each one like a history-item line: ``[X] {create_date} [{tags}] :: {query}``,
    with the bracketed tag group omitted when the entry has no tags. The
    checkbox is always checked - every listed entry is saved by definition.
    Use ``tools/add_saved.py`` and ``tools/delete_saved.py``
    to manage entries too.

    Args:
        patterns: Optional vararg of filter patterns (a plain pattern must
              match the record, a '-pattern' must not). Default: None (list all).
        saved_storage: Saved queries storage (injected dependency)

    Returns:
        Iterable of saved query dicts with keys: pattern, query, tags, create_date, history_id

    Examples:
        >>> saved
        - [X] 2026-10-19 22:48:10 [demo, ux] :: range 100, sort, limit 10
        - [X] 2026-10-19 22:47:05 :: range 100, sort

        >>> saved demo
        - [X] 2026-10-19 22:48:10 [demo, ux] :: range 100, sort, limit 10

        >>> saved limit
        - [X] 2026-10-19 22:48:10 [demo, ux] :: range 100, sort, limit 10

        >>> saved demo ux
        - [X] 2026-10-19 22:48:10 [demo, ux] :: range 100, sort, limit 10

        >>> saved -demo
        - [X] 2026-10-19 22:47:05 :: range 100, sort

        >>> saved sort -limit
        - [X] 2026-10-19 22:47:05 :: range 100, sort
    """
    if saved_storage is None:
        return []

    entries = list(saved_storage.list_saved())
    if not patterns:
        return entries
    return [entry for entry in entries if _matches_tokens(entry, patterns)]


@annotated(meta={"tool_type": "inserter", "output_type": "str", "aliases": ["saved-tags"]})
def saved_tags_list(saved_storage: SavedQueriesAPI | None = None) -> Iterable[str]:
    """List the tags used by saved queries.

    Collects the tags of every stored record, drops duplicates and sorts them
    alphabetically. Feeds the tag filter of the saved inserter: pick a tag
    here, then run ``saved <tag>``.

    Args:
        saved_storage: Saved queries storage (injected dependency)

    Returns:
        Sorted distinct tags across all saved queries

    Examples:
        >>> saved-tags
        - demo
        - ux
    """
    if saved_storage is None:
        return []
    tags = {tag for entry in saved_storage.list_saved() for tag in entry.get("tags", [])}
    return sorted(tags)


@annotated(meta={"attribute_type": "simple"})
def history_saved(item: Item, saved_storage: SavedQueriesAPI | None = None) -> bool:
    """Is this history entry added to saved queries?

    An entry is saved when a saved query record referencing its
    history_id exists.

    Args:
        item: History entry dict (as produced by the history inserter).
        saved_storage: Saved queries storage (injected dependency)

    Returns:
        True if the entry is saved, False otherwise

    Example:
        >>> history, filter_by_attribute history_saved == True
        Show only history entries saved as saved queries
    """
    if saved_storage is None or not isinstance(item, dict):
        return False
    history_id = item.get("history_id")
    if history_id is None:
        return False
    return saved_storage.get_by_history_id(history_id) is not None


@annotated(meta={"attribute_type": "simple"})
def history_saved_tags(item: Item, saved_storage: SavedQueriesAPI | None = None) -> list[str]:
    """Tags of the saved query linked to this history entry.

    Empty when the entry is not saved.

    Args:
        item: History entry dict (as produced by the history inserter).
        saved_storage: Saved queries storage (injected dependency)

    Returns:
        Tag list of the linked saved query, [] when the entry is not saved

    Example:
        >>> history, filter_by_attribute history_saved_tags == [demo]
        Show only history entries saved with the tag "demo"
    """
    if saved_storage is None or not isinstance(item, dict):
        return []
    history_id = item.get("history_id")
    if history_id is None:
        return []
    saved = saved_storage.get_by_history_id(history_id)
    if saved is None:
        return []
    return list(saved.get("tags", []))


@annotated(meta={"attribute_type": "simple"})
def saved_saved(item: Item) -> bool:
    """Is this saved query record present in the saved queries storage?

    Every entry the saved inserter lists is a stored record, so the attribute
    is True for any listed entry.

    Args:
        item: Saved query dict (as produced by the saved inserter).

    Returns:
        True for a saved query record, False otherwise

    Example:
        >>> saved, filter_by_attribute saved_saved == True
        All listed saved queries (the listing only holds saved records)
    """
    return _saved_entry(item) is not None


@annotated(meta={"attribute_type": "simple"})
def saved_tags(item: Item) -> list[str]:
    """Tags of this saved query record.

    Args:
        item: Saved query dict (as produced by the saved inserter).

    Returns:
        Tag list of the record, [] for non-record items

    Example:
        >>> saved, filter_by_attribute saved_tags == [demo]
        Saved queries tagged "demo"
    """
    entry = _saved_entry(item)
    if entry is None:
        return []
    return list(entry.get("tags", []))


@annotated(meta={"item_type": "history_entry", "tool_type": "render", "aliases": ["history-item"]})
def render_history(item: Item, indent: str = "", saved_storage: SavedQueriesAPI | None = None) -> str:
    """Render history entry dictionary in formatted output.

    Formats history entries as a checkbox line with the entry's history id
    and, when the entry is saved, the tags of the linked saved query:
        - [X] [alice, bob] #42 {date} {ok/fail emoji} ({total} items) :: {query}
        - [X] #42 {date} {ok/fail emoji} ({total} items) :: {query}
        - [ ] {date} {ok/fail emoji} ({total} items) :: {query}

    The checkbox shows the saved status (see history_saved attribute) and the
    bracket group the tags (see history_saved_tags); both are omitted/empty
    when the entry is not saved. The #<id> part is present only when the
    entry has a history_id.

    Args:
        item: Either a dict with history data, or a tuple (depth, dict)
        indent: Indentation string
        saved_storage: Saved queries storage (injected dependency)

    Returns:
        Formatted string for history entry
    """
    # Handle tuple format (depth, dict) from nested inserters
    if isinstance(item, tuple) and len(item) == _NESTED_ITEM_TUPLE_SIZE:
        depth, item_data = item
    else:
        item_data = item

    if not isinstance(item_data, dict):
        return f"{indent}- {str(item_data)}"

    # Extract fields
    timestamp = item_data.get("timestamp", "")
    command = item_data.get("command", "")
    success = item_data.get("success", True)
    total_items = item_data.get("total_items", 0)
    error = item_data.get("error", "")

    # Format timestamp (remove microseconds for cleaner output)
    ts_str = _format_timestamp(timestamp)

    # Status indicator
    status = "🟢" if success else "🔴"

    # Saved checkbox, tags group and history id part
    checkbox = "[X]" if history_saved(item_data, saved_storage=saved_storage) else "[ ]"
    tags = history_saved_tags(item_data, saved_storage=saved_storage)
    history_id = item_data.get("history_id")
    id_part = f" #{history_id}" if history_id is not None else ""

    # Normalize command: replace newlines with spaces for oneline display
    command_oneline = command.replace("\n", " ")

    # For failed queries, show only start of command
    if not success:
        command_oneline = cut_if_needed(command_oneline, _HISTORY_COMMAND_TRUNCATION_LENGTH)

    # Format entry
    line = (
        f"{indent}- {checkbox}{_tags_group(tags)}{id_part} {ts_str} {status} ({total_items} items) :: {command_oneline}"
    )
    if error:
        error = cut_if_needed(error, _HISTORY_COMMAND_TRUNCATION_LENGTH)
        error = error.replace("\n", " ")
        line += f" - {error}"

    return line


@annotated(meta={"item_type": "saved_query", "tool_type": "render", "aliases": ["saved-item"]})
def render_saved(item: Item, indent: str = "") -> str:
    """Render a saved query dict like a history-item line.

    Formats saved queries as a checkbox line with the entry's create date and
    tag group:
        - [X] 2026-10-19 22:48:10 [demo] :: range 100, sort, limit 10
        - [X] 2026-10-19 22:47:05 :: range 100, sort

    The checkbox is always checked - every listed entry is a stored record.

    Args:
        item: A saved query dict, or a tuple (depth, dict)
        indent: Indentation string

    Returns:
        Formatted string for the saved query
    """
    entry = _saved_entry(item)
    if entry is None:
        return f"{indent}- {str(item)}"

    date_str = _format_timestamp(entry.get("create_date", ""))
    tags = entry.get("tags", [])
    return f"{indent}- [X] {date_str}{_tags_group(list(tags))} :: {entry.get('query', '')}"


@annotated(
    meta={
        "tool_type": "inserter",
        "supported_renders": ["history-item"],
        "output_type": "history_entry",
    }
)
def history(
    patterns: Annotated[list[str] | None, "vararg"] = None,
    limit: int | None = None,
    all: bool = False,
    history_logger: HistoryLoggerAPI | None = None,
) -> Iterable[dict]:
    """Insert recently executed commands from history.

    Shows command execution history including timestamp, command, success status,
    and item statistics. Commands are shown most recent first. Entries are
    produced lazily, so reading stops once enough entries have been consumed.

    By default, failed entries and entries whose command is shorter than
    5 characters are hidden; pass ``--all`` to see them.

    Positional patterns are interpreted as a filter with the same semantics as
    the builtins ``greps`` filter: an entry is kept when every pattern is
    contained in it, and a pattern prefixed with '-' excludes entries that
    contain it. All filtering happens before the limit is applied, so limit
    counts matching entries.

    The default hiding and the limit are pushed down into the history storage
    (``get_history``), so the storage applies them natively - as SQL
    WHERE/LIMIT for SQLite - instead of streaming every entry to Python.
    Only the greps-style patterns are applied here, since their per-entry
    semantics cannot be pushed down.

    By default, uses the 'history' render for formatted output. Use :raw to see
    the raw JSON objects.

    Args:
        patterns: Optional vararg of greps-style patterns to filter entries
                  (e.g. "history fruits -limit").
        limit: Maximum number of history entries to show (default: None = all entries).
        all: Also show failed entries and entries with commands shorter than
             5 characters (default: False = hide them).
        history_logger: History logger (injected dependency)

    Returns:
        Iterable of history entry dictionaries with keys: history_id, timestamp,
        command, success, total_items, depth_zero_items, error (if failed),
        comment (if provided)

    Example:
        >>> history
        - [ ] #12 2026-01-09 10:30:15 🟢 (5 items) :: fruits, limit 3, :list
        - [ ] #11 2026-01-09 10:29:45 🟢 (42 items) :: fruits

        >>> history fruits -limit
        - [ ] #11 2026-01-09 10:29:45 🟢 (42 items) :: fruits

        >>> history --all
        - [ ] #12 2026-01-09 10:30:15 🟢 (5 items) :: fruits, limit 3, :list
        - [ ] #11 2026-01-09 10:29:45 🟢 (42 items) :: fruits
        - [ ] #10 2026-01-09 10:28:30 🔴 (0 items) :: raiser - Test exception

        >>> history fruits --limit=5, :raw
        - {'history_id': 11, 'timestamp': '2026-01-09T10:29:45.123456', 'command': 'fruits', ...}
    """
    if history_logger is None:
        return []

    # Without patterns the storage can apply the limit natively; with patterns
    # limit must count entries surviving greps, so it is applied after them.
    entries = history_logger.get_history(
        success=None if all else True,
        min_command_length=None if all else _HISTORY_MIN_COMMAND_LENGTH,
        limit=None if patterns else limit,
    )
    if patterns:
        entries = (entry for entry in entries if greps(entry, patterns))
        if limit is not None and limit >= 0:
            entries = islice(entries, limit)
    return entries
