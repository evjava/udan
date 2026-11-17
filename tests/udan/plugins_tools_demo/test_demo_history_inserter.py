"""Demo test for history inserter.

This test verifies that the history inserter shows history items from command execution.
"""

import udan.plugins_history.plugins_history
from tests.conftest import make_qp
from udan.core.config import UdanConfig
from udan.core.impl_ioc import create_udan_container
from udan.core.impl_udan_context import UdanContext
from udan.core_tools_loading.impl_tools_loader import ToolsLoader
from udan.plugins_tools_core import plugins_help, plugins_system


def test_history_inserter_shows_history_items(tmp_path, monkeypatch):
    """Test that history inserter shows executed commands from history."""
    monkeypatch.setenv("UDAN_HISTORY_PATH", str(tmp_path / "history.jsonl"))
    container = create_udan_container(config=UdanConfig())
    ctx = container.get(UdanContext)
    ctx.container = container
    qp = make_qp(ctx)
    ctx._register_dependency_providers_from_module(udan.plugins_history.plugins_history.__name__)

    # Load tools including history inserter
    loader = ToolsLoader(cache_dir=None, use_cache=False)
    ctx._register_many_metadatas(loader.load_from_module(plugins_help))
    metadata_fns = loader.load_from_module(plugins_system)
    ctx._register_many_metadatas(metadata_fns)
    metadata_fns = loader.load_from_module(udan.plugins_history.plugins_history)
    ctx._register_many_metadatas(metadata_fns)

    # Execute some commands to populate history
    qp.execute_query("vars")
    qp.execute_query("help")
    qp.execute_query("help pattern=vars")

    # Now use the history inserter
    forest, attrs, render_specs, out = qp.execute_query("history")

    # Should return history items
    history_items = forest.items
    assert len(history_items) > 0, "history inserter should return history items"

    # Items should be history dicts (Forest unpacks the tuples into depths and items)
    # Each item should be a dict with history data
    for item in history_items:
        assert isinstance(item, dict), f"history item should be dict, got {type(item)}"
        # Check required fields
        assert "command" in item, "history dict should have 'command' field"
        assert "timestamp" in item, "history dict should have 'timestamp' field"
        assert "success" in item, "history dict should have 'success' field"


def test_history_inserter_limit_returns_most_recent(tmp_path, monkeypatch):
    """Test that the history inserter honours --limit and keeps newest first."""
    monkeypatch.setenv("UDAN_HISTORY_PATH", str(tmp_path / "history.jsonl"))
    container = create_udan_container(config=UdanConfig())
    ctx = container.get(UdanContext)
    ctx.container = container
    qp = make_qp(ctx)
    ctx._register_dependency_providers_from_module(udan.plugins_history.plugins_history.__name__)

    loader = ToolsLoader(cache_dir=None, use_cache=False)
    ctx._register_many_metadatas(loader.load_from_module(plugins_help))
    metadata_fns = loader.load_from_module(plugins_system)
    ctx._register_many_metadatas(metadata_fns)
    metadata_fns = loader.load_from_module(udan.plugins_history.plugins_history)
    ctx._register_many_metadatas(metadata_fns)

    qp.execute_query("vars")
    qp.execute_query("help")
    qp.execute_query("help pattern=vars")

    # --all: the bare `help` command is under the default 5-char history minimum
    forest, attrs, render_specs, out = qp.execute_query("history --limit=2 --all")

    history_items = forest.items
    commands = [item["command"] for item in history_items]
    assert commands == ["help pattern=vars", "help"]


def test_history_inserter_empty_history(tmp_path, monkeypatch):
    """Test that history inserter returns empty list when no history."""
    # Don't create history file - empty history
    monkeypatch.setenv("UDAN_HISTORY_PATH", str(tmp_path / "history.jsonl"))
    container = create_udan_container(config=UdanConfig())
    ctx = container.get(UdanContext)
    ctx.container = container
    qp = make_qp(ctx)
    ctx._register_dependency_providers_from_module(udan.plugins_history.plugins_history.__name__)

    # Load tools
    loader = ToolsLoader(cache_dir=None, use_cache=False)
    ctx._register_many_metadatas(loader.load_from_module(plugins_help))
    metadata_fns = loader.load_from_module(plugins_system)
    ctx._register_many_metadatas(metadata_fns)
    metadata_fns = loader.load_from_module(udan.plugins_history.plugins_history)
    ctx._register_many_metadatas(metadata_fns)

    # Use the history inserter without executing any commands
    forest, attrs, render_specs, out = qp.execute_query("history")

    # Should return empty list or list with empty message
    history_items = forest.items
    assert len(history_items) == 0 or "no history" in str(history_items[0]).lower()
