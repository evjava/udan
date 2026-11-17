"""Tests for is_even attribute."""

from tests.conftest import make_qp
from udan.attributes import plugins_operators_attribute
from udan.core_tools_loading.api_types import Group
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.plugins_tools_demo.plugins_demo import is_even
from udan.plugins_tools_examples import plugins_builtins


def test_is_even_direct():
    """Test is_even attribute function directly."""

    # Test even numbers
    assert is_even(0) is True
    assert is_even(2) is True
    assert is_even(10) is True
    assert is_even(-2) is True

    # Test odd numbers
    assert is_even(1) is False
    assert is_even(3) is False
    assert is_even(11) is False
    assert is_even(-3) is False

    # Test non-integer types
    assert is_even("2") is None
    assert is_even(2.5) is None
    assert is_even(None) is None


def test_filter_by_attribute_is_even(make_ctx):
    """Test filter_by_attribute with is_even attribute."""
    # Execute query: range 1 10, filter by is_even attribute
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 1 10, filter_by_attribute is_even == True")

    # Should show: 2, 4, 6, 8 (even numbers from 1 to 9)
    lines = out.strip().split("\n")
    assert len(lines) == 4
    assert lines[0] == "- 2"
    assert lines[1] == "- 4"
    assert lines[2] == "- 6"
    assert lines[3] == "- 8"


def test_filter_by_attribute_is_even_with_zero(make_ctx):
    """Test filter_by_attribute with is_even including zero."""
    # Execute query: range 0 5, filter by is_even == True
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 0 5, filter_by_attribute is_even == True")

    # Should show: 0, 2, 4 (even numbers from 0 to 4)
    lines = out.strip().split("\n")
    assert len(lines) == 3
    assert lines[0] == "- 0"
    assert lines[1] == "- 2"
    assert lines[2] == "- 4"


def test_filter_by_attribute_is_even_with_step(make_ctx):
    """Test filter_by_attribute with range that has a step."""
    # Execute query: range 0 10 3 (0, 3, 6, 9), filter by is_even == True
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 0 10 3, filter_by_attribute is_even == True")

    # Should show: 0, 6 (even numbers from 0, 3, 6, 9)
    lines = out.strip().split("\n")
    assert len(lines) == 2
    assert lines[0] == "- 0"
    assert lines[1] == "- 6"


def test_filter_by_attribute_is_even_all_odd(make_ctx):
    """Test filter_by_attribute when all numbers are odd."""
    # Execute query: range 1 6 2 (1, 3, 5), filter by is_even == True
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 1 6 2, filter_by_attribute is_even == True")

    # Should show empty result
    lines = out.strip().split("\n")
    assert len(lines) == 1 or out.strip() == ""


def test_filter_by_attribute_is_even_negative_numbers(make_ctx):
    """Test filter_by_attribute with negative numbers."""
    # Execute query: range -5 5, filter by is_even == True
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range -5 5, filter_by_attribute is_even == True")

    # Should show even numbers: -4, -2, 0, 2, 4
    lines = out.strip().split("\n")
    assert len(lines) == 5
    assert lines[0] == "- -4"
    assert lines[1] == "- -2"
    assert lines[2] == "- 0"
    assert lines[3] == "- 2"
    assert lines[4] == "- 4"


def test_group_by_attribute_is_even(make_ctx):
    """Test group_by_attribute with is_even attribute."""
    # Execute query: range 4, group by is_even
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 4, group_by_attribute is_even")

    # Should have two groups: True (0, 2) and False (1, 3)
    # Group items are now skipped during rendering, so we only see the child items
    lines = out.strip().split("\n")

    # Check that we have the 4 items (0, 1, 2, 3)
    # Note: items at depth > 0 have leading space in output
    assert any("0" in line for line in lines)
    assert any("1" in line for line in lines)
    assert any("2" in line for line in lines)
    assert any("3" in line for line in lines)

    # Verify that Group items exist in the forest (not rendered)

    group_items = [item for item in forest.items if isinstance(item, Group)]
    assert len(group_items) == 2

    # Check that groups have correct keys (keys are booleans, not strings)
    group_true = next((g for g in group_items if g.key is True), None)
    assert group_true is not None

    group_false = next((g for g in group_items if g.key is False), None)
    assert group_false is not None
