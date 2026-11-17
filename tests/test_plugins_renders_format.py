"""Tests for formatter render with attribute references."""

from types import SimpleNamespace

import pytest

import udan.plugins_tools_demo.plugins_fruits
import udan.renders.plugins_renders
from tests.conftest import make_qp, register_tools_from_module
from udan.attributes import plugins_operators_attribute
from udan.plugins_tools_examples import plugins_builtins
from udan.renders.plugins_renders import (
    _format_with_attr_refs,
    _resolve_attr_path,
    _resolve_item_field,
    render_format,
)


@pytest.fixture
def ctx_with_renders(make_ctx):
    """Provide an UdanContext with renders plugin registered."""
    ctx = make_ctx()
    register_tools_from_module(ctx, udan.renders.plugins_renders.__name__)
    return ctx


def test_fmt_render_basic_item(ctx_with_renders):
    """Test that :fmt renders basic item with {item} placeholder."""

    result = render_format("hello, world")
    assert "hello, world" in result


def test_fmt_render_with_attr_refs(ctx_with_renders):
    """Test that :fmt renders with attribute path references."""

    # Test with a missing attribute - should handle gracefully
    result = render_format(":fmt", format="- {item} :: CC={metrics.CC}")
    # Should show the item with empty CC value
    assert "- :fmt :: CC=" in result


def test_resolve_attr_path_simple(ctx_with_renders):
    """Test _resolve_attr_path with simple path."""

    attrs = {"metrics": {"CC": 5}}
    result = _resolve_attr_path(attrs, "metrics.CC")
    assert result == 5


def test_resolve_attr_path_nested(ctx_with_renders):
    """Test _resolve_attr_path with nested path."""

    attrs = {"build": {"report": {"count": 75.5}}}
    result = _resolve_attr_path(attrs, "build.report.count")
    assert result == 75.5


def test_resolve_attr_path_missing(ctx_with_renders):
    """Test _resolve_attr_path with missing path."""

    attrs = {"metrics": {"CC": 5}}
    result = _resolve_attr_path(attrs, "metrics.missing")
    assert result is None


def test_resolve_attr_path_none_attrs(ctx_with_renders):
    """Test _resolve_attr_path with None attrs."""

    result = _resolve_attr_path(None, "metrics.CC")
    assert result is None


def test_format_with_attr_refs_basic(ctx_with_renders):
    """Test _format_with_attr_refs with basic format string."""

    result = _format_with_attr_refs("- {item} :: value", "test_item", None, "")
    assert result == "- test_item :: value"


def test_format_with_attr_refs_with_attrs(ctx_with_renders):
    """Test _format_with_attr_refs with attribute references."""

    attrs = {"metrics": {"CC": 10, "item_name": "test_func"}}
    result = _format_with_attr_refs("- {item} {metrics.item_name} :: {metrics.CC}", "test.py:42", attrs, "")
    assert result == "- test.py:42 test_func :: 10"


def test_format_with_attr_refs_with_format_spec(ctx_with_renders):
    """Test _format_with_attr_refs with format spec."""

    attrs = {"build": {"report": {"count": 75.567}}}
    result = _format_with_attr_refs("- {item} :: {build.report.count:.1f}%", "test.py:42", attrs, "")
    assert result == "- test.py:42 :: 75.6%"


def test_format_with_attr_refs_missing_attr(ctx_with_renders):
    """Test _format_with_attr_refs with missing attribute."""

    attrs = {"other": {"value": 5}}
    result = _format_with_attr_refs("- {item} :: {missing.attr}", "test", attrs, "")
    # Should handle missing attr gracefully
    assert "test" in result


def test_resolve_item_field_dict(ctx_with_renders):
    """Test _resolve_item_field with a dict item."""

    assert _resolve_item_field({"id": 1, "name": "apple"}, "name") == "apple"
    assert _resolve_item_field({"id": 1, "name": "apple"}, "missing") is None


def test_resolve_item_field_object(ctx_with_renders):
    """Test _resolve_item_field with a non-dict item (attribute lookup)."""

    assert _resolve_item_field(SimpleNamespace(name="apple"), "name") == "apple"
    assert _resolve_item_field(SimpleNamespace(name="apple"), "missing") is None


def test_resolve_item_field_subscript(ctx_with_renders):
    """Test _resolve_item_field with the explicit {item[field]} form."""

    assert _resolve_item_field({"name": "apple"}, "item[name]") == "apple"
    assert _resolve_item_field({"name": "apple"}, "item['name']") == "apple"
    assert _resolve_item_field(SimpleNamespace(name="apple"), "item[name]") == "apple"


def test_format_with_item_dict_field(ctx_with_renders):
    """Test that {field} resolves from a dict item when no attrs are loaded."""

    result = _format_with_attr_refs("{name}", {"id": 1, "name": "apple", "color": "red"}, None, "")
    assert result == "apple"


def test_format_with_item_field_format_spec(ctx_with_renders):
    """Test that format specs apply to item fields."""

    result = _format_with_attr_refs("{calories:.0f}", {"name": "apple", "calories": 52.4}, None, "")
    assert result == "52"


def test_format_attrs_take_precedence_over_item_field(ctx_with_renders):
    """Test that an explicit attribute wins over an item field with the same name."""

    attrs = {"name": "attr-value"}
    result = _format_with_attr_refs("{name}", {"name": "apple"}, attrs, "")
    assert result == "attr-value"


def test_format_missing_item_field_falls_back_to_item(ctx_with_renders):
    """Test that a format string resolving to nothing falls back to the item string."""

    result = _format_with_attr_refs("{missing}", {"name": "apple"}, None, "")
    assert result == "{'name': 'apple'}"


def test_format_constant_string_returned_as_is(ctx_with_renders):
    """Test that a format string without placeholders is returned as-is, not the item."""

    result = _format_with_attr_refs("const", {"name": "apple"}, None, "")
    assert result == "const"


def test_fmt_render_fruits_by_name(make_ctx):
    """Test that `fruits, :fmt "{name}"` renders just the fruit names."""

    ctx = make_ctx(
        udan.plugins_tools_demo.plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        udan.renders.plugins_renders,
    )
    qp = make_qp(ctx)
    _, _, _, out = qp.execute_query('fruits, limit 2, :fmt("{name}")')
    assert out == "apple\norange"


def test_fmt_render_fruits_constant_string(make_ctx):
    """Test that `fruits, :fmt "const"` repeats the constant for every fruit."""

    ctx = make_ctx(
        udan.plugins_tools_demo.plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        udan.renders.plugins_renders,
    )
    qp = make_qp(ctx)
    _, _, _, out = qp.execute_query('fruits, limit 3, :fmt("const")')
    assert out == "const\nconst\nconst"
