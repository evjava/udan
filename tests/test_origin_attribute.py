"""Tests for the origin attribute.

All tests use execute_query and parse output for readability and reproducibility.
Uses range + is_even for simplicity.
"""

from typing import Any

import udan.plugins_tools_demo.plugins_demo
import udan.plugins_tools_demo.plugins_fruits
from tests.conftest import make_qp, register_tools_from_module
from udan.attributes import plugins_operators_attribute
from udan.attributes.api_attribute_storage import AttributeStorageAPI
from udan.core.api_attributes import AttributeDescriptor
from udan.core_tools_loading.api_tools import ToolDescriptor
from udan.core_tools_loading.api_types import Group
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.plugins_tools_examples import plugins_builtins

# Origin attribute descriptor constant
ORIGIN_AD = AttributeDescriptor.create("origin", args={"node": None})


def get_origin(ctx: Any, item: Any) -> list[ToolDescriptor] | None:
    return ctx.container.get(AttributeStorageAPI).get_attr_value_from_dict(ORIGIN_AD, item)


def test_origin_static_item(make_ctx):
    """Test that static items (not from any operator) have empty origin."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    forest, _, _, _ = qp.execute_query("'item1' 'item2'")

    # Static items should have None or empty origin
    for item in forest.items:
        assert get_origin(ctx, item) is None or get_origin(ctx, item) == []


def test_origin_from_created_level(make_ctx):
    """Test origin attribute for items from an inserter."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__, verbose=False)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__, verbose=False)

    forest, _, _, out = qp.execute_query("range 5")
    assert "0" in out

    # All numbers should have same origin as item 0
    item_0 = next(item for item in forest.items if item == 0)
    expected_origin = get_origin(ctx, item_0)
    for item in forest.items:
        assert get_origin(ctx, item) == expected_origin


def test_origin_with_groups(make_ctx):
    """Test origin attribute for items that have been grouped.

    Verifies that:
    - Groups have only the grouper in origin (created by grouper, not inserter)
    - Items inside groups have both inserter and grouper in origin
    """
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__, verbose=False)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__, verbose=False)

    forest, _, _, _ = qp.execute_query("range 5, group_by_attribute is_even")

    # Check Group has only grouper in origin, number has both range and grouper
    for item in forest.items:
        origin = get_origin(ctx, item)
        identities = [op.name for op in origin] if origin else []

        if isinstance(item, Group):
            assert "group_by_attribute" in identities
            assert identities == ["group_by_attribute"]
        elif isinstance(item, int):
            assert "group_by_attribute" in identities
            assert "range" in identities
        else:
            assert False, f"Bad item: {item}"


def test_origin_double_grouper(make_ctx):
    """Test origin with two different groupers in sequence."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__, verbose=False)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__, verbose=False)

    forest, _, _, _ = qp.execute_query("range 9, group_by_attribute is_even, group_by_attribute div_3")

    # Should have groups
    group_count = sum(1 for item in forest.items if isinstance(item, Group))
    assert group_count > 0

    # Check number 4 has range + both groupers in origin
    item_4 = next(item for item in forest.items if item == 4)
    origin = get_origin(ctx, item_4)
    assert [op.name for op in origin] == ["range", "group_by_attribute", "group_by_attribute"]


def test_origin_chain_appends(make_ctx):
    """Test that each operator appends itself to the origin chain."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__, verbose=False)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__, verbose=False)

    forest, _, _, _ = qp.execute_query("range 5, group_by_attribute is_even")

    # Check first number's origin chain order
    item_0 = next(item for item in forest.items if item == 0)
    origin = get_origin(ctx, item_0)
    identities = [op.name for op in origin]
    assert "range" in identities
    assert "group_by_attribute" in identities
    assert identities.index("range") < identities.index("group_by_attribute")


def test_origin_two_inserters_and_grouper(make_ctx):
    """Test origin with two inserters followed by a grouper.

    Two inserters are concatenated via a parenthesized statement list:
    items from each inserter keep their own inserter in origin,
    then the grouper appends itself to all of them.
    """
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__, verbose=False)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__, verbose=False)

    forest, _, _, _ = qp.execute_query("(range 3; range 3 6), group_by_attribute is_even")

    # Define expected origins from items 0 and 3
    item_0 = next(item for item in forest.items if item == 0)
    item_3 = next(item for item in forest.items if item == 3)
    expected_origin_first = get_origin(ctx, item_0)
    expected_origin_second = get_origin(ctx, item_3)

    for item in forest.items:
        if isinstance(item, Group):
            pass  # Groups are fine, skip them
        elif item in (0, 1, 2):
            assert get_origin(ctx, item) == expected_origin_first
        elif item in (3, 4, 5):
            assert get_origin(ctx, item) == expected_origin_second
        else:
            assert False, f"Bad item: {item}"
