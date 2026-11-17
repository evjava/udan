"""Tests for plugins inserter."""

import pytest

import udan.plugins_tools_demo.plugins_demo
import udan.plugins_tools_demo.plugins_fruits
from tests.conftest import make_qp, register_tools_from_module
from udan.plugins_tools_examples import plugins_builtins
from udan.renders import plugins_renders


@pytest.fixture
def ctx(make_ctx):
    """Provide an UdanContext with demo plugin for testing."""
    ctx = make_ctx()
    return ctx


@pytest.fixture
def ctx_with_builtins(make_ctx):
    """Provide an UdanContext with builtins and demo plugins registered."""

    ctx = make_ctx()
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)
    register_tools_from_module(ctx, plugins_builtins.__name__)
    register_tools_from_module(ctx, plugins_renders.__name__)
    return ctx


def test_plugins_no_pattern(ctx_with_builtins):
    qp_with_builtins = make_qp(ctx_with_builtins)
    """Test plugins inserter with no pattern returns all plugins."""
    forest, attrs, render_specs, out = qp_with_builtins.execute_query("plugins")

    # Should have at least builtins, demo, and renders plugins
    assert len(forest.items) >= 3

    # Check that result is a list of dicts with expected keys
    for plugin in forest.items:
        assert isinstance(plugin, dict)
        assert "name" in plugin
        assert "domain" in plugin
        assert "count" in plugin
        assert isinstance(plugin["count"], int)
        assert plugin["count"] >= 0


def test_plugins_with_pattern(ctx_with_builtins):
    qp_with_builtins = make_qp(ctx_with_builtins)
    """Test plugins inserter with pattern filters results."""
    forest, attrs, render_specs, out = qp_with_builtins.execute_query("plugins demo")

    # Should only have demo plugin
    assert len(forest.items) == 1
    plugin = forest.items[0]
    assert plugin["name"] == "demo"
    assert plugin["domain"] == "demo"
    assert plugin["count"] >= 5  # demo has multiple tools


def test_plugins_pattern_case_insensitive(ctx_with_builtins):
    qp_with_builtins = make_qp(ctx_with_builtins)
    """Test plugins pattern matching is case insensitive."""
    forest1, _, _, _ = qp_with_builtins.execute_query("plugins DEMO")
    forest2, _, _, _ = qp_with_builtins.execute_query("plugins demo")

    # Both should return same results
    assert forest1.items == forest2.items


def test_plugins_via_query_render(ctx_with_builtins):
    qp_with_builtins = make_qp(ctx_with_builtins)
    """Test plugins through query with list render."""
    forest, attrs, render_specs, out = qp_with_builtins.execute_query("plugins demo, :list")

    # Output should contain demo plugin info
    assert "demo" in out.lower()
