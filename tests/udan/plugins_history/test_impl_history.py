"""Tests for command history logging.

Shared behaviour is verified against both History API implementations (JSONL and
SQLite) through the parametrized `history_impl` fixture. Behaviour specific to a
single implementation is tested in the dedicated sections below.
"""

import sqlite3

import pytest

from tests.conftest import make_qp
from udan.core.api_forests import EMPTY_FOREST, Forest
from udan.core.config import UdanConfig
from udan.core.impl_ioc import create_udan_container
from udan.core.impl_udan_context import UdanContext
from udan.core_tools_loading.impl_tools_loader import ToolsLoader
from udan.plugins_history.api_history import DummyHistoryLogger, HistoryLoggerAPI
from udan.plugins_history.history_config import HistoryConfig
from udan.plugins_history.impl_history_jsonl import HistoryLogger, _iter_lines_reversed
from udan.plugins_history.impl_history_sqlite import HistoryLoggerSqlite
from udan.plugins_history.plugins_history import create_history_storage
from udan.plugins_tools_core import plugins_system
from udan.plugins_tools_examples import plugins_builtins

HISTORY_IMPLS = [HistoryLogger, HistoryLoggerSqlite]

# Storage filenames matching the extensions the history plugin dispatches on
_HISTORY_FILENAMES = {HistoryLogger: "history.jsonl", HistoryLoggerSqlite: "history.db"}


@pytest.fixture(params=HISTORY_IMPLS, ids=["jsonl", "sqlite"])
def history_impl(request) -> type[HistoryLoggerAPI]:
    """Fixture providing both History API implementations."""
    return request.param


def _history_path(history_impl: type[HistoryLoggerAPI], tmp_path) -> str:
    """Build a storage path for the implementation under test."""
    return str(tmp_path / _HISTORY_FILENAMES[history_impl])


@pytest.fixture
def history_logger(history_impl, tmp_path) -> HistoryLoggerAPI:
    """Fixture providing a history logger over a temporary storage path."""
    return history_impl(history_path=_history_path(history_impl, tmp_path))


# --- Shared History API behaviour (both implementations) ---


def test_history_logger_creates_storage(history_logger):
    """Test that logging creates the storage with a complete entry."""
    history_logger.log("test command", success=True, forest=EMPTY_FOREST)

    assert history_logger.history_path.exists(), "History storage should be created"

    entry = list(history_logger.get_history())[0]
    assert entry["command"] == "test command"
    assert entry["success"] is True
    assert entry["total_items"] == 0
    assert entry["depth_zero_items"] == 0
    assert "timestamp" in entry


def test_history_logger_appends_entries(history_logger):
    """Test that multiple entries are stored and read back newest first."""
    history_logger.log("command 1", success=True, forest=EMPTY_FOREST)
    history_logger.log("command 2", success=False, forest=EMPTY_FOREST, error="test error")

    history = list(history_logger.get_history())
    assert len(history) == 2

    assert history[0]["command"] == "command 2"
    assert history[0]["success"] is False
    assert history[0]["error"] == "test error"

    assert history[1]["command"] == "command 1"
    assert history[1]["success"] is True
    assert "error" not in history[1]


def test_history_logger_disabled(history_impl):
    """Test that a logger without a path does nothing and reads empty."""
    logger = history_impl(history_path=None)
    logger.log("test command", success=True, forest=EMPTY_FOREST)

    assert list(logger.get_history()) == []


def test_history_logger_calculates_statistics(history_logger):
    """Test that the logger correctly calculates item statistics."""
    forest = Forest(depths=[0, 1, 0, 2, 0, 1], items=[1, 2, 3, 4, 5, 6])
    history_logger.log("test", success=True, forest=forest)

    entry = list(history_logger.get_history())[0]
    assert entry["total_items"] == 6
    assert entry["depth_zero_items"] == 3  # Items at depth 0


def test_history_get_history(history_logger):
    """Test reading history entries."""
    history_logger.log("command 1", success=True, forest=EMPTY_FOREST)
    history_logger.log("command 2", success=True, forest=EMPTY_FOREST)
    history_logger.log("command 3", success=True, forest=EMPTY_FOREST)

    history = list(history_logger.get_history(limit=10))

    assert len(history) == 3
    # Should be in reverse order (newest first)
    assert history[0]["command"] == "command 3"
    assert history[1]["command"] == "command 2"
    assert history[2]["command"] == "command 1"


def test_history_get_history_respects_limit(history_logger):
    """Test that get_history respects the limit parameter."""
    for i in range(10):
        history_logger.log(f"command {i}", success=True, forest=EMPTY_FOREST)

    history = list(history_logger.get_history(limit=5))

    assert len(history) == 5
    # Should get the 5 most recent
    assert history[0]["command"] == "command 9"
    assert history[4]["command"] == "command 5"


def test_history_get_history_with_pattern(history_logger):
    """Test that get_history filters by pattern."""
    history_logger.log("fruits", success=True, forest=EMPTY_FOREST)
    history_logger.log("vars", success=True, forest=EMPTY_FOREST)
    history_logger.log("fruits deep", success=True, forest=EMPTY_FOREST)
    history_logger.log("history", success=True, forest=EMPTY_FOREST)

    # Filter by exact substring
    history = list(history_logger.get_history(pattern="fruits"))
    assert len(history) == 2
    assert all("fruits" in e["command"] for e in history)

    # Filter by regex pattern
    history = list(history_logger.get_history(pattern="^var"))
    assert len(history) == 1
    assert history[0]["command"] == "vars"

    # No match
    history = list(history_logger.get_history(pattern="nonexistent"))
    assert len(history) == 0

    # Pattern with limit
    history = list(history_logger.get_history(limit=1, pattern="fruits"))
    assert len(history) == 1
    assert history[0]["command"] == "fruits deep"  # newest first


def test_history_get_history_filters_by_success(history_logger):
    """Test that the success filter is applied by the storage itself."""
    history_logger.log("good command", success=True, forest=EMPTY_FOREST)
    history_logger.log("bad command", success=False, forest=EMPTY_FOREST, error="boom")

    assert [e["command"] for e in history_logger.get_history(success=True)] == ["good command"]
    assert [e["command"] for e in history_logger.get_history(success=False)] == ["bad command"]


def test_history_get_history_filters_by_min_command_length(history_logger):
    """Test that the min_command_length filter is applied by the storage itself."""
    history_logger.log("ab", success=True, forest=EMPTY_FOREST)
    history_logger.log("abcde", success=True, forest=EMPTY_FOREST)
    history_logger.log("abcdef", success=True, forest=EMPTY_FOREST)

    history = list(history_logger.get_history(min_command_length=5))

    # Newest first; the short entry never leaves the storage
    assert [e["command"] for e in history] == ["abcdef", "abcde"]


def test_history_get_history_filters_combine_with_limit(history_logger):
    """Test that limit counts entries surviving the visibility filters."""
    history_logger.log("short", success=True, forest=EMPTY_FOREST)
    history_logger.log("failed command", success=False, forest=EMPTY_FOREST, error="x")
    history_logger.log("first good command", success=True, forest=EMPTY_FOREST)
    history_logger.log("second good command", success=True, forest=EMPTY_FOREST)

    history = list(history_logger.get_history(success=True, min_command_length=5, limit=2))

    assert [e["command"] for e in history] == ["second good command", "first good command"]


def test_history_get_history_missing_storage_returns_empty(history_impl, tmp_path):
    """Test that get_history returns nothing when the storage does not exist."""
    logger = history_impl(history_path=str(tmp_path / "missing" / _HISTORY_FILENAMES[history_impl]))

    assert list(logger.get_history()) == []


def test_history_get_history_is_lazy(history_logger):
    """Test that get_history returns a lazy iterable, not a materialized list."""
    for i in range(3):
        history_logger.log(f"command {i}", success=True, forest=EMPTY_FOREST)

    history = history_logger.get_history()

    assert not isinstance(history, list)
    assert [e["command"] for e in history] == ["command 2", "command 1", "command 0"]


def test_history_get_history_zero_limit_returns_nothing(history_logger):
    """Test that a zero limit yields no entries."""
    history_logger.log("command", success=True, forest=EMPTY_FOREST)

    assert list(history_logger.get_history(limit=0)) == []


def test_history_get_history_negative_limit_means_unlimited(history_logger):
    """Test that a negative limit is treated as no limit."""
    for i in range(3):
        history_logger.log(f"command {i}", success=True, forest=EMPTY_FOREST)

    history = list(history_logger.get_history(limit=-1))

    assert [e["command"] for e in history] == ["command 2", "command 1", "command 0"]


def test_history_path_expansion(history_impl, tmp_path, monkeypatch):
    """Test that the logger expands ~ in path."""
    monkeypatch.setenv("HOME", str(tmp_path))
    history_path = "~/udan_test/" + _HISTORY_FILENAMES[history_impl]

    logger = history_impl(history_path=history_path)
    logger.log("test", success=True, forest=EMPTY_FOREST)

    expected_path = tmp_path / "udan_test" / _HISTORY_FILENAMES[history_impl]
    assert expected_path.exists(), "History storage should be created with expanded path"


# --- JSONL implementation specifics ---


def test_history_jsonl_get_history_skips_malformed_lines(tmp_path):
    """Test that lines which are not valid JSON objects are skipped."""
    history_path = tmp_path / "history.jsonl"
    history_path.write_text(
        "{broken\n"
        '["not", "an", "object"]\n'
        '{"timestamp": "2026-01-09T10:00:01", "command": "good 1", "success": true,'
        ' "total_items": 0, "depth_zero_items": 0}\n'
        '{"timestamp": "2026-01-09T10:00:02", "command": "good 2", "success": true,'
        ' "total_items": 0, "depth_zero_items": 0}\n'
    )

    logger = HistoryLogger(history_path=str(history_path))

    assert [e["command"] for e in logger.get_history()] == ["good 2", "good 1"]


def test_iter_lines_reversed_reads_last_line_first(tmp_path):
    """Test that lines are yielded from the last one to the first one."""
    path = tmp_path / "lines.txt"
    path.write_text("first\nsecond\nthird")

    assert list(_iter_lines_reversed(path)) == ["third", "second", "first"]


def test_iter_lines_reversed_trailing_newline(tmp_path):
    """Test that a trailing newline produces an empty last line."""
    path = tmp_path / "lines.txt"
    path.write_text("a\nb\n")

    assert list(_iter_lines_reversed(path)) == ["", "b", "a"]


def test_iter_lines_reversed_single_line_without_newline(tmp_path):
    """Test a file with a single line and no trailing newline."""
    path = tmp_path / "lines.txt"
    path.write_text("only")

    assert list(_iter_lines_reversed(path)) == ["only"]


def test_iter_lines_reversed_empty_file(tmp_path):
    """Test that an empty file yields no lines."""
    path = tmp_path / "lines.txt"
    path.write_text("")

    assert list(_iter_lines_reversed(path)) == []


def test_iter_lines_reversed_lines_longer_than_chunk_size(tmp_path):
    """Test that lines spanning several read steps are reassembled."""
    path = tmp_path / "lines.txt"
    first = "x" * 100
    second = "y" * 100
    path.write_text(f"{first}\n{second}\n")

    assert list(_iter_lines_reversed(path, chunk_size=7)) == ["", second, first]


def test_iter_lines_reversed_multibyte_characters_across_chunk_size(tmp_path):
    """Test that multi-byte characters split across read steps survive."""
    path = tmp_path / "lines.txt"
    line = "αβγ" * 20
    path.write_text(line, encoding="utf-8")

    assert list(_iter_lines_reversed(path, chunk_size=3)) == [line]


# --- SQLite implementation specifics ---


def test_history_sqlite_entries_have_history_id(tmp_path):
    """Test that entries carry their row id as history_id."""
    logger = HistoryLoggerSqlite(history_path=str(tmp_path / "history.db"))
    logger.log("command 1", success=True, forest=EMPTY_FOREST)
    logger.log("command 2", success=True, forest=EMPTY_FOREST)

    history = list(logger.get_history())
    assert len(history) == 2
    # Newest first; ids are autoincrement, so the newest entry has the bigger id
    assert history[0]["history_id"] == 2
    assert history[1]["history_id"] == 1


def test_history_sqlite_index_created_and_used(tmp_path):
    """Test that the timestamp index exists and is used by get_history query plan."""
    history_path = str(tmp_path / "history.db")
    logger = HistoryLoggerSqlite(history_path=history_path)
    logger.log("test", success=True, forest=EMPTY_FOREST)

    conn = sqlite3.connect(history_path)
    try:
        indexes = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='history'").fetchall()
        plan = conn.execute(
            "EXPLAIN QUERY PLAN SELECT timestamp, command FROM history ORDER BY timestamp DESC, id DESC LIMIT 5"
        ).fetchall()
    finally:
        conn.close()

    assert "idx_history_ts_id" in [row[0] for row in indexes]
    plan_str = " ".join(str(row) for row in plan)
    assert "idx_history_ts_id" in plan_str


def test_history_sqlite_read_creates_missing_index(tmp_path):
    """Test that get_history works on a legacy storage predating the index.

    The read query is pinned to the index with INDEXED BY, which raises when the
    index is missing; the read path must create it instead of failing into an
    empty result.
    """
    history_path = str(tmp_path / "history.db")
    conn = sqlite3.connect(history_path)
    try:
        conn.execute(
            "CREATE TABLE history ("
            " id INTEGER PRIMARY KEY,"
            " timestamp TEXT NOT NULL,"
            " command TEXT NOT NULL,"
            " success INTEGER NOT NULL,"
            " total_items INTEGER NOT NULL,"
            " depth_zero_items INTEGER NOT NULL,"
            " error TEXT,"
            " comment TEXT)"
        )
        conn.execute(
            "INSERT INTO history (timestamp, command, success, total_items, depth_zero_items)"
            " VALUES ('2026-01-09T10:00:00', 'legacy command', 1, 0, 0)"
        )
        conn.commit()
    finally:
        conn.close()

    logger = HistoryLoggerSqlite(history_path=history_path)

    assert [e["command"] for e in logger.get_history(success=True, min_command_length=5)] == ["legacy command"]


# --- Plugin storage selection and dummy implementation ---


def test_history_plugin_selects_jsonl_logger(tmp_path, monkeypatch):
    """Test that the history plugin selects JSONL logger for .jsonl history path."""
    monkeypatch.setenv("UDAN_HISTORY_PATH", str(tmp_path / "history.jsonl"))

    logger = create_history_storage(str(HistoryConfig().path))

    assert isinstance(logger, HistoryLogger)


def test_history_plugin_selects_sqlite_logger(tmp_path, monkeypatch):
    """Test that the history plugin selects SQLite logger for .db history path."""
    monkeypatch.setenv("UDAN_HISTORY_PATH", str(tmp_path / "history.db"))

    logger = create_history_storage(str(HistoryConfig().path))

    assert isinstance(logger, HistoryLoggerSqlite)


def test_history_plugin_selects_dummy_logger_for_unknown_extension(tmp_path, monkeypatch):
    """Test that the history plugin selects dummy logger for unrecognized history path."""
    monkeypatch.setenv("UDAN_HISTORY_PATH", str(tmp_path / "history.txt"))

    logger = create_history_storage(str(HistoryConfig().path))

    assert isinstance(logger, DummyHistoryLogger)


def test_dummy_history_logger_does_nothing():
    """Test that dummy logger does nothing and returns empty history."""
    logger = DummyHistoryLogger()

    logger.log("test", success=True, forest=EMPTY_FOREST)

    assert list(logger.get_history()) == []
    assert logger.get_history(pattern="test", limit=5) == []


def test_history_default_path():
    """Test that default history path is ./.udan/history.db."""
    config = HistoryConfig()
    # Default is ./.udan/history.db
    assert config.path.endswith("history.db")


# --- ExecContext integration (exercises IOC selection by path extension) ---


@pytest.mark.parametrize("filename", ["history.jsonl", "history.db"])
def test_exec_context_logs_history(tmp_path, filename, monkeypatch):
    """Test that ExecContext logs command execution."""
    tmpdir = str(tmp_path)
    monkeypatch.setenv("UDAN_HISTORY_PATH", f"{tmpdir}/{filename}")
    container = create_udan_container(UdanConfig())
    ctx = container.get(UdanContext)._with_plugins()
    ctx.container = container
    qp = make_qp(ctx)
    ctx._register_dependency_providers_from_module("udan.plugins_history.plugins_history")

    # Use vars inserter for testing (shows all variables, should succeed)
    loader = ToolsLoader(cache_dir=None, use_cache=False)
    metadata_fns = loader.load_from_module(plugins_system)
    ctx._register_many_metadatas(metadata_fns)

    qp.execute_query("vars")

    entry = list(container.get(HistoryLoggerAPI).get_history())[0]
    assert entry["command"] == "vars"
    assert entry["success"] is True


@pytest.mark.parametrize("filename", ["history.jsonl", "history.db"])
def test_exec_context_logs_failed_command(tmp_path, filename, monkeypatch):
    """Test that ExecContext logs failed commands."""
    tmpdir = str(tmp_path)
    monkeypatch.setenv("UDAN_HISTORY_PATH", f"{tmpdir}/{filename}")
    container = create_udan_container(UdanConfig())
    ctx = container.get(UdanContext)._with_plugins()
    ctx.container = container
    qp = make_qp(ctx)
    ctx._register_dependency_providers_from_module("udan.plugins_history.plugins_history")

    # Load tools so "raiser" will actually fail
    loader = ToolsLoader(cache_dir=None, use_cache=False)
    metadata_fns = loader.load_from_module(plugins_builtins)
    ctx._register_many_metadatas(metadata_fns)

    # Execute query that will fail (raiser always raises an exception)
    qp.execute_query("raiser")

    entry = list(container.get(HistoryLoggerAPI).get_history())[0]
    assert entry["command"] == "raiser"
    assert entry["success"] is False
    assert "error" in entry
    assert "Test exception from raiser inserter" in entry["error"]
