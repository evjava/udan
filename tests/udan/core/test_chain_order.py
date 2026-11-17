"""Behaviour tests for the chain order of tools.

A tool is applied at the chain position it is written at: an aggregate answers
"what exists here", a per-item attribute computes for the items that exist at its
position, and a filter after either of them selects from the values already produced.
The table below is the UDAN-391 acceptance set.
"""

import pytest

import tests.plugins_test_lazy_attrs as lazy_module
from tests.conftest import make_qp, register_tools_from_module
from udan.attributes import plugins_aggregates_attribute, plugins_operators_attribute
from udan.attributes.api_attribute_runtime import AttributeRuntimeAPI
from udan.attributes.api_attribute_storage import AttributeStorageAPI
from udan.core.api_attributes import AttributeDescriptor
from udan.plugins_tools_core import plugins_help, plugins_system
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.plugins_tools_examples import plugins_builtins, plugins_builtins_set_operations
from udan.renders import plugins_renders

ROOT_ITEM = "forest"

# Fruit calories (ambrosia has None, skipped by sum): count=10, sum=501


@pytest.fixture
def ctx_order(make_ctx):
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_help,
        plugins_operators_attribute,
        plugins_renders,
        plugins_system,
    )
    register_tools_from_module(ctx, plugins_aggregates_attribute.__name__)
    register_tools_from_module(ctx, plugins_builtins_set_operations.__name__)
    register_tools_from_module(ctx, lazy_module.__name__)
    return ctx


@pytest.fixture
def qp(ctx_order):
    return make_qp(ctx_order)


def _get_agg(ctx, name):
    """Get an aggregate value from attribute storage by identity."""
    storage = ctx.container.get(AttributeStorageAPI)
    for at_d, values in storage.attributes.items():
        if at_d.name == name:
            return values.get(ROOT_ITEM)
    return None


# --- the UDAN-391 table: an aggregate is computed over the items of its position ---


def test_count_over_all_items(qp, ctx_order):
    qp.execute_query("insert_fruits, count")
    assert _get_agg(ctx_order, "count") == 10


def test_count_after_filter_is_unchanged(qp, ctx_order):
    qp.execute_query("insert_fruits, greps banana, count")
    assert _get_agg(ctx_order, "count") == 1


def test_count_before_filter_answers_its_position(qp, ctx_order):
    forest, _attrs, _render, out = qp.execute_query("insert_fruits, count, greps banana")

    assert forest.items[0]["name"] == "banana"
    assert len(forest.items) == 1
    assert out.strip().split("\n")[-1] == "# count: 10"


def test_two_filters_around_an_aggregate(qp, ctx_order):
    forest, _attrs, _render, out = qp.execute_query("insert_fruits, greps berry, count, greps banana")

    assert forest.items == []
    assert out.strip().split("\n")[-1] == "# count: 3"


def test_aggregates_chain_independently(qp, ctx_order):
    forest, _attrs, _render, out = qp.execute_query("insert_fruits, count, greps banana, sum calories")

    assert len(forest.items) == 1
    lines = out.strip().split("\n")
    assert lines[-2:] == ["# count: 10", "# sum: 89"]


# --- per-item attributes at their position ---


def test_attribute_before_a_filter_computes_at_position(qp, ctx_order):
    """The filter selects from the values the attribute computed before it."""
    lazy_module.reset_call_log()
    forest, _attrs, _render, _out = qp.execute_query("range 6, tracked_even, filter_by_attribute tracked_even == True")

    assert forest.items == [0, 2, 4]
    assert lazy_module.call_log == {0: 1, 1: 1, 2: 1, 3: 1, 4: 1, 5: 1}


def test_attribute_after_a_filter_computes_for_survivors(qp, ctx_order):
    lazy_module.reset_call_log()
    forest, _attrs, _render, _out = qp.execute_query("range 6, is_odd, tracked_twice")

    assert forest.items == [1, 3, 5]
    assert lazy_module.call_log == {1: 1, 3: 1, 5: 1}


def test_attribute_value_is_present_on_the_surviving_item(qp, ctx_order):
    forest, _attrs, _render, _out = qp.execute_query("insert_fruits, fruit_cost, greps banana")

    assert len(forest.items) == 1
    storage = ctx_order.container.get(AttributeRuntimeAPI).attribute_storage
    value = storage.get_attr_value(AttributeDescriptor.create("fruit_cost"), forest.items[0])
    assert value == 0.5


# --- aggregates over groups and nested trees ---


def test_count_over_grouped_items(qp, ctx_order):
    forest, _attrs, _render, out = qp.execute_query("insert_fruits, group_by_field color, count")

    assert len(forest.items) == 16
    assert out.strip().split("\n")[-1] == "# count: 10"


def test_count_over_two_level_grouping(qp, ctx_order):
    forest, _attrs, _render, _out = qp.execute_query("insert_fruits, group_by_field color, group_by_field name, count")

    assert len(forest.items) == 26
    assert _get_agg(ctx_order, "count") == 10


def test_count_over_an_extender_tree(qp, ctx_order):
    """An extender's subtrees carry their own aggregate; the root counts the leaves."""
    forest, _attrs, _render, out = qp.execute_query("range 3, extend_multiply 2, count")

    assert len(forest.items) == 6
    assert out.strip().split("\n")[-1] == "# count: 3"


# --- columns, unique, limit, splices ---


def test_cattr_column_summed_after_the_chain(qp, ctx_order):
    forest, _attrs, _render, out = qp.execute_query("range 6, cattr 'it * 2' --name=d, sum d")

    assert len(forest.items) == 6
    assert out.strip().split("\n")[-1] == "# sum: 30"


def test_unique_and_limit_still_apply_in_chain(qp, ctx_order):
    _forest, _attrs, _render, out = qp.execute_query("range 6, extend_multiply 1, unique, limit 3")
    lines = [line for line in out.strip().split("\n") if line.startswith("- ")]
    assert lines == ["- 0", "- 1", "- 2"]


def test_variable_splice_keeps_the_chain(qp, ctx_order):
    forest, _attrs, _render, _out = qp.execute_query("v := insert_fruits; $v, greps banana")

    assert len(forest.items) == 1
    assert forest.items[0]["name"] == "banana"


def test_variable_spliced_aggregate_answers_its_position(qp, ctx_order):
    _forest, _attrs, _render, out = qp.execute_query("v := insert_fruits, count; $v, greps banana")

    assert out.strip().split("\n")[-1] == "# count: 10"


def test_aggregate_inside_a_subquery_argument_does_not_leak(qp, ctx_order):
    """A nested chain item is not data: it stays out of the argument's items."""
    forest, _attrs, _render, _out = qp.execute_query("difference (range 3, count) (range 2)")

    assert forest.items == [2]


# --- introspection keeps its short-circuit ---


def test_introspection_renders_without_applying_the_chain(qp, ctx_order):
    """Nothing applies before the override: no operator run, no attribute computation."""
    lazy_module.reset_call_log()
    forest, _attrs, _render, out = qp.execute_query("range 5, tracked_twice, ?", debug=True)

    assert forest is not None
    assert lazy_module.call_log == {}
    assert "applying operator: " not in out
