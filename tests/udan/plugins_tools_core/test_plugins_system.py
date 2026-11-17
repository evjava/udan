"""Tests for system plugins - configuration and system attributes."""

import pytest

from tests.conftest import make_qp, register_tools_from_module
from udan.core.api_attributes import SYSTEM
from udan.plugins_tools_core import plugins_help, plugins_system
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.renders import plugins_renders


@pytest.fixture
def ctx_with_system(make_ctx):
    """Context with system plugins registered."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_help, plugins_system, plugins_renders)
    register_tools_from_module(ctx, plugins_help.__name__)
    register_tools_from_module(ctx, plugins_system.__name__)
    return ctx


def test_system_render_attribute_exists(ctx_with_system):
    """Test that render system attribute is registered."""
    ctx = ctx_with_system

    # Check that render attribute is registered
    metadata = ctx.registry.get_metadata("render")

    assert metadata is not None
    assert metadata.meta.get(SYSTEM) is True
    assert metadata.meta.get("tool_type") == "attribute"


def test_system_render_attribute_default_value(ctx_with_system):
    """Test that render attribute returns default fallback value when not set."""
    ctx = ctx_with_system
    qp = make_qp(ctx)

    # Execute query that uses render attribute
    forest, attrs, render_specs, out = qp.execute_query("fruits, :attrs render")

    # Should contain default render name "term-list-item"
    assert "term-list-item" in out


def test_udan_config_inserter_exists(ctx_with_system):
    """Test that udan_config inserter is registered."""
    ctx = ctx_with_system

    # Check that udan_config inserter is registered
    metadata = ctx.registry.get_metadata("udan_config")

    assert metadata is not None
    assert metadata.meta.get("tool_type") == "inserter"


def test_udan_config_inserter_works(ctx_with_system):
    """Test that udan_config inserter returns configuration."""
    ctx = ctx_with_system
    qp = make_qp(ctx)

    # Execute query that uses udan_config
    forest, attrs, render_specs, out = qp.execute_query("udan_config")

    # Should contain configuration keys
    assert "udan_cache_dir" in out or "cache_dir" in out
