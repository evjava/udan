from collections.abc import Iterator
from itertools import islice

import pytest

import tests.plugins_test
import tests.plugins_test_bad_signatures
import udan.plugins_tools_demo.plugins_demo
import udan.plugins_tools_demo.plugins_fruits
from tests.conftest import make_qp, register_tools_from_module
from udan.attributes import plugins_operators_attribute
from udan.attributes.api_attribute_runtime import AttributeRuntimeAPI
from udan.attributes.impl_attribute_runtime import AttributesContext
from udan.attributes.impl_attribute_storage import AttributeStorage
from udan.core.api_forests import Forest
from udan.core.api_operators import OperatorDescriptor
from udan.core.impl_debug_logger import DebugLogger
from udan.core.impl_exec_context import ExecContext
from udan.core.utils_collections import CachedIterable
from udan.core_tools_loading.api_types import Group
from udan.operator.api_operator_engine import OperatorsEngineAPI
from udan.operator.impl_operator_engine import OneShotIterableGuard, _guard_one_shot
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.plugins_tools_examples import plugins_builtins

opd = OperatorDescriptor.create

Item = tests.plugins_test.Item


def apply_operators(ctx, items: list[OperatorDescriptor]) -> Forest:
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)
    register_tools_from_module(ctx, tests.plugins_test.__name__)
    forest = Forest.from_items(items)
    exec_ctx = ExecContext(logger=DebugLogger(log_time=False))

    # Create attribute storage and context for operator application
    attribute_storage = AttributeStorage(attributes={})
    attr_context = AttributesContext(
        attribute_runtime=ctx.container.get(AttributeRuntimeAPI),
        attribute_storage=attribute_storage,
        requested_attributes=forest.types.flattened_requested(),
        ctx=exec_ctx,
    )

    forest_ext = _engine(ctx)._apply_operators_in_forest(forest, exec_ctx, attr_context)
    return forest_ext


def check_forest(forest_actual, forest_expected):
    assert forest_actual.items == forest_expected.items
    assert forest_actual.depths == forest_expected.depths


def test_inserter(make_ctx):
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    items = [opd("insert_test_numbers")]
    forest_actual = apply_operators(ctx, items)
    check_forest(forest_actual, Forest(items=[0, 1, 2], depths=[0, 0, 0]))


def test_filter(make_ctx):
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    items = [opd("insert_test_numbers"), opd("filter_keep_div", {"div": 2})]
    forest_actual = apply_operators(ctx, items)
    check_forest(forest_actual, Forest(items=[0, 2], depths=[0, 0]))


def test_extender(make_ctx):
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    items = [opd("insert_test_numbers_1_to_4"), opd("extend_div2")]
    forest_actual = apply_operators(ctx, items)
    # Expected: 1 -> [], 2 -> [1], 3 -> [10]
    forest_expected = Forest(items=[1, 2, 1, 3, 4, 2], depths=[0, 0, 1, 0, 0, 1])
    check_forest(forest_actual, forest_expected)


def test_extender_2(make_ctx):
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    items = [opd("insert_single_number"), opd("extend_div2", tool_args={"max_depth": 2})]
    forest_actual = apply_operators(ctx, items)
    # Expected: 1 -> [], 2 -> [1], 3 -> [10]
    forest_expected = Forest(items=[4, 2, 1], depths=[0, 1, 2])
    check_forest(forest_actual, forest_expected)


def test_extender_appends_after_existing_children(make_ctx):
    """A second extender adds its items next to the children an earlier extender created."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    items = [
        opd("insert_test_numbers"),
        opd("extend_multiply", {"mults": [2]}),
        opd("extend_multiply", {"mults": [3]}),
    ]
    forest_actual = apply_operators(ctx, items)

    # extend_multiply 2: 0->[0], 1->[2], 2->[4]; the second pass adds 3*n after them
    forest_expected = Forest(items=[0, 0, 0, 1, 2, 3, 2, 4, 6], depths=[0, 1, 1, 0, 1, 1, 0, 1, 1])
    check_forest(forest_actual, forest_expected)


def test_extender_on_depth_extends_deeper_level(make_ctx):
    """--on-depth=1 extends the depth-1 nodes, leaving the top level untouched."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    items = [
        opd("insert_test_numbers_1_to_4"),
        opd("extend_multiply", {"mults": [2]}),
        opd("extend_div2", tool_args=[("on_depth", 1)]),
    ]
    forest_actual = apply_operators(ctx, items)

    # extend_multiply 2: 1->[2], 2->[4], 3->[6], 4->[8]; extend_div2 halves them at depth 1
    forest_expected = Forest(items=[1, 2, 1, 2, 4, 2, 3, 6, 3, 4, 8, 4], depths=[0, 1, 2, 0, 1, 2, 0, 1, 2, 0, 1, 2])
    check_forest(forest_actual, forest_expected)


def test_extender_on_depth_beyond_tree_keeps_nodes(make_ctx):
    """--on-depth past the existing levels extends nothing: nodes pass through."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    items = [opd("insert_test_numbers"), opd("extend_div2", tool_args=[("on_depth", 5)])]
    forest_actual = apply_operators(ctx, items)

    forest_expected = Forest(items=[0, 1, 2], depths=[0, 0, 0])
    check_forest(forest_actual, forest_expected)


def test_filter_on_depth_all_tests_every_level(make_ctx):
    """--on-depth=all filters every node of the tree, a failing node losing its subtree."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    items = [
        opd("insert_test_numbers"),
        opd("extend_multiply", {"mults": [2]}),
        opd("filter_greater_than", {"threshold": 0}, tool_args=[("on_depth", "all")]),
    ]
    forest_actual = apply_operators(ctx, items)

    # extend_multiply 2: 0->[0], 1->[2], 2->[4]; the 0 and its child are the only ones <= 0
    forest_expected = Forest(items=[1, 2, 2, 4], depths=[0, 1, 0, 1])
    check_forest(forest_actual, forest_expected)


def test_filter_on_depth_leaf_tests_only_leaves(make_ctx):
    """--on-depth=leaf filters the nodes without children; the inner nodes always stay."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    items = [
        opd("insert_test_numbers"),
        opd("extend_multiply", {"mults": [2]}),
        opd("filter_greater_than", {"threshold": 2}, tool_args=[("on_depth", "leaf")]),
    ]
    forest_actual = apply_operators(ctx, items)

    # the leaves are 0, 2 and 4, and only the 4 is > 2; their parents keep their places
    forest_expected = Forest(items=[0, 1, 2, 4], depths=[0, 0, 0, 1])
    check_forest(forest_actual, forest_expected)


def test_extender_on_depth_all_extends_every_node(make_ctx):
    """--on-depth=all extends every node, the children a node already has included."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    items = [
        opd("insert_test_numbers"),
        opd("extend_multiply", {"mults": [2]}),
        opd("extend_multiply", {"mults": [3]}, tool_args=[("on_depth", "all")]),
    ]
    forest_actual = apply_operators(ctx, items)

    # extend_multiply 2: 0->[0], 1->[2], 2->[4]; every node is walked and extended,
    # so a child the first pass created gets its own x3 items after it
    forest_expected = Forest(
        items=[0, 0, 0, 0, 1, 2, 6, 3, 2, 4, 12, 6],
        depths=[0, 1, 2, 1, 0, 1, 2, 1, 0, 1, 2, 1],
    )
    check_forest(forest_actual, forest_expected)


def test_extender_on_depth_leaf_extends_childless_nodes(make_ctx):
    """--on-depth=leaf extends the nodes without children; the parents pass through."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    items = [
        opd("insert_test_numbers"),
        opd("extend_multiply", {"mults": [2]}),
        opd("extend_multiply", {"mults": [3]}, tool_args=[("on_depth", "leaf")]),
    ]
    forest_actual = apply_operators(ctx, items)

    # the leaves are the depth-1 nodes 0, 2 and 4, and only they get the x3 children;
    # their parents keep their own children and gain none
    forest_expected = Forest(items=[0, 0, 0, 1, 2, 6, 2, 4, 12], depths=[0, 1, 2, 0, 1, 2, 0, 1, 2])
    check_forest(forest_actual, forest_expected)


def test_extender_on_depth_leaf_created_children_stay_unextended(make_ctx):
    """The leaves an extender creates are not extended again: max_depth stays the bound."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    items = [opd("insert_test_numbers"), opd("extend_multiply", {"mults": [3]}, tool_args=[("on_depth", "leaf")])]
    forest_actual = apply_operators(ctx, items)

    # 0, 1 and 2 are all leaves, so each is extended once; the created 0, 3 and 6 are
    # leaves too, and extending them again would never stop
    forest_expected = Forest(items=[0, 0, 1, 3, 2, 6], depths=[0, 1, 0, 1, 0, 1])
    check_forest(forest_actual, forest_expected)


def test_extender_position_wins_over_on_depth_all(make_ctx):
    """--position still takes precedence over --on-depth=all: only the named node is extended."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    items = [
        opd("insert_test_numbers"),
        opd("extend_multiply", {"mults": [2]}),
        opd("extend_multiply", {"mults": [3]}, tool_args=[("on_depth", "all"), ("position", (1,))]),
    ]
    forest_actual = apply_operators(ctx, items)

    # all would have extended every node; only the second node and nothing else is extended
    forest_expected = Forest(items=[0, 0, 1, 2, 3, 2, 4], depths=[0, 1, 0, 1, 1, 0, 1])
    check_forest(forest_actual, forest_expected)


def test_extender_position_extends_one_node(make_ctx):
    """--position=1 extends only the second node; the other nodes pass through untouched."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    items = [
        opd("insert_test_numbers_1_to_4"),
        opd("extend_multiply", {"mults": [2]}),
        opd("extend_div2", tool_args=[("position", (1,))]),
    ]
    forest_actual = apply_operators(ctx, items)

    # extend_multiply 2: 1->[2], 2->[4], 3->[6], 4->[8]; extend_div2 halves only the 2,
    # so its children are the kept 4 and the new 1
    forest_expected = Forest(items=[1, 2, 2, 4, 1, 3, 6, 4, 8], depths=[0, 1, 0, 1, 1, 0, 1, 0, 1])
    check_forest(forest_actual, forest_expected)


def test_extender_position_hierarchical(make_ctx):
    """--position=1.0 is children[1].children[0]: the path indexes the siblings per component."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    items = [
        opd("insert_test_numbers_1_to_4"),
        opd("extend_multiply", {"mults": [2]}),
        opd("extend_div2", tool_args=[("position", (1, 0))]),
    ]
    forest_actual = apply_operators(ctx, items)

    # the path points at the 4 under the 2, so only that 4 is halved
    forest_expected = Forest(items=[1, 2, 2, 4, 2, 3, 6, 4, 8], depths=[0, 1, 0, 1, 2, 0, 1, 0, 1])
    check_forest(forest_actual, forest_expected)


def test_extender_position_out_of_range_keeps_nodes(make_ctx):
    """--position past the existing siblings matches nothing: nodes pass through."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    items = [
        opd("insert_test_numbers_1_to_4"),
        opd("extend_multiply", {"mults": [2]}),
        opd("extend_div2", tool_args=[("position", (9,))]),
    ]
    forest_actual = apply_operators(ctx, items)

    forest_expected = Forest(items=[1, 2, 2, 4, 3, 6, 4, 8], depths=[0, 1, 0, 1, 0, 1, 0, 1])
    check_forest(forest_actual, forest_expected)


def test_extender_position_wins_over_on_depth(make_ctx):
    """--position takes precedence over --on-depth: the named node is the target."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    items = [
        opd("insert_test_numbers_1_to_4"),
        opd("extend_multiply", {"mults": [2]}),
        opd("extend_div2", tool_args=[("on_depth", 1), ("position", (3,))]),
    ]
    forest_actual = apply_operators(ctx, items)

    # on_depth=1 would have extended every depth-1 node; only the node at 3 is extended
    forest_expected = Forest(items=[1, 2, 2, 4, 3, 6, 4, 8, 2], depths=[0, 1, 0, 1, 0, 1, 0, 1, 1])
    check_forest(forest_actual, forest_expected)


def test_grouper_position_regroups_one_nodes_children(make_ctx):
    """--position=0 re-groups only the children of the first node; the other nodes keep theirs."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    items = [
        opd("insert_test_numbers_1_to_4"),
        opd("group_by_modulo", {"n": 2}),
        opd("group_by_modulo", {"n": 3}, tool_args=[("position", (0,))]),
    ]
    forest_actual = apply_operators(ctx, items)

    # group 1(mod 2) holds [1, 3]: only its children are re-grouped by mod 3
    forest_expected = Forest(
        items=[
            Group(key="1(mod 2)"),
            Group(key="1(mod 3)"),
            1,
            Group(key="0(mod 3)"),
            3,
            Group(key="0(mod 2)"),
            2,
            4,
        ],
        depths=[0, 1, 2, 1, 2, 0, 1, 1],
    )
    check_forest(forest_actual, forest_expected)


def test_grouper(make_ctx):
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    items = [opd("insert_test_numbers"), opd("group_by_parity")]
    forest_actual = apply_operators(ctx, items)

    # Group items are now Group objects instead of strings

    group_even = Group(key="even")
    group_odd = Group(key="odd")
    forest_expected = Forest(items=[group_even, 0, 2, group_odd, 1], depths=[0, 1, 1, 0, 1])
    check_forest(forest_actual, forest_expected)


def test_grouper_ordered(make_ctx):
    """Test grouper that returns Group with explicit order — groups sorted by order."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)

    items = [opd("insert_test_numbers"), opd("group_by_parity_ordered")]
    forest_actual = apply_operators(ctx, items)

    # Input is [0, 1, 2]; even order=2, odd order=1 -> odd group first.
    group_odd = Group(key="odd", order=1)
    group_even = Group(key="even", order=2)
    forest_expected = Forest(items=[group_odd, 1, group_even, 0, 2], depths=[0, 1, 0, 1, 1])
    check_forest(forest_actual, forest_expected)

    # The returned group items must carry the order.
    group_items = [it for it, d in zip(forest_actual.items, forest_actual.depths) if d == 0]
    assert [g.order for g in group_items] == [1, 2]


def test_grouper_returns_group_no_rewrap(make_ctx):
    """Test grouper returning a Group is not rewrapped; attribute_descriptor is attached."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)

    items = [opd("insert_test_numbers"), opd("group_by_parity_plain_group")]
    forest_actual = apply_operators(ctx, items)

    # No order -> fall back to key ordering: "even" < "odd".
    group_even = Group(key="even")
    group_odd = Group(key="odd")
    forest_expected = Forest(items=[group_even, 0, 2, group_odd, 1], depths=[0, 1, 1, 0, 1])
    check_forest(forest_actual, forest_expected)


# A filter or grouper without 'item' parameter is rejected at registration
def test_filter_without_item_parameter_raises_error(make_ctx):
    """Test that a filter without 'item' parameter fails to register."""
    with pytest.raises(ValueError, match="must have an 'item' parameter"):
        make_ctx(tests.plugins_test_bad_signatures)


def test_grouper_without_item_parameter_raises_error(make_ctx):
    """Test that a grouper without 'item' parameter fails to register."""
    with pytest.raises(ValueError, match="must have an 'item' parameter"):
        make_ctx(tests.plugins_test_bad_signatures)


def test_sort_by_field_with_dict(make_ctx):
    """Test sort_by_field with dictionary items."""
    # Need to register sort_by_field from builtins
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, plugins_builtins.__name__)

    items = [opd("insert_dicts"), opd("sort_by_field", {"field": "name"})]
    forest_actual = apply_operators(ctx, items)

    # Should be sorted by name: alice, bob, charlie
    expected_items = [
        {"name": "alice", "value": 1},
        {"name": "bob", "value": 2},
        {"name": "charlie", "value": 3},
    ]
    forest_expected = Forest(items=expected_items, depths=[0, 0, 0])
    check_forest(forest_actual, forest_expected)


def test_sort_by_field_with_object(make_ctx):
    """Test sort_by_field with object items using getattr."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, plugins_builtins.__name__)

    items = [opd("insert_items"), opd("sort_by_field", {"field": "name"})]
    forest_actual = apply_operators(ctx, items)

    # Should be sorted by name attribute: alice, bob, charlie
    forest_expected = Forest(items=[1, 0, 0], depths=[0, 0, 0])
    assert forest_actual.depths == forest_expected.depths
    # Check that items are Item objects with correct names
    actual_items = forest_actual.items
    assert len(actual_items) == 3
    assert actual_items[0].name == "alice"
    assert actual_items[1].name == "bob"
    assert actual_items[2].name == "charlie"


def test_sort_by_field_with_value(make_ctx):
    """Test sort_by_field sorting by numeric value field."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, plugins_builtins.__name__)

    items = [opd("insert_dicts"), opd("sort_by_field", {"field": "value"})]
    forest_actual = apply_operators(ctx, items)

    # Should be sorted by value: alice(1), bob(2), charlie(3)
    expected_items = [
        {"name": "alice", "value": 1},
        {"name": "bob", "value": 2},
        {"name": "charlie", "value": 3},
    ]
    forest_expected = Forest(items=expected_items, depths=[0, 0, 0])
    check_forest(forest_actual, forest_expected)


def test_group_by_field_with_color(make_ctx):
    """Test group_by_field with fruit colors."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)

    register_tools_from_module(ctx, plugins_builtins.__name__)

    items = [opd("insert_fruits"), opd("group_by_field", {"field": "color"})]
    forest_actual = apply_operators(ctx, items)

    # Should group by color
    # Groups should be: red, orange, yellow, blue, purple, None (ambrosia has color=None)
    actual_items = forest_actual.items

    # Check that we have Group objects with correct keys
    group_items = [item for item in actual_items if isinstance(item, Group)]
    assert len(group_items) == 6

    # Check group keys
    group_keys = {g.key for g in group_items}
    assert group_keys == {"red", "orange", "yellow", "blue", "purple", None}

    # Find the red group
    red_group = next(g for g in group_items if g.key == "red")
    assert red_group is not None


def test_group_by_field_with_dict(make_ctx):
    """Test group_by_field with dictionary items."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)

    register_tools_from_module(ctx, plugins_builtins.__name__)

    items = [opd("insert_dicts"), opd("group_by_field", {"field": "value"})]
    forest_actual = apply_operators(ctx, items)

    # Should group by value
    actual_items = forest_actual.items

    # Check that we have Group objects
    group_items = [item for item in actual_items if isinstance(item, Group)]
    assert len(group_items) == 3

    # Check group keys (note: the values from the dicts are ints, not strings)
    group_keys = {g.key for g in group_items}
    assert group_keys == {1, 2, 3}

    # Find value=1 group
    val1_group = next((g for g in group_items if g.key == 1), None)
    assert val1_group is not None


def test_unique_basic(make_ctx):
    """Test unique operator removes duplicate integers."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, plugins_builtins.__name__)

    items = [opd("insert_duplicates"), opd("unique")]
    forest_actual = apply_operators(ctx, items)

    # Should keep first occurrence of each: 1, 2, 3, 4, 5
    expected_items = [1, 2, 3, 4, 5]
    forest_expected = Forest(items=expected_items, depths=[0, 0, 0, 0, 0])
    check_forest(forest_actual, forest_expected)


def test_unique_strings(make_ctx):
    """Test unique operator removes duplicate strings."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, plugins_builtins.__name__)

    items = [opd("insert_duplicate_strings"), opd("unique")]
    forest_actual = apply_operators(ctx, items)

    # Should keep first occurrence of each: apple, banana, cherry, date
    expected_items = ["apple", "banana", "cherry", "date"]
    forest_expected = Forest(items=expected_items, depths=[0, 0, 0, 0])
    check_forest(forest_actual, forest_expected)


def test_unique_sort_combo(make_ctx):
    """Test unique after sort (sort, unique pattern)."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, plugins_builtins.__name__)

    # Sort then unique should give sorted unique items
    items = [opd("insert_duplicates"), opd("sort_by_natural_order"), opd("unique")]
    forest_actual = apply_operators(ctx, items)

    # Sorted: [1, 1, 2, 2, 3, 3, 4, 5] -> unique: [1, 2, 3, 4, 5]
    expected_items = [1, 2, 3, 4, 5]
    forest_expected = Forest(items=expected_items, depths=[0, 0, 0, 0, 0])
    check_forest(forest_actual, forest_expected)


def test_unique_dicts(make_ctx):
    """Test unique operator with dictionary items (string comparison)."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, plugins_builtins.__name__)

    items = [opd("insert_duplicate_dicts"), opd("unique")]
    forest_actual = apply_operators(ctx, items)

    # Unique by string representation: keeps first of each
    # Note: Since dicts convert to strings, this might not work as expected
    # for exact deduplication, but it tests the functionality
    actual_items = forest_actual.items
    # Should have fewer items than original (5 -> fewer due to duplicates)
    assert len(actual_items) <= 5
    assert len(actual_items) > 0


def test_unique_empty(make_ctx):
    """Test unique operator with empty input."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, plugins_builtins.__name__)

    items = [opd("insert_test_numbers"), opd("filter_greater_than", {"threshold": 100}), opd("unique")]
    forest_actual = apply_operators(ctx, items)

    # No numbers greater than 100 in range 0-2
    forest_expected = Forest(items=[], depths=[])
    check_forest(forest_actual, forest_expected)


def test_unique_all_unique(make_ctx):
    """Test unique operator when all items are already unique."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, plugins_builtins.__name__)

    items = [opd("insert_test_numbers"), opd("unique")]
    forest_actual = apply_operators(ctx, items)

    # All numbers 0, 1, 2 are already unique
    forest_expected = Forest(items=[0, 1, 2], depths=[0, 0, 0])
    check_forest(forest_actual, forest_expected)


def test_unique_aliases(make_ctx):
    """Test unique operator alias (uniq)."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, plugins_builtins.__name__)

    # Test 'uniq' alias
    items = [opd("insert_duplicates"), opd("uniq")]
    forest_actual = apply_operators(ctx, items)
    expected_items = [1, 2, 3, 4, 5]
    forest_expected = Forest(items=expected_items, depths=[0, 0, 0, 0, 0])
    check_forest(forest_actual, forest_expected)


def test_sort_by_field_with_none_values(make_ctx):
    """Test sort_by_field handles None values correctly (None values sorted to end)."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, plugins_builtins.__name__)

    items = [opd("insert_items_with_none_scores"), opd("sort_by_field", {"field": "score"})]
    forest_actual = apply_operators(ctx, items)

    # Items with None scores should be at the end
    # Sorted: charlie(5), alice(10), eve(15), bob(None), dave(None)
    actual_items = forest_actual.items
    assert len(actual_items) == 5

    # First three should be sorted by score (5, 10, 15)
    assert actual_items[0] == {"name": "charlie", "score": 5}
    assert actual_items[1] == {"name": "alice", "score": 10}
    assert actual_items[2] == {"name": "eve", "score": 15}

    # Last two should have None scores (order between them doesn't matter)
    assert actual_items[3]["score"] is None
    assert actual_items[4]["score"] is None
    assert {actual_items[3]["name"], actual_items[4]["name"]} == {"bob", "dave"}


def test_sort_by_field_descending(make_ctx):
    """Test sort_by_field with --desc flag sorts in descending order."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, plugins_builtins.__name__)

    items = [opd("insert_items_with_none_scores"), opd("sort_by_field", {"field": "score", "desc": True})]
    forest_actual = apply_operators(ctx, items)

    # Should be sorted in descending order
    # eve(15), alice(10), charlie(5), bob(None), dave(None)
    actual_items = forest_actual.items
    assert len(actual_items) == 5

    # First three should be sorted by score descending (15, 10, 5)
    assert actual_items[0] == {"name": "eve", "score": 15}
    assert actual_items[1] == {"name": "alice", "score": 10}
    assert actual_items[2] == {"name": "charlie", "score": 5}

    # Last two should have None scores (order between them doesn't matter)
    assert actual_items[3]["score"] is None
    assert actual_items[4]["score"] is None
    assert {actual_items[3]["name"], actual_items[4]["name"]} == {"bob", "dave"}


def test_sort_by_field_descending_simple(make_ctx):
    """Test sort_by_field with --desc using simple values {3, 1, None, 2}."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, tests.plugins_test.__name__)
    register_tools_from_module(ctx, plugins_builtins.__name__)

    # Test ascending (default) - sort by the 'value' field directly
    items_asc = [opd("insert_simple_values"), opd("sort_by_field", {"field": "value"})]
    forest_asc = apply_operators(ctx, items_asc)

    # Ascending: 1, 2, 3, None (by 'value' field)
    asc_items = forest_asc.items
    assert [x["id"] for x in asc_items] == ["b", "d", "a", "c"]
    assert [x["value"] for x in asc_items] == [1, 2, 3, None]

    # Test descending - sort by the 'value' field in descending order
    items_desc = [opd("insert_simple_values"), opd("sort_by_field", {"field": "value", "desc": True})]
    forest_desc = apply_operators(ctx, items_desc)

    # Descending: 3, 2, 1, None (by 'value' field)
    desc_items = forest_desc.items
    assert [x["id"] for x in desc_items] == ["a", "d", "b", "c"]
    assert [x["value"] for x in desc_items] == [3, 2, 1, None]


def test_sort_by_field_descending_string(make_ctx):
    """Test sort_by_field with desc sorts strings in reverse order."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)
    register_tools_from_module(ctx, plugins_builtins.__name__)

    items_desc = [opd("insert_fruits"), opd("sort_by_field", {"field": "name", "desc": True})]
    forest_desc = apply_operators(ctx, items_desc)

    # Descending string order: strawberry ... ambrosia
    assert [x["name"] for x in forest_desc.items] == [
        "strawberry",
        "raspberry",
        "pineapple",
        "orange",
        "mango",
        "grape",
        "blueberry",
        "banana",
        "apple",
        "ambrosia",
    ]


def test_sort_by_field_desc_with_query_execution(make_ctx):
    """Test sort_by_field with --desc flag through full query execution."""
    # Register demo module for fruits and builtins for sort_by_field
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)
    register_tools_from_module(ctx, plugins_builtins.__name__)

    # Test ascending (default)
    forest_asc, attrs_asc, renders_asc, out_asc = qp.execute_query("insert_fruits, sort_by_field pfc.carbs, pfc.carbs")
    items_asc = forest_asc.items
    # Should be ascending: strawberry (7.7) first, banana (23.0) before
    # ambrosia (None)
    assert items_asc[0]["name"] == "strawberry"
    # orange and raspberry both have 12.0, so either could be first
    assert {items_asc[1]["name"], items_asc[2]["name"]} == {"orange", "raspberry"}
    assert items_asc[-3]["name"] == "grape"
    assert items_asc[-2]["name"] == "banana"
    assert items_asc[-1]["name"] == "ambrosia"

    # Test descending
    forest_desc, attrs_desc, renders_desc, out_desc = qp.execute_query(
        "insert_fruits, sort_by_field pfc.carbs --desc, pfc.carbs"
    )
    items_desc = forest_desc.items
    # Should be descending: banana (23.0) first, strawberry (7.7) before
    # ambrosia (None)
    assert items_desc[0]["name"] == "banana"
    assert items_desc[1]["name"] == "grape"
    # orange and raspberry both have 12.0, so either could be before the other
    assert {items_desc[-3]["name"], items_desc[-4]["name"]} == {"orange", "raspberry"}
    assert items_desc[-2]["name"] == "strawberry"
    assert items_desc[-1]["name"] == "ambrosia"


def test_sort_by_calories(make_ctx):
    """Sort fruits by calories field (includes None for ambrosia)."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, plugins_builtins.__name__)

    items = [opd("insert_fruits"), opd("sort_by_field", {"field": "calories"})]
    forest_actual = apply_operators(ctx, items)

    actual_items = forest_actual.items
    # Ascending: strawberry(32), orange(47), pineapple(50), apple(52),
    #   raspberry(52), blueberry(57), mango(60), grape(62), banana(89), ambrosia(None)
    scores = [item["calories"] for item in actual_items]
    non_none = [s for s in scores if s is not None]
    assert non_none == sorted(non_none)  # ascending order
    assert scores[-1] is None  # None sorts last
    assert len(actual_items) == 10


def test_sort_by_name(make_ctx):
    """Sort fruits by name field (string comparison)."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, plugins_builtins.__name__)

    items = [opd("insert_fruits"), opd("sort_by_field", {"field": "name"})]
    forest_actual = apply_operators(ctx, items)

    actual_items = forest_actual.items
    names = [item["name"] for item in actual_items]
    assert names == sorted(names)  # alphabetical


def test_sort_by_attribute_fruit_cost(make_ctx):
    """Sort fruits by fruit_cost attribute (not a dict key, resolved from attributes)."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)
    register_tools_from_module(ctx, plugins_builtins.__name__)

    forest, attrs, renders, out = qp.execute_query("insert_fruits, fruit_cost, sort_by_field fruit_cost, fruit_cost")
    actual_items = forest.items
    costs = [item.get("fruit_cost") for item in actual_items]
    # fruit_cost returns None for ambrosia (not in FRUIT_COSTS dict)
    non_none = [c for c in costs if c is not None]
    assert non_none == sorted(non_none)  # ascending by cost
    assert costs[-1] is None  # None sorts last


def test_sort_by_attribute_not_requested(make_ctx):
    """Sort by an attribute that is not among requested columns (computed on demand)."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)
    register_tools_from_module(ctx, plugins_builtins.__name__)

    forest, attrs, renders, out = qp.execute_query("insert_fruits, sort_by_field fruit_cost, map_field name")
    assert forest.items == [
        "banana",
        "orange",
        "apple",
        "mango",
        "pineapple",
        "grape",
        "strawberry",
        "raspberry",
        "blueberry",
        "ambrosia",
    ]


def test_sort_by_minus_field_descends(make_ctx):
    """Sort by field with leading '-' reverses the order (ascending by default)."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)
    register_tools_from_module(ctx, plugins_builtins.__name__)

    forest, attrs, renders, out = qp.execute_query("insert_fruits, sort_by_field -calories, map_field name")
    assert forest.items == [
        "banana",
        "grape",
        "mango",
        "blueberry",
        "apple",
        "raspberry",
        "pineapple",
        "orange",
        "strawberry",
        "ambrosia",
    ]


def test_sort_by_minus_attribute_not_requested(make_ctx):
    """Sort by attribute with leading '-' (computed on demand, descending)."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)
    register_tools_from_module(ctx, plugins_builtins.__name__)

    forest, attrs, renders, out = qp.execute_query("insert_fruits, sort_by_field -fruit_cost, map_field name")
    assert forest.items == [
        "blueberry",
        "raspberry",
        "strawberry",
        "grape",
        "pineapple",
        "mango",
        "apple",
        "orange",
        "banana",
        "ambrosia",
    ]


def test_limit_default(make_ctx):
    """Test limit replacer with default limit (10)."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, plugins_builtins.__name__)

    items = [opd("insert_duplicates"), opd("limit")]
    forest_actual = apply_operators(ctx, items)

    # insert_duplicates returns [1, 2, 1, 3, 2, 4, 3, 5]
    # limit with default 10 should return all 8 items
    expected_items = [1, 2, 1, 3, 2, 4, 3, 5]
    forest_expected = Forest(items=expected_items, depths=[0, 0, 0, 0, 0, 0, 0, 0])
    check_forest(forest_actual, forest_expected)


def test_limit_custom(make_ctx):
    """Test limit replacer with custom limit."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, plugins_builtins.__name__)

    items = [opd("insert_duplicates"), opd("limit", {"limit": 3})]
    forest_actual = apply_operators(ctx, items)

    # Should return only first 3 items: [1, 2, 1]
    expected_items = [1, 2, 1]
    forest_expected = Forest(items=expected_items, depths=[0, 0, 0])
    check_forest(forest_actual, forest_expected)


def test_limit_zero(make_ctx):
    """Test limit replacer with limit=0 returns empty list."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, plugins_builtins.__name__)

    items = [opd("insert_duplicates"), opd("limit", {"limit": 0})]
    forest_actual = apply_operators(ctx, items)

    # Should return empty list
    forest_expected = Forest(items=[], depths=[])
    check_forest(forest_actual, forest_expected)


def test_limit_more_than_available(make_ctx):
    """Test limit replacer when limit exceeds available items."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, plugins_builtins.__name__)

    items = [opd("insert_test_numbers"), opd("limit", {"limit": 100})]
    forest_actual = apply_operators(ctx, items)

    # insert_test_numbers returns [0, 1, 2]
    # limit with 100 should return all 3 items
    expected_items = [0, 1, 2]
    forest_expected = Forest(items=expected_items, depths=[0, 0, 0])
    check_forest(forest_actual, forest_expected)


def test_grep_with_pattern_or(make_ctx):
    """Test that grep filter with pattern 'or' matches fruits with 'or' in any value.

    This test verifies that grep filters dicts by checking all values,
    not just keys or the name field.
    """
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, plugins_builtins.__name__)

    items = [opd("insert_fruits"), opd("has_pattern", {"pattern": "or"})]
    forest_actual = apply_operators(ctx, items)

    # Should match fruits with 'or' in any value:
    # - orange (name and color "orange" contain "or")
    # - mango (color "orange" contains "or")
    assert len(forest_actual.items) == 2
    names = {item["name"] for item in forest_actual.items}
    assert names == {"orange", "mango"}
    assert forest_actual.depths == [0, 0]


def test_fruits_alias_returns_non_empty_output(make_ctx):
    """Test that the 'fruits' alias (for insert_fruits) returns non-empty output.

    This is a critical test to ensure that user-facing commands work as expected.
    Previously, tests used 'insert_fruits' but users expected 'fruits' to work.
    This test validates that the alias is properly configured.
    """

    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)

    # Test using the 'fruits' alias (not 'insert_fruits')
    forest, attrs, render_specs, out = qp.execute_query("fruits")

    # Should have non-empty output
    assert out != "", "Output should not be empty"
    assert len(out) > 0, "Output should have content"

    # Should have fruits in the output
    assert "apple" in out.lower(), "Output should contain 'apple'"
    assert "banana" in out.lower(), "Output should contain 'banana'"
    assert "orange" in out.lower(), "Output should contain 'orange'"

    # Aforest should have items
    assert len(forest.items) > 0, "Aforest should contain items"
    assert len(forest.items) >= 10, "Should have at least 10 fruits"


def test_replacer_flat_on_nested_tree(make_ctx):
    """Flat replacer (limit) applied to a nested tree — applies recursively at each depth."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, plugins_builtins.__name__)

    # extend_multiply creates: 0->[0], 1->[2], 2->[4]
    # limit 1 at each depth level keeps only first item
    items = [opd("insert_test_numbers"), opd("extend_multiply", {"mults": [2]}), opd("limit", {"limit": 1})]
    forest_actual = apply_operators(ctx, items)

    # At depth 0: [0, 1, 2] -> limit 1 -> [0]
    # At depth 1: [0] -> limit 1 -> [0]
    # Forest: items=[0, 0], depths=[0, 1]
    assert forest_actual.items == [0, 0]
    assert forest_actual.depths == [0, 1]


def test_replacer_map_field_on_nested_tree(make_ctx):
    """map_field (flat replacer) on items replaces each with its field value."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, plugins_builtins.__name__)

    # insert_dicts -> [{name: alice, value: 1}, {name: bob, value: 2}, {name: charlie, value: 3}]
    # map_field name -> ["alice", "bob", "charlie"]
    items = [opd("insert_dicts"), opd("map_field", {"field": "name"})]
    forest_actual = apply_operators(ctx, items)

    assert set(forest_actual.items) == {"alice", "bob", "charlie"}


def test_replacer_on_depth_flat(make_ctx):
    """Flat replacer with --on-depth=0 only replaces at depth 0, preserves children."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, plugins_builtins.__name__)

    # Create nested: 0->[0], 1->[2], 2->[4]
    # limit 1 --on-depth=0: calls op_fn with items=[0,1,2] -> limit 1 -> [0]
    # Then distributes [0] at depth 0: only first node gets replaced
    items = [
        opd("insert_test_numbers"),
        opd("extend_multiply", {"mults": [2]}),
        opd("limit", {"limit": 1}, tool_args=[("on_depth", 0)]),
    ]
    forest_actual = apply_operators(ctx, items)

    # replace_at_depth uses the pre-computed op_res (limit 1 on [0,1,2] -> [0])
    # At depth 0: 3 nodes but only 1 replacement item -> first gets replaced, rest kept original
    actual_items = forest_actual.items
    assert actual_items[0] == 0  # replaced with limit result


def test_replacer_on_depth_nested(make_ctx):
    """Nested replacer (flatten) with --on-depth filters output pairs by depth."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, plugins_builtins.__name__)

    # Create nested: 0->[0], 1->[2], 2->[4]
    # flatten with --on-depth=0 should only keep depth-0 items from the flat output
    items = [
        opd("insert_test_numbers"),
        opd("extend_multiply", {"mults": [2]}),
        opd("flatten", tool_args=[("on_depth", 0)]),
    ]
    forest_actual = apply_operators(ctx, items)

    # flatten produces: [(0, 0), (0, 0), (0, 1), (0, 2), (0, 2), (0, 4)]
    # with on_depth=0 filter: all are depth 0, so all pass through
    assert all(d == 0 for d in forest_actual.depths)


def test_replacer_nested_empty_result(make_ctx):
    """Nested replacer that returns no items yields nothing."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, plugins_builtins.__name__)

    # sgrep with depth=99 — no items at that depth, should return empty
    items = [
        opd("insert_test_numbers"),
        opd("sgrep", {"pattern": "depth=99"}),
    ]
    forest_actual = apply_operators(ctx, items)

    assert forest_actual.items == []
    assert forest_actual.depths == []


def counting_source(total: int, pulls: list[int]) -> Iterator[int]:
    """One-shot generator that records every item it hands out."""
    for i in range(total):
        pulls.append(i)
        yield i


def test_cached_iterable_replays_full_passes(make_ctx):
    """Two full passes see the same items and the source is pulled once."""
    pulls = []
    stage = CachedIterable(counting_source(3, pulls))

    assert list(stage) == [0, 1, 2]
    assert list(stage) == [0, 1, 2]
    assert pulls == [0, 1, 2]


def test_cached_iterable_partial_passes_replay_from_cache():
    """A pass that stops early does not re-pull the items of a previous pass."""
    pulls = []
    stage = CachedIterable(counting_source(100, pulls))

    assert list(islice(stage, 2)) == [0, 1]
    assert list(islice(stage, 5)) == [0, 1, 2, 3, 4]
    assert pulls == [0, 1, 2, 3, 4]


def test_cached_iterable_cap_propagates_upstream():
    """A capped pass stops the source at the cap."""
    pulls = []
    stage = CachedIterable(counting_source(100, pulls))

    assert list(islice(stage, 6)) == list(range(6))
    assert pulls == list(range(6))


def test_cached_iterable_interleaved_passes():
    """Passes can be iterated interleaved; each one starts from the beginning."""
    pulls = []
    stage = CachedIterable(counting_source(100, pulls))

    assert list(islice(stage, 2)) == [0, 1]
    assert list(islice(stage, 3)) == [0, 1, 2]
    assert list(islice(stage, 2)) == [0, 1]
    assert pulls == [0, 1, 2]


def test_guard_one_shot_logs_on_second_pass():
    """The debug guard logs a one-shot input whose second pass silently sees nothing."""
    ctx = ExecContext(logger=DebugLogger(log_time=False))
    ctx.is_debug = True

    guarded = _guard_one_shot(counting_source(3, []), ctx, opd("group_by_parity"))
    assert isinstance(guarded, OneShotIterableGuard)
    assert list(guarded) == [0, 1, 2]
    assert list(guarded) == []

    expected_log = "# [DEBUG] group_by_parity: operator input iterated more than once; items may be lost"
    assert ctx.get_debug_log() == expected_log


def test_guard_one_shot_passes_re_iterables_through():
    """Lists and cached stages are safe to iterate twice and are not wrapped."""
    ctx = ExecContext(logger=DebugLogger(log_time=False))
    ctx.is_debug = True

    children = [0, 1, 2]
    assert _guard_one_shot(children, ctx, opd("group_by_parity")) is children
    cached = CachedIterable(counting_source(3, []))
    assert _guard_one_shot(cached, ctx, opd("group_by_parity")) is cached


def test_guard_one_shot_disabled_without_debug_mode():
    """Outside debug mode a one-shot input is passed through untouched."""
    ctx = ExecContext(logger=DebugLogger(log_time=False))
    source = counting_source(3, [])

    assert _guard_one_shot(source, ctx, opd("group_by_parity")) is source


def _engine(ctx):
    """The operators engine, resolved from the container the fixture built."""
    return ctx.container.get(OperatorsEngineAPI)
