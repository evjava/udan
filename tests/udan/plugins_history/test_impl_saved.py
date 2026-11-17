"""Tests for saved queries storage implementations and plugin storage selection.

Shared behaviour is verified against both saved queries storage implementations
(JSONL and SQLite) through the parametrized `saved_impl` fixture.
Behaviour specific to a single implementation is tested in the dedicated
sections below.
"""

import json
import os
import sqlite3
from pathlib import Path

import pytest

from udan.plugins_history.api_history import DummySavedQueries, SavedQueriesAPI
from udan.plugins_history.impl_saved_jsonl import SavedQueriesJsonl
from udan.plugins_history.impl_saved_sqlite import SavedQueriesSqlite
from udan.plugins_history.plugins_history import create_saved_storage

SAVED_IMPLS = [SavedQueriesJsonl, SavedQueriesSqlite]

# Storage filenames matching the extensions the history plugin dispatches on
_SAVED_FILENAMES = {SavedQueriesJsonl: "saved.jsonl", SavedQueriesSqlite: "saved.db"}

_LEGACY_DB_NAME = "favorites.db"
_LEGACY_MIGRATED_NAME = "favorites.db.migrated"


@pytest.fixture(params=SAVED_IMPLS, ids=["jsonl", "sqlite"])
def saved_impl(request) -> type[SavedQueriesAPI]:
    """Fixture providing both saved queries storage implementations."""
    return request.param


def _saved_path(saved_impl: type[SavedQueriesAPI], tmp_path) -> str:
    """Build a storage path for the implementation under test."""
    return str(tmp_path / _SAVED_FILENAMES[saved_impl])


@pytest.fixture
def saved_storage(saved_impl, tmp_path) -> SavedQueriesAPI:
    """Fixture providing a saved queries storage over a temporary storage path."""
    return saved_impl(saved_path=_saved_path(saved_impl, tmp_path))


def _write_legacy_favorites_db(tmp_path, rows: list[tuple]) -> Path:
    """Create a legacy favorites.db with the pre-rename schema and rows."""
    legacy_path = tmp_path / _LEGACY_DB_NAME
    conn = sqlite3.connect(legacy_path)
    try:
        conn.execute(
            "CREATE TABLE favorites ("
            " id INTEGER PRIMARY KEY,"
            " pattern TEXT NOT NULL,"
            " query TEXT NOT NULL,"
            " create_date TEXT NOT NULL,"
            " history_id INTEGER)"
        )
        conn.executemany("INSERT INTO favorites (pattern, query, create_date, history_id) VALUES (?, ?, ?, ?)", rows)
        conn.commit()
    finally:
        conn.close()
    return legacy_path


# --- Shared SavedQueries API behaviour (both implementations) ---


def test_saved_add_and_list(saved_storage):
    """Test that storage saves and lists entries in insertion order."""
    saved_storage.add("my-sort", "range 100, sort")
    saved_storage.add("my-limit", "range 50, limit 5")

    saved = list(saved_storage.list_saved())
    assert len(saved) == 2
    assert set(saved[0].keys()) == {"pattern", "query", "tags", "create_date", "history_id"}
    assert saved[0]["pattern"] == "my-sort"
    assert saved[0]["query"] == "range 100, sort"
    assert saved[0]["tags"] == []
    assert saved[0]["history_id"] is None
    assert saved[1]["pattern"] == "my-limit"
    assert "create_date" in saved[0]


def test_saved_delete(saved_storage):
    """Test that delete removes entries by exact pattern and reports count."""
    saved_storage.add("my-sort", "range 100, sort")
    saved_storage.add("my-sort", "range 200, sort")
    saved_storage.add("other", "vars")

    removed = saved_storage.delete("my-sort")
    assert removed == 2

    saved = list(saved_storage.list_saved())
    assert len(saved) == 1
    assert saved[0]["pattern"] == "other"

    # Deleting non-existent pattern removes nothing
    assert saved_storage.delete("my-sort") == 0


def test_saved_missing_storage_returns_empty(saved_impl, tmp_path):
    """Test that list_saved returns nothing when the storage does not exist."""
    storage = saved_impl(saved_path=str(tmp_path / "missing" / _SAVED_FILENAMES[saved_impl]))

    assert list(storage.list_saved()) == []


def test_saved_disabled(saved_impl):
    """Test that storage does nothing when path is None."""
    storage = saved_impl(saved_path=None)

    storage.add("my-sort", "range 100, sort")

    assert list(storage.list_saved()) == []
    assert storage.delete("my-sort") == 0


def test_saved_history_id(saved_storage):
    """Test that history_id is stored, nullable, and returned."""
    saved_storage.add("linked", "vars", history_id=42)
    saved_storage.add("unlinked", "history")

    saved = list(saved_storage.list_saved())
    assert saved[0]["history_id"] == 42
    assert saved[1]["history_id"] is None


def test_saved_add_with_tags(saved_storage):
    """Test that tags are stored and returned as a normalized list."""
    saved_storage.add("tagged", "vars", tags=["alice", "bob"])
    saved_storage.add("untagged", "history")

    saved = list(saved_storage.list_saved())
    assert saved[0]["tags"] == ["alice", "bob"]
    assert saved[1]["tags"] == []


def test_saved_add_normalizes_tags(saved_storage):
    """Test that add() dedupes, strips brackets, and splits commas in tags."""
    saved_storage.add("tagged", "vars", tags=["b", "a", "b", "[c]", "a,b"])

    saved = list(saved_storage.list_saved())
    assert saved[0]["tags"] == ["b", "a", "c"]


def test_saved_update_tags(saved_storage):
    """Test that update_tags updates every entry linked to the history id."""
    saved_storage.add("first", "vars", history_id=42)
    saved_storage.add("second", "history", history_id=42)
    saved_storage.add("other", "range 5", history_id=43)

    updated = saved_storage.update_tags(42, ["x", "y"])

    assert updated == 2
    saved = list(saved_storage.list_saved())
    assert saved[0]["tags"] == ["x", "y"]
    assert saved[1]["tags"] == ["x", "y"]
    assert saved[2]["tags"] == []


def test_saved_update_tags_clears_on_empty(saved_storage):
    """Test that update_tags with an empty list clears the tags."""
    saved_storage.add("tagged", "vars", history_id=42, tags=["alice"])

    assert saved_storage.update_tags(42, []) == 1

    assert saved_storage.get_by_history_id(42)["tags"] == []


def test_saved_update_tags_without_linked_entries(saved_storage):
    """Test that update_tags reports 0 when nothing is linked."""
    saved_storage.add("unlinked", "vars")

    assert saved_storage.update_tags(42, ["x"]) == 0


def test_saved_update_tags_missing_storage(saved_impl, tmp_path):
    """Test that update_tags returns 0 when the storage does not exist."""
    storage = saved_impl(saved_path=str(tmp_path / "missing" / _SAVED_FILENAMES[saved_impl]))

    assert storage.update_tags(1, ["x"]) == 0


def test_saved_get_by_history_id(saved_storage):
    """Test that get_by_history_id finds the linked saved query or returns None."""
    assert saved_storage.get_by_history_id(42) is None

    saved_storage.add("linked", "vars", history_id=42)
    saved_storage.add("unlinked", "history")

    saved = saved_storage.get_by_history_id(42)
    assert saved is not None
    assert saved["pattern"] == "linked"
    assert saved["query"] == "vars"
    assert saved["history_id"] == 42

    assert saved_storage.get_by_history_id(43) is None


def test_saved_get_by_history_id_missing_storage(saved_impl, tmp_path):
    """Test that get_by_history_id returns None when the storage does not exist."""
    storage = saved_impl(saved_path=str(tmp_path / "missing" / _SAVED_FILENAMES[saved_impl]))

    assert storage.get_by_history_id(1) is None


def test_saved_cache_refreshed_on_external_write(saved_impl, tmp_path):
    """Test that lookups see saved queries written by another storage instance.

    The storages cache the saved queries list between calls (the history render
    checks the saved status per entry); the cache must not hide entries
    written behind its back, e.g. by tools/add_saved.py.
    """
    storage_path = _saved_path(saved_impl, tmp_path)
    writer = saved_impl(saved_path=storage_path)
    writer.add("one", "vars", history_id=1)

    reader = saved_impl(saved_path=storage_path)
    assert reader.get_by_history_id(2) is None  # fills the cache

    writer.add("two", "range 5", history_id=2)
    # Coarse filesystem timestamp granularity can collapse two rapid writes
    # into one mtime; pin a later mtime so the change is detectable.
    stamp = Path(storage_path).stat().st_mtime_ns
    os.utime(storage_path, ns=((stamp + 1_000_000),) * 2)

    saved = reader.get_by_history_id(2)
    assert saved is not None
    assert saved["pattern"] == "two"


def test_saved_delete_by_history_id(saved_storage):
    """Test that delete_by_history_id removes only linked saved queries."""
    saved_storage.add("first", "vars", history_id=42)
    saved_storage.add("second", "history", history_id=42)
    saved_storage.add("other", "range 5", history_id=43)
    saved_storage.add("unlinked", "ls_files")

    removed = saved_storage.delete_by_history_id(42)
    assert removed == 2

    saved = list(saved_storage.list_saved())
    assert [s["pattern"] for s in saved] == ["other", "unlinked"]

    # Deleting non-linked history_id removes nothing
    assert saved_storage.delete_by_history_id(42) == 0


def test_saved_delete_by_history_id_missing_storage(saved_impl, tmp_path):
    """Test that delete_by_history_id returns 0 when the storage does not exist."""
    storage = saved_impl(saved_path=str(tmp_path / "missing" / _SAVED_FILENAMES[saved_impl]))

    assert storage.delete_by_history_id(1) == 0


# --- JSONL implementation specifics ---


def test_saved_jsonl_omits_unset_history_id_on_disk(tmp_path):
    """Test that JSONL storage omits history_id from disk when it is not set."""
    jsonl_path = tmp_path / "saved.jsonl"

    storage = SavedQueriesJsonl(saved_path=str(jsonl_path))
    storage.add("linked", "vars", history_id=7)
    storage.add("unlinked", "history")

    lines = jsonl_path.read_text().strip().splitlines()
    assert json.loads(lines[0])["history_id"] == 7
    assert "history_id" not in json.loads(lines[1])


def test_saved_jsonl_stores_normalized_tags_on_disk(tmp_path):
    """Test that JSONL storage omits empty tags and stores them normalized."""
    jsonl_path = tmp_path / "saved.jsonl"

    storage = SavedQueriesJsonl(saved_path=str(jsonl_path))
    storage.add("tagged", "vars", tags=["b", "a", "b"])
    storage.add("untagged", "history")

    lines = jsonl_path.read_text().strip().splitlines()
    assert json.loads(lines[0])["tags"] == "b a"
    assert "tags" not in json.loads(lines[1])


# --- SQLite implementation specifics: legacy favorites migration ---


def test_sqlite_migrates_legacy_favorites_db_on_first_read(tmp_path):
    """Test that a legacy favorites.db next to the saved db is absorbed on read."""
    _write_legacy_favorites_db(tmp_path, [("kept", "range 5", "2026-01-01T00:00:00", 7)])
    storage = SavedQueriesSqlite(saved_path=str(tmp_path / "saved.db"))

    saved = list(storage.list_saved())

    assert saved == [
        {"pattern": "kept", "query": "range 5", "tags": [], "create_date": "2026-01-01T00:00:00", "history_id": 7}
    ]
    assert not (tmp_path / _LEGACY_DB_NAME).exists()
    assert (tmp_path / _LEGACY_MIGRATED_NAME).exists()


def test_sqlite_alters_preexisting_table_without_tags(tmp_path):
    """Test that a pre-tags saved_queries table is upgraded via ALTER TABLE."""
    db_path = str(tmp_path / "saved.db")

    # Simulate a db created before the tags column existed
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE saved_queries ("
            " id INTEGER PRIMARY KEY,"
            " pattern TEXT NOT NULL,"
            " query TEXT NOT NULL,"
            " create_date TEXT NOT NULL,"
            " history_id INTEGER)"
        )
        conn.execute("INSERT INTO saved_queries (pattern, query, create_date) VALUES ('old', 'vars', '2026-01-01')")
        conn.commit()
    finally:
        conn.close()

    storage = SavedQueriesSqlite(saved_path=db_path)
    storage.add("tagged", "range 5", tags=["new"])

    saved = list(storage.list_saved())
    assert len(saved) == 2
    assert saved[0]["pattern"] == "old"
    assert saved[0]["tags"] == []
    assert saved[1]["pattern"] == "tagged"
    assert saved[1]["tags"] == ["new"]


def test_sqlite_migration_runs_once(tmp_path):
    """Test that the migrated legacy file is never re-read."""
    _write_legacy_favorites_db(tmp_path, [("kept", "range 5", "2026-01-01T00:00:00", 7)])
    storage = SavedQueriesSqlite(saved_path=str(tmp_path / "saved.db"))
    assert len(list(storage.list_saved())) == 1

    storage.delete("kept")

    assert list(storage.list_saved()) == []


def test_sqlite_no_db_created_on_read_without_legacy(tmp_path):
    """Test that reads do not create the saved db when there is nothing to migrate."""
    storage = SavedQueriesSqlite(saved_path=str(tmp_path / "saved.db"))

    assert storage.get_by_history_id(1) is None

    assert not (tmp_path / "saved.db").exists()


def test_sqlite_no_migration_without_legacy_rows(tmp_path):
    """Test that a legacy db without a readable favorites table is left alone."""
    conn = sqlite3.connect(tmp_path / _LEGACY_DB_NAME)
    try:
        conn.execute("CREATE TABLE other (id INTEGER PRIMARY KEY)")
        conn.commit()
    finally:
        conn.close()
    storage = SavedQueriesSqlite(saved_path=str(tmp_path / "saved.db"))

    assert list(storage.list_saved()) == []
    assert (tmp_path / _LEGACY_DB_NAME).exists()
    assert not (tmp_path / _LEGACY_MIGRATED_NAME).exists()


# --- Factory selection and dummy implementation ---


def test_create_saved_storage_jsonl(tmp_path):
    """Test that factory selects JSONL storage for .jsonl path."""
    storage = create_saved_storage(str(tmp_path / "saved.jsonl"))

    assert isinstance(storage, SavedQueriesJsonl)


def test_create_saved_storage_db(tmp_path):
    """Test that factory selects SQLite storage for .db path."""
    storage = create_saved_storage(str(tmp_path / "saved.db"))

    assert isinstance(storage, SavedQueriesSqlite)


def test_create_saved_storage_unknown_extension(tmp_path):
    """Test that factory selects dummy storage for unrecognized path."""
    storage = create_saved_storage(str(tmp_path / "saved.txt"))

    assert isinstance(storage, DummySavedQueries)


def test_create_saved_storage_none():
    """Test that factory selects dummy storage when path is None."""
    assert isinstance(create_saved_storage(None), DummySavedQueries)


def test_dummy_saved_queries_does_nothing():
    """Test that dummy storage does nothing and returns empty saved queries."""
    storage = DummySavedQueries()

    storage.add("my-sort", "range 100, sort")

    assert list(storage.list_saved()) == []
    assert storage.delete("my-sort") == 0


def test_dummy_saved_queries_history_id_methods():
    """Test that dummy storage history_id methods are no-ops."""
    storage = DummySavedQueries()

    assert storage.get_by_history_id(1) is None
    assert storage.delete_by_history_id(1) == 0
