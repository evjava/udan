"""Tests for demo plugin operators."""

from tests.conftest import make_qp
from udan.attributes import plugins_operators_attribute
from udan.core_tools_loading.api_types import Group
from udan.plugins_history import plugins_history
from udan.plugins_tools_core import plugins_system
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.plugins_tools_examples import plugins_builtins, plugins_org
from udan.renders import plugins_renders


def test_similar_fruits_creates_nested_structure(make_ctx):
    """Test that similar_fruits extender creates nested structure."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("fruits, similar_fruits")

    # Should have nested structure with fruits and their similar fruits
    assert "apple" in out
    assert "orange" in out
    assert "strawberry" in out
    assert "blueberry" in out


def test_map_attr_works_with_nested_structure(make_ctx):
    """Test that map_attr works with nested similar_fruits structure."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("fruits, similar_fruits, map_attr calories")

    # All items should be calories (numbers), not full dicts
    assert "{" not in out  # No dict syntax
    assert "}" not in out

    # Should have both parent and child calories
    assert "52" in out  # apple calories
    assert "47" in out  # orange calories


def test_map_attr_respects_nested_structure(make_ctx):
    """Test that map_attr replaces items at all depth levels while preserving structure."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("fruits, limit 3, similar_fruits, map_attr calories, :list")

    # All items should be calories (numbers), nested brackets show child items
    # Format: [parent_cal, [child_calories...], parent_cal,
    # [child_calories...], ...]
    assert out.startswith("[") and out.endswith("]")
    # Should have nested structure (brackets within brackets)
    assert "[, [" in out or ", [" in out or "[]," in out


def test_filter_field_by_color_red(make_ctx):
    """Test filter_field operator filtering fruits by color red."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("fruits, filter_field color == red, :list")

    # Should only contain red fruits (apple, strawberry, raspberry)
    result = eval(out)
    expected = [
        {
            "id": 1,
            "name": "apple",
            "calories": 52,
            "color": "red",
            "ftype": "fruit",
            "tags": ["fruit", "sweet", "fresh"],
        },
        {
            "id": 4,
            "name": "strawberry",
            "calories": 32,
            "color": "red",
            "ftype": "berry",
            "tags": ["berry", "sweet", "fresh"],
        },
        {"id": 6, "name": "raspberry", "calories": 52, "color": "red", "ftype": "berry", "tags": ["berry", "fresh"]},
    ]
    assert result == expected


def test_filter_field_by_calories_less_than_51(make_ctx):
    """Test filter_field operator filtering fruits by calories <= 50."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("fruits, filter_field calories <= 50, :list")

    # Should only contain fruits with calories <= 50
    # strawberry: 32, pineapple: 50, orange: 47
    result = eval(out)
    expected = [
        {
            "id": 2,
            "name": "orange",
            "calories": 47,
            "color": "orange",
            "ftype": "fruit",
            "tags": ["fruit", "sweet", "citrus"],
        },
        {
            "id": 4,
            "name": "strawberry",
            "calories": 32,
            "color": "red",
            "ftype": "berry",
            "tags": ["berry", "sweet", "fresh"],
        },
        {
            "id": 8,
            "name": "pineapple",
            "calories": 50,
            "color": "yellow",
            "ftype": "fruit",
            "tags": ["fruit", "tropical"],
        },
    ]
    assert result == expected


def test_filter_field_with_none_values(make_ctx):
    """Test filter_field operator with is/is not for None values."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("fruits, filter_field calories is None, :list")

    # Should only contain ambrosia (calories: None)
    result = eval(out)
    expected = [{"id": 10, "name": "ambrosia", "calories": None, "color": None, "ftype": "fruit", "tags": []}]
    assert result == expected

    # Test is not None
    forest, attrs, render_specs, out = qp.execute_query("fruits, filter_field calories 'is not' None, :list")

    # Should contain all fruits except ambrosia
    result = eval(out)
    assert len(result) == 9
    # Verify ambrosia is not in the results
    assert all(item["name"] != "ambrosia" for item in result)


def test_extend_by_attribute_translate_ru(make_ctx):
    """Test extend_by_attribute creates children from attribute values."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("fruits, extend_by_attribute translate_ru, :list")

    # Each fruit should have its Russian translation as a child
    assert "яблоко" in out  # apple
    assert "апельсин" in out  # orange


def test_extend_by_attribute_dict_key(make_ctx):
    """Test extend_by_attribute falls back to dict key lookup."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("fruits, extend_by_attribute name, :list")

    # Each fruit dict should have its 'name' value as a child
    assert "apple" in out
    assert "orange" in out


def test_extend_by_attribute_empty_value_skipped(make_ctx):
    """Test extend_by_attribute skips items where attribute returns None."""
    # pfc returns None for fruits not in NUTRITION_DATA; ambrosia has no pfc
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("fruits, extend_by_attribute pfc, :list")

    # Items with None attribute should have no children (not even an empty child)
    result = eval(out)
    for item in result:
        if isinstance(item, list):
            # Child exists — pfc was not None for this fruit
            assert len(item) == 1
        # If not a list, the fruit had no pfc value and was left as-is


def test_extend_multiply_position_query(make_ctx):
    """Test that --position extends only the node it names, through a query.

    UDAN-387: `range`, then extend, then extend only at a specific position.
    """
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    forest, _, _, _ = qp.execute_query("range 3, extend_multiply 2, extend_multiply 3 --position=1")

    # only the second node gets the second extender's children
    assert forest.items == [0, 0, 1, 2, 3, 2, 4]
    assert forest.depths == [0, 1, 0, 1, 1, 0, 1]


def test_group_by_modulo_position_query(make_ctx):
    """Test that --position re-groups only the children of the node it names, through a query."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    forest, _, _, _ = qp.execute_query("range 6, group_by_modulo 2, group_by_modulo 3 --position=1")

    # only the children of group 1(mod 2) are re-grouped by mod 3
    assert forest.items == [
        Group(key="0(mod 2)"),
        0,
        2,
        4,
        Group(key="1(mod 2)"),
        Group(key="1(mod 3)"),
        1,
        Group(key="0(mod 3)"),
        3,
        Group(key="2(mod 3)"),
        5,
    ]
    assert forest.depths == [0, 1, 1, 1, 0, 1, 2, 1, 2, 1, 2]


def test_position_switched_off_applies_everywhere(make_ctx):
    """Test that --position=-1 and --position="" mean no position, like not passing it."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    forest, _, _, _ = qp.execute_query("range 3, extend_multiply 2, extend_multiply 3 --position=-1")

    assert forest.items == [0, 0, 0, 1, 2, 3, 2, 4, 6]
    assert forest.depths == [0, 1, 1, 0, 1, 1, 0, 1, 1]

    forest_empty, _, _, _ = qp.execute_query('range 3, extend_multiply 2, extend_multiply 3 --position=""')
    assert forest_empty.items == forest.items
    assert forest_empty.depths == forest.depths


def test_filter_even_lazy_on_depth_all_query(make_ctx):
    """Test that --on-depth=all filters every level, through a query.

    UDAN-392: `range 3, extend_shift_lazy, filter_even_lazy --on-depth=all` used to
    raise "TypeError: --on-depth must be an integer"; one stage now filters every
    depth instead of one --on-depth=N stage per depth.
    """
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    forest, _, _, _ = qp.execute_query("range 3, extend_shift_lazy, filter_even_lazy --on-depth=all")

    # extend_shift_lazy: 0->[0, 1], 1->[10, 11], 2->[20, 21]; the filter keeps the even
    # items at every level, so the odd 1 loses its children with it
    assert forest.items == [0, 0, 2, 20]
    assert forest.depths == [0, 1, 0, 1]


def test_extend_multiply_on_depth_leaf_query(make_ctx):
    """Test that --on-depth=leaf extends only the nodes without children, through a query."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    forest, _, _, _ = qp.execute_query("range 3, extend_multiply 2, extend_multiply 3 --on-depth=leaf")

    # the leaves are the depth-1 nodes 0, 2 and 4, and only they get the x3 children
    assert forest.items == [0, 0, 0, 1, 2, 6, 2, 4, 12]
    assert forest.depths == [0, 1, 2, 0, 1, 2, 0, 1, 2]
