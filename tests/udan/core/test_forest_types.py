"""Tests for ForestTypeDescriptor: item types folded from the operator chain onto Forest."""

import pytest

from tests.conftest import make_qp
from udan.attributes import plugins_operators_attribute
from udan.attributes.api_attribute_runtime import AttributeRuntimeAPI
from udan.attributes.api_attribute_storage import AttributeStorageAPI
from udan.core.api_attributes import AttributeDescriptor
from udan.core.api_forests import EMPTY_FOREST, Forest, Node
from udan.core.api_operators import OperatorDescriptor
from udan.core.api_query_processor import QueryProcessorAPI
from udan.core.api_type_system import ForestTypeDescriptor
from udan.core_tools_loading.api_types import TypeDescriptor
from udan.operator.api_operator_engine import OperatorsEngineAPI
from udan.plugins_history import plugins_history
from udan.plugins_tools_core import plugins_help, plugins_system
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.plugins_tools_examples import plugins_builtins
from udan.renders import plugins_renders

DEBUG_LINE = "# [DEBUG] forest types: [dict/fruit{fruit_cost}]"


def _query_forest(ctx, query: str) -> Forest:
    qp = make_qp(ctx)
    """Execute a query through the public API and return the forest."""
    return qp.execute_query(query)[0]


# --------------------------------------------------------------------------
# Inserters
# --------------------------------------------------------------------------


def test_inserter_fruits_declares_dict(make_ctx):
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("fruits")

    assert forest.types.depths == [TypeDescriptor(name="dict", semantic="fruit")]
    assert forest.items[0]["name"] == "apple"


def test_inserter_range_declares_int(make_ctx):
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 5")

    assert forest.types.depths == [TypeDescriptor(name="int")]
    assert forest.items == [0, 1, 2, 3, 4]


# --------------------------------------------------------------------------
# Extenders
# --------------------------------------------------------------------------


def test_extender_appends_dict_level(make_ctx):
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("fruits, similar_fruits")

    fruit_dict = TypeDescriptor(name="dict", semantic="fruit")
    assert forest.types.depths == [fruit_dict, fruit_dict]


def test_extender_appends_int_level(make_ctx):
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 5, extend_multiply")

    assert forest.types.depths == [TypeDescriptor(name="int"), TypeDescriptor(name="int")]


# --------------------------------------------------------------------------
# Attributes
# --------------------------------------------------------------------------


def test_attribute_attaches_to_deepest_level(make_ctx):
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("fruits, fruit_cost")

    assert forest.types.depths == [
        TypeDescriptor(name="dict", semantic="fruit", requested=[AttributeDescriptor.create("fruit_cost")])
    ]
    assert attrs == forest.types.flattened_requested()


def test_attribute_attaches_to_second_level(make_ctx):
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("fruits, similar_fruits, fruit_cost")

    assert forest.types.depths[0] == TypeDescriptor(name="dict", semantic="fruit")
    assert forest.types.depths[1] == TypeDescriptor(
        name="dict", semantic="fruit", requested=[AttributeDescriptor.create("fruit_cost")]
    )
    assert forest.types.flattened_requested() == [AttributeDescriptor.create("fruit_cost")]


def test_attributes_keep_level_order(make_ctx):
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("fruits, pfc, similar_fruits, fruit_cost")

    assert [at_d.name for at_d in forest.types.flattened_requested()] == ["pfc", "fruit_cost"]


def test_cattr_column_attaches_to_source_level(make_ctx):
    """cattr is a pass-through extender: its column is an attribute of the source level.

    It creates no child level (the operator returns []), and the column is requested
    once per query, not once per item.
    """
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 3, cattr 'is_odd(it + 1)' --name=n1")

    assert forest.types.depths == [TypeDescriptor(name="int", requested=[AttributeDescriptor.create("n1")])]
    assert attrs == [AttributeDescriptor.create("n1")]
    assert out.splitlines() == ["- 0 :: True", "- 1 :: False", "- 2 :: True"]


def test_cattr_columns_keep_request_order(make_ctx):
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query(
        "range 6, cattr 'is_odd(it + 1)' --name=n1, cattr 'n1 == True' --name=n2"
    )

    assert forest.types.depths == [
        TypeDescriptor(name="int", requested=[AttributeDescriptor.create("n1"), AttributeDescriptor.create("n2")])
    ]
    assert attrs == [AttributeDescriptor.create("n1"), AttributeDescriptor.create("n2")]


# --------------------------------------------------------------------------
# Filters, groupers, variables, unknown chains
# --------------------------------------------------------------------------


def test_filter_keeps_types(make_ctx):
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("fruits, limit 2")

    assert forest.types.depths == [TypeDescriptor(name="dict", semantic="fruit")]


def test_grouper_prepends_group_level(make_ctx):
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 6, group_by_modulo 2")

    assert forest.types.depths == [TypeDescriptor(name="group"), TypeDescriptor(name="int")]


def test_variable_reference_folds_spliced_items(make_ctx):
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("f := fruits, similar_fruits; $f")

    fruit_dict = TypeDescriptor(name="dict", semantic="fruit")
    assert forest.types.depths == [fruit_dict, fruit_dict]


def test_types_after_transition_table(make_ctx):
    """Unit test of the fold table (12-31 doc T1): one step per operator kind."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
    )
    fold = ctx.container.get(QueryProcessorAPI)._types_after
    fruits = ForestTypeDescriptor.from_created_level("dict")
    literal = Node.leaf("apple")

    assert fold(fruits, literal) == ForestTypeDescriptor.unknown()
    assert fold(fruits, None) == fruits
    assert fold(fruits, Node.leaf(AttributeDescriptor.create("fruit_cost"))) == fruits
    assert fold(fruits, Node.leaf(OperatorDescriptor.create("limit"))) == fruits


# --------------------------------------------------------------------------
# Representation
# --------------------------------------------------------------------------


def test_type_descriptor_str():
    assert str(TypeDescriptor(name="dict")) == "dict"
    assert str(TypeDescriptor(name="dict", semantic="fruit")) == "dict/fruit"
    assert str(TypeDescriptor(name="dict", requested=[AttributeDescriptor.create("fruit_cost")])) == "dict{fruit_cost}"


def test_forest_type_descriptor_str():
    assert str(ForestTypeDescriptor()) == "[]"
    assert str(ForestTypeDescriptor(depths=[TypeDescriptor(name="group")])) == "[group]"
    fruits = ForestTypeDescriptor(depths=[TypeDescriptor(name="dict")])
    assert str(fruits.with_requested(AttributeDescriptor.create("fruit_cost"))) == "[dict{fruit_cost}]"


def test_descriptor_repr_is_short():
    assert repr(ForestTypeDescriptor(depths=[TypeDescriptor(name="int")])) == "[int]"


# --------------------------------------------------------------------------
# Non-nullable types on Forest
# --------------------------------------------------------------------------


def test_forest_types_never_none():
    forest = Forest.from_items([1, 2])

    assert isinstance(forest.types, ForestTypeDescriptor)
    assert forest.types.depths == []
    assert EMPTY_FOREST.types.depths == []


def test_with_attribute_explicit_level():
    fruits = ForestTypeDescriptor.from_created_level("dict").with_appended_level("dict")

    level_zero = fruits.with_requested(AttributeDescriptor.create("fruit_cost"), level=0)
    assert str(level_zero) == "[dict{fruit_cost}, dict]"
    assert str(fruits) == "[dict, dict]"

    with pytest.raises(ValueError):
        fruits.with_requested(AttributeDescriptor.create("fruit_cost"), level=5)


# --------------------------------------------------------------------------
# Types survive the operator engine
# --------------------------------------------------------------------------


def test_engine_carries_types_without_recomputing(make_ctx):
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
    )
    forest = _query_forest(ctx, "range 5, extend_multiply")

    exec_ctx = ctx.create_exec_context()
    attr_context = ctx.container.get(AttributeRuntimeAPI).create_attributes_context(
        attribute_storage=ctx.container.get(AttributeStorageAPI),
        requested_attributes=forest.types.flattened_requested(),
        ctx=exec_ctx,
    )
    forest_exp = _engine(ctx)._apply_operators_in_forest(forest, exec_ctx, attr_context)

    assert forest_exp.types.depths == [TypeDescriptor(name="int"), TypeDescriptor(name="int")]


def test_auto_limit_keeps_types(make_ctx):
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 200")

    assert forest.types.depths == [TypeDescriptor(name="int")]


def test_introspection_override_reports_unknown(make_ctx):
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("fruits, ?")

    assert forest.types.depths == []


# --------------------------------------------------------------------------
# DEBUG surface
# --------------------------------------------------------------------------


def test_debug_line_shows_forest_types(make_ctx):
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("fruits, fruit_cost", debug=True)

    assert DEBUG_LINE in out.splitlines()


def test_debug_line_shows_cattr_column_once(make_ctx):
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
    )
    qp = make_qp(ctx)
    _, _, _, out = qp.execute_query("range 3, cattr 'is_odd(it + 1)' --name=n1", debug=True)

    assert "# [DEBUG] forest types: [int{n1}]" in out.splitlines()


def test_debug_line_shows_forest_types_on_introspection_override(make_ctx):
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
    )
    qp = make_qp(ctx)
    _, _, _, out = qp.execute_query("fruits, ?", debug=True)

    assert "# [DEBUG] forest types: []" in out.splitlines()


def _engine(ctx):
    """The operators engine, resolved from the container the fixture built."""
    return ctx.container.get(OperatorsEngineAPI)
