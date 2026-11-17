"""Unit tests for the orchestrator's chain walk.

The walk reads the resolved chain from the forest's children, groups the consecutive
items by their handler, and hands each group over: a run of operators is one engine
call, an attribute group is one runtime call, each over the stage the previous groups
produced. These tests pin the grouping, the order, the item cap, the introspection
guard and the end pass.
"""

import pytest

import tests.plugins_test
import tests.plugins_test_lazy_attrs as lazy_module
from tests.conftest import make_qp, register_tools_from_module
from udan.attributes import plugins_aggregates_attribute, plugins_operators_attribute
from udan.attributes.api_attribute_runtime import AttributeRuntimeAPI
from udan.attributes.plugins_attributes import AttributeRuntime
from udan.core.api_attributes import AttributeDescriptor
from udan.core.api_query_processor import QueryProcessorAPI
from udan.operator.plugins_operator import OperatorsEngine
from udan.parsing.api_query_parser import QueryParserAPI
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.plugins_tools_examples import plugins_builtins

ITEM_CAP = 7


@pytest.fixture
def ctx_walk(make_ctx):
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, tests.plugins_test.__name__)
    register_tools_from_module(ctx, plugins_aggregates_attribute.__name__)
    return ctx


@pytest.fixture
def qp(ctx_walk) -> QueryProcessorAPI:
    return ctx_walk.container.get(QueryProcessorAPI)


@pytest.fixture
def group_calls(monkeypatch):
    """Record the (service family, descriptor names, item cap) of every chain group."""
    calls: list[tuple[str, list[str], int | None]] = []
    engine_step = OperatorsEngine.apply_chain_step
    runtime_step = AttributeRuntime.apply_chain_step

    def engine_spy(self, descriptors, stage, attr_context, ctx_, item_cap=None):
        calls.append(("engine", [d.name for d in descriptors], item_cap))
        return engine_step(self, descriptors, stage, attr_context, ctx_, item_cap)

    def runtime_spy(self, descriptors, stage, attr_context, ctx_, item_cap=None):
        calls.append(("runtime", [d.name for d in descriptors], item_cap))
        return runtime_step(self, descriptors, stage, attr_context, ctx_, item_cap)

    monkeypatch.setattr(OperatorsEngine, "apply_chain_step", engine_spy)
    monkeypatch.setattr(AttributeRuntime, "apply_chain_step", runtime_spy)
    return calls


def _resolve(qp, ctx, query):
    exec_ctx = ctx.create_exec_context()
    parser = ctx.container.get(QueryParserAPI)
    query_tree = parser.parse_text_to_tree(query, exec_ctx)
    return qp.resolve_query(query_tree, exec_ctx)


def test_resolver_keeps_attribute_nodes_in_the_chain(qp, ctx_walk):
    forest, attrs, _renders = _resolve(qp, ctx_walk, "insert_fruits, count, greps banana")

    assert [(depth, type(item).__name__) for depth, item in forest.as_pairs()] == [
        (0, "OperatorDescriptor"),
        (0, "AttributeDescriptor"),
        (0, "OperatorDescriptor"),
    ]
    assert [item.name for item in forest.items] == ["insert_fruits", "count", "greps"]
    assert [at_d.name for at_d in attrs] == ["count"]


def test_walk_applies_one_group_per_service_in_written_order(qp, ctx_walk, group_calls):
    exec_ctx = ctx_walk.create_exec_context()
    forest, _attrs, _renders = _resolve(qp, ctx_walk, "insert_fruits, count, greps banana")
    attr_context = ctx_walk.container.get(AttributeRuntimeAPI).create_attributes_context(
        attribute_storage=ctx_walk.container.get(AttributeRuntimeAPI).attribute_storage,
        requested_attributes=forest.types.flattened_requested(),
        ctx=exec_ctx,
    )

    ctx_walk._apply_chain(forest, attr_context, exec_ctx, item_cap=ITEM_CAP)

    assert group_calls == [
        ("engine", ["insert_fruits"], None),
        ("runtime", ["count"], None),
        ("engine", ["greps"], ITEM_CAP),
    ]


def test_walk_sends_a_run_of_same_kind_operators_as_one_group(qp, ctx_walk, group_calls):
    """Consecutive operators of one kind form one group; different kinds form separate ones.

    Every operator kind is a plugin kind with its own chain service, so a run of
    mixed kinds is one group per kind, in written order - a run the same kind's
    service applies together is still one group.
    """
    exec_ctx = ctx_walk.create_exec_context()
    forest, _attrs, _renders = _resolve(qp, ctx_walk, "insert_numbers, filter_keep_div 2, filter_keep_div 3")
    attr_context = ctx_walk.container.get(AttributeRuntimeAPI).create_attributes_context(
        attribute_storage=ctx_walk.container.get(AttributeRuntimeAPI).attribute_storage,
        requested_attributes=forest.types.flattened_requested(),
        ctx=exec_ctx,
    )

    ctx_walk._apply_chain(forest, attr_context, exec_ctx)

    assert group_calls == [
        ("engine", ["insert_numbers"], None),
        ("engine", ["filter_keep_div", "filter_keep_div"], None),
    ]


def test_walk_returns_the_attributes_it_applied(qp, ctx_walk):
    exec_ctx = ctx_walk.create_exec_context()
    forest, _attrs, _renders = _resolve(qp, ctx_walk, "insert_fruits, count, greps banana")
    attr_context = ctx_walk.container.get(AttributeRuntimeAPI).create_attributes_context(
        attribute_storage=ctx_walk.container.get(AttributeRuntimeAPI).attribute_storage,
        requested_attributes=forest.types.flattened_requested(),
        ctx=exec_ctx,
    )

    _stage, applied = ctx_walk._apply_chain(forest, attr_context, exec_ctx)

    # The walk returns everything it applied; the attribute part of it is what the
    # end pass skips, so that is what this pins
    assert [d for d in applied if isinstance(d, AttributeDescriptor)] == [AttributeDescriptor.create("count")]


def test_walk_applies_a_data_literal_chain(qp, ctx_walk, group_calls):
    exec_ctx = ctx_walk.create_exec_context()
    forest, _attrs, _renders = _resolve(qp, ctx_walk, '"banana", greps banana')
    attr_context = ctx_walk.container.get(AttributeRuntimeAPI).create_attributes_context(
        attribute_storage=ctx_walk.container.get(AttributeRuntimeAPI).attribute_storage,
        requested_attributes=forest.types.flattened_requested(),
        ctx=exec_ctx,
    )

    stage, applied = ctx_walk._apply_chain(forest, attr_context, exec_ctx)

    assert stage.items == ["banana"]
    assert [d for d in applied if isinstance(d, AttributeDescriptor)] == []
    assert group_calls == [("engine", ["greps"], None)]


def test_walk_leaves_a_chain_without_operators_untouched(qp, ctx_walk, group_calls):
    exec_ctx = ctx_walk.create_exec_context()
    forest, _attrs, _renders = _resolve(qp, ctx_walk, "insert_fruits")
    attr_context = ctx_walk.container.get(AttributeRuntimeAPI).create_attributes_context(
        attribute_storage=ctx_walk.container.get(AttributeRuntimeAPI).attribute_storage,
        requested_attributes=forest.types.flattened_requested(),
        ctx=exec_ctx,
    )

    stage, applied = ctx_walk._apply_chain(forest, attr_context, exec_ctx)

    assert [d for d in applied if isinstance(d, AttributeDescriptor)] == []
    assert group_calls == [("engine", ["insert_fruits"], None)]
    assert len(stage.items) == 10


def test_walk_appends_data_written_after_a_group(qp, ctx_walk, group_calls):
    """A literal after an operator joins the stage when the operator has run.

    `insert_numbers; 7` resolves to the chain [insert_numbers, 7]: the operator
    produces 0, 1, 2 and the literal lands after them, not before.
    """
    exec_ctx = ctx_walk.create_exec_context()
    forest, _attrs, _renders = _resolve(qp, ctx_walk, "insert_numbers; 7")
    attr_context = ctx_walk.container.get(AttributeRuntimeAPI).create_attributes_context(
        attribute_storage=ctx_walk.container.get(AttributeRuntimeAPI).attribute_storage,
        requested_attributes=forest.types.flattened_requested(),
        ctx=exec_ctx,
    )

    stage, applied = ctx_walk._apply_chain(forest, attr_context, exec_ctx)

    assert stage.items == [0, 1, 2, 7]
    assert [d for d in applied if isinstance(d, AttributeDescriptor)] == []
    assert group_calls == [("engine", ["insert_numbers"], None)]


def test_walk_interleaves_groups_and_data_in_written_order(qp, ctx_walk, group_calls):
    """Data between two operator runs lands between their outputs."""
    exec_ctx = ctx_walk.create_exec_context()
    forest, _attrs, _renders = _resolve(qp, ctx_walk, "insert_numbers; 7; insert_numbers")
    attr_context = ctx_walk.container.get(AttributeRuntimeAPI).create_attributes_context(
        attribute_storage=ctx_walk.container.get(AttributeRuntimeAPI).attribute_storage,
        requested_attributes=forest.types.flattened_requested(),
        ctx=exec_ctx,
    )

    stage, applied = ctx_walk._apply_chain(forest, attr_context, exec_ctx)

    assert stage.items == [0, 1, 2, 7, 0, 1, 2]
    assert group_calls == [("engine", ["insert_numbers"], None), ("engine", ["insert_numbers"], None)]


def test_introspection_applies_nothing(ctx_walk, group_calls):
    """`range 5, ?` keeps its short-circuit: no group is applied before the override."""
    make_qp(ctx_walk).execute_query("range 5, ?")

    assert group_calls == []


def test_the_end_pass_skips_the_applied_attributes(ctx_walk):
    """An attribute applied at its position is not recomputed over the final forest."""
    register_tools_from_module(ctx_walk, lazy_module.__name__)
    lazy_module.reset_call_log()
    make_qp(ctx_walk).execute_query("range 6, tracked_twice, is_odd")

    assert lazy_module.call_log == {0: 1, 1: 1, 2: 1, 3: 1, 4: 1, 5: 1}
