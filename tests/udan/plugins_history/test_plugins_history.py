"""Tests for render_history and history in udan.plugins_history."""

import uuid

import pytest

from tests.conftest import make_qp
from udan.core.config import UdanConfig
from udan.core.impl_ioc import create_udan_container
from udan.core.impl_udan_context import UdanContext
from udan.core_tools_loading.impl_tools_loader import ToolsLoader
from udan.plugins_history import plugins_history
from udan.plugins_history.api_history import DummyHistoryLogger
from udan.plugins_history.plugins_history import history, render_history
from udan.plugins_tools_examples import plugins_builtins


class _StubHistoryLogger(DummyHistoryLogger):
    """History logger returning a fixed list of entries, newest first.

    Applies the success/min-command-length/limit filters in memory, mirroring
    how the real storages push them down natively (SQL WHERE/LIMIT for SQLite).
    """

    def __init__(self, entries: list[dict]):
        self._entries = entries

    def get_history(self, pattern=None, limit=None, success=None, min_command_length=None):
        entries = self._entries
        if success is not None:
            entries = [e for e in entries if e.get("success", True) == success]
        if min_command_length is not None:
            entries = [e for e in entries if len(str(e.get("command", ""))) >= min_command_length]
        if limit is not None and limit >= 0:
            entries = entries[:limit]
        return iter(entries)


def test_history_patterns_filter_entries() -> None:
    """Test that positional patterns are applied with greps semantics (AND + '-' exclusion)."""
    entries = [
        {"history_id": 3, "command": "git log", "success": True, "error": ""},
        {"history_id": 2, "command": "git status", "success": True, "error": ""},
        {"history_id": 1, "command": "ls -la", "success": True, "error": ""},
    ]
    logger = _StubHistoryLogger(entries)

    assert list(history(patterns=["git"], history_logger=logger)) == entries[:2]
    assert list(history(patterns=["git", "-status"], history_logger=logger)) == entries[:1]
    assert list(history(patterns=["-git"], history_logger=logger)) == entries[2:]
    assert list(history(patterns=["nomatch"], history_logger=logger)) == []


def test_history_patterns_limit_counts_matching_entries() -> None:
    """Test that limit is applied after pattern filtering."""
    entries = [
        {"history_id": 3, "command": "git log", "success": True, "error": ""},
        {"history_id": 2, "command": "git status", "success": True, "error": ""},
        {"history_id": 1, "command": "ls -la", "success": True, "error": ""},
    ]
    logger = _StubHistoryLogger(entries)

    assert list(history(patterns=["git"], limit=1, history_logger=logger)) == entries[:1]
    assert list(history(limit=2, history_logger=logger)) == entries[:2]
    assert list(history(limit=0, history_logger=logger)) == []
    assert list(history(limit=-1, history_logger=logger)) == entries


def test_history_hides_failed_and_short_entries_by_default() -> None:
    """Test that failed entries and commands shorter than 5 chars are hidden by default."""
    entries = [
        {"history_id": 4, "command": "git log", "success": True, "error": ""},
        {"history_id": 3, "command": "ls", "success": True, "error": ""},
        {"history_id": 2, "command": "vars", "success": False, "error": "boom"},
        {"history_id": 1, "command": "ab", "success": False, "error": "x"},
    ]
    logger = _StubHistoryLogger(entries)

    assert list(history(history_logger=logger)) == [entries[0]]


def test_history_all_shows_failed_and_short_entries() -> None:
    """Test that --all shows failed and short entries."""
    entries = [
        {"history_id": 4, "command": "git log", "success": True, "error": ""},
        {"history_id": 3, "command": "ls", "success": True, "error": ""},
        {"history_id": 2, "command": "vars", "success": False, "error": "boom"},
        {"history_id": 1, "command": "ab", "success": False, "error": "x"},
    ]
    logger = _StubHistoryLogger(entries)

    assert list(history(all=True, history_logger=logger)) == entries


def test_history_limit_counts_entries_surviving_default_hiding() -> None:
    """Test that limit is applied after the default hiding filter."""
    entries = [
        {"history_id": 4, "command": "git log", "success": True, "error": ""},
        {"history_id": 3, "command": "ls", "success": True, "error": ""},
        {"history_id": 2, "command": "fruits", "success": True, "error": ""},
    ]
    logger = _StubHistoryLogger(entries)

    assert list(history(limit=1, history_logger=logger)) == [entries[0]]
    assert list(history(limit=2, history_logger=logger)) == [entries[0], entries[2]]


def test_render_history_successful_command_oneline() -> None:
    """Test rendering successful command without newlines."""
    entry = {
        "timestamp": "2026-01-09T20:00:00",
        "command": "test query",
        "success": True,
        "total_items": 5,
    }
    result = render_history(entry)
    assert result == "- [ ] [] 2026-01-09 20:00:00 🟢 (5 items) :: test query"


def test_render_history_successful_command_multiline() -> None:
    """Test that multiline successful commands are shown on one line."""
    entry = {
        "timestamp": "2026-01-09T20:00:00",
        "command": "first line\nsecond line\nthird line",
        "success": True,
        "total_items": 10,
    }
    result = render_history(entry)
    # Newlines should be replaced with spaces
    assert "\n" not in result
    assert result == "- [ ] [] 2026-01-09 20:00:00 🟢 (10 items) :: first line second line third line"


def test_render_history_failed_command_short() -> None:
    """Test that failed short commands are shown fully."""
    entry = {
        "timestamp": "2026-01-09T20:00:00",
        "command": "bad query",
        "success": False,
        "total_items": 0,
        "error": "syntax error",
    }
    result = render_history(entry)
    assert result == "- [ ] [] 2026-01-09 20:00:00 🔴 (0 items) :: bad query - syntax error"


def test_render_history_failed_command_long() -> None:
    """Test that failed long commands are truncated to ~60 chars."""
    entry = {
        "timestamp": "2026-01-09T20:00:00",
        "command": "this is a very long query that exceeds the sixty character limit and should be truncated",
        "success": False,
        "total_items": 0,
        "error": "some error",
    }
    result = render_history(entry)
    # Should be truncated with "..." suffix
    assert "..." in result
    # Length should be controlled (timestamp + status + items + truncated query + error)
    # The truncated command part should be at most 60 chars total (including
    # "...")
    assert "this is a very long query that exceeds the sixty characte..." in result
    assert result.endswith("- some error")


def test_render_history_failed_command_multiline() -> None:
    """Test that failed multiline commands are shown on one line and truncated."""
    entry = {
        "timestamp": "2026-01-09T20:00:00",
        "command": "line one\nline two\nline three\nline four\nline five continues further",
        "success": False,
        "total_items": 0,
        "error": "error",
    }
    result = render_history(entry)
    # No newlines in output
    assert "\n" not in result
    # Should have "..." since it's a failed query with long content
    assert "..." in result


def test_render_history_failed_command_multiline_short() -> None:
    """Test failed multiline command that becomes short after newline replacement."""
    entry = {
        "timestamp": "2026-01-09T20:00:00",
        "command": "a\nb\nc",
        "success": False,
        "total_items": 0,
        "error": "error",
    }
    result = render_history(entry)
    # Should be "a b c" without truncation
    assert "\n" not in result
    assert ":: a b c" in result
    assert "..." not in result


def test_render_history_tuple_format() -> None:
    """Test rendering with tuple (depth, item_data) format."""
    entry = {
        "timestamp": "2026-01-09T20:00:00",
        "command": "test",
        "success": True,
        "total_items": 3,
    }
    result = render_history((2, entry))
    # Note: The current implementation extracts depth but doesn't use it for indentation
    # It uses the default indent parameter instead
    assert result == "- [ ] [] 2026-01-09 20:00:00 🟢 (3 items) :: test"


def test_render_history_with_indent() -> None:
    """Test rendering with custom indent."""
    entry = {
        "timestamp": "2026-01-09T20:00:00",
        "command": "test",
        "success": True,
        "total_items": 1,
    }
    result = render_history(entry, indent="    ")
    assert result == "    - [ ] [] 2026-01-09 20:00:00 🟢 (1 items) :: test"


def test_render_history_non_dict_item() -> None:
    """Test rendering non-dict item (fallback to string representation)."""
    result = render_history("not a dict")
    assert result == "- not a dict"


def test_render_history_missing_fields() -> None:
    """Test rendering entry with missing fields (graceful degradation)."""
    entry = {"command": "test"}
    result = render_history(entry)
    # Should handle missing fields gracefully
    assert "test" in result


@pytest.mark.xdist_group("history_test")  # Mark as xdist-incompatible due to shared history state
def test_history_render_failed_query_shows_oneline_truncated(
    tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Integration test: failed queries in history are shown on one line and truncated."""
    # Set up history file path - use unique path to avoid conflicts with other tests

    unique_id = str(uuid.uuid4())[:8]
    history_path = tmp_path / f"udan_history_{unique_id}.jsonl"
    monkeypatch.setenv("UDAN_HISTORY_PATH", str(history_path))
    container = create_udan_container(UdanConfig())
    ctx = container.get(UdanContext)
    ctx.container = container
    qp = make_qp(ctx)

    # Load tools: builtins (raiser inserter) and history (history);
    # register the history plugin providers so its storages are resolvable

    ctx._register_dependency_providers_from_module(plugins_history.__name__)
    loader = ToolsLoader(cache_dir=None, use_cache=False)
    ctx._register_many_metadatas(loader.load_from_module(plugins_builtins))
    ctx._register_many_metadatas(loader.load_from_module(plugins_history))

    # Run a query with newlines that will fail (using raiser inserter)
    bad_query = (
        "raiser\nwith\nnewlines\nthat is very long and should be truncated when shown in history because it failed"
    )
    qp.execute_query(bad_query)

    # Run history with --all to see the result (uses default history-item render;
    # the failed query is hidden without --all)
    forest, attrs, render_specs, out = qp.execute_query("history --all")

    # The history output should not contain newlines (except between history entries)
    # Each history entry should be on its own line
    lines = [line for line in out.split("\n") if line.strip()]
    assert len(lines) > 0, "History should have entries"

    # Find our specific failed query in the history (search for "raiser with newlines")
    # We need to find the line that contains our query - look for the truncated pattern "trun..."
    failed_line = None
    for line in lines:
        if "raiser" in line and "newlines" in line and "trun..." in line:
            failed_line = line
            break

    assert failed_line is not None, "Failed query should be in history"

    # The failed query line should not contain literal \n in the command part
    # (newlines in the command should be replaced with spaces)
    assert "\n" not in failed_line, "Each history entry should be on a single line"

    # The failed query should be truncated with "..."
    assert "..." in failed_line, "Failed query should be truncated with '...'"


def _make_history_ctx(tmp_path, monkeypatch):
    """Create a context with history tools registered and history file isolated."""
    monkeypatch.setenv("UDAN_HISTORY_PATH", str(tmp_path / "history.jsonl"))
    container = create_udan_container(UdanConfig())
    ctx = container.get(UdanContext)
    ctx.container = container
    ctx._register_dependency_providers_from_module(plugins_history.__name__)
    loader = ToolsLoader(cache_dir=None, use_cache=False)
    ctx._register_many_metadatas(loader.load_from_module(plugins_builtins))
    ctx._register_many_metadatas(loader.load_from_module(plugins_history))
    return ctx


def test_history_query_with_patterns(tmp_path, monkeypatch) -> None:
    """Test that history patterns are bound from the query as greps-style filters."""
    ctx = _make_history_ctx(tmp_path, monkeypatch)
    qp = make_qp(ctx)

    qp.execute_query("fruits")
    qp.execute_query("fruits, limit 3, :list")

    forest, attrs, render_specs, out = qp.execute_query("history fruits --all")

    commands = [item["command"] for item in forest.items]
    assert commands == ["fruits, limit 3, :list", "fruits"]


def test_history_query_with_exclusion_pattern(tmp_path, monkeypatch) -> None:
    """Test that a '-'-prefixed history pattern excludes matching entries."""
    ctx = _make_history_ctx(tmp_path, monkeypatch)
    qp = make_qp(ctx)

    qp.execute_query("fruits")
    qp.execute_query("fruits, limit 3, :list")

    forest, attrs, render_specs, out = qp.execute_query("history fruits -limit --all")

    commands = [item["command"] for item in forest.items]
    assert commands == ["fruits"]


def test_history_query_patterns_with_limit(tmp_path, monkeypatch) -> None:
    """Test that --limit counts entries surviving the pattern filter."""
    ctx = _make_history_ctx(tmp_path, monkeypatch)
    qp = make_qp(ctx)

    qp.execute_query("fruits")
    qp.execute_query("fruits, limit 3, :list")

    forest, attrs, render_specs, out = qp.execute_query("history fruits --limit=1 --all")

    commands = [item["command"] for item in forest.items]
    assert commands == ["fruits, limit 3, :list"]
