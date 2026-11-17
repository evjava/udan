"""Tests for udan.operator.plugins_operator_replacer: the replacer kind's service.

The applicator is exercised through the operators engine's dispatch (the path a
replacer descriptor nested inside a run takes), and the chain contract through the
orchestrator's routing (the path a replacer chain group takes), so both ways the
service is reached are covered. The registration contract is tested directly: an
engine without the registered applicator does not apply replacers, the
container-built one does. The routing handler is the plugin's verbs: attach adds it,
detach takes it back off, and the routing answers accordingly.
"""

import pytest

import tests.plugins_test
import tests.plugins_test_replacer
from tests.conftest import make_qp, register_tools_from_module
from udan.attributes import plugins_operators_attribute
from udan.attributes.api_attribute_runtime import AttributeRuntimeAPI
from udan.attributes.impl_attribute_storage import AttributeStorage
from udan.core.api_chain_routing import ChainRoutingAPI
from udan.core.api_forests import Forest
from udan.core.api_operators import OperatorDescriptor
from udan.core.impl_debug_logger import DebugLogger
from udan.core.impl_exec_context import ExecContext
from udan.core.impl_types_registry import TypesRegistry
from udan.operator.api_operator_engine import OperatorsEngineAPI
from udan.operator.plugins_operator import OperatorsEngine
from udan.operator.plugins_operator_replacer import REPLACER, ReplacerApplier, ReplacerPlugin, _apply_replacer
from udan.plugins_tools_demo import plugins_demo
from udan.plugins_tools_examples import plugins_builtins

opd = OperatorDescriptor.create


def _exec_context(ctx):
    return ExecContext(logger=DebugLogger(log_time=False), symbols_env=ctx.symbols_env)


def _attr_context(ctx, exec_ctx):
    return ctx.container.get(AttributeRuntimeAPI).create_attributes_context(
        attribute_storage=AttributeStorage(), requested_attributes=[], ctx=exec_ctx
    )


def _apply(ctx, descriptors, items, depths):
    """Run descriptors over a stage through the engine walk, the shape a chain step wraps."""
    exec_ctx = _exec_context(ctx)
    attr_context = _attr_context(ctx, exec_ctx)
    forest = Forest(items=[*descriptors, *items], depths=[0] * len(descriptors) + depths)
    return _engine(ctx)._apply_operators_in_forest(forest, exec_ctx, attr_context)


def test_applier_owns_the_replacer_kind():
    """The kind is the package's declaration: the engine's KINDS do not name it."""
    assert ReplacerApplier.KINDS == (REPLACER,)
    assert REPLACER not in OperatorsEngine.KINDS
    assert REPLACER.query_keyword == "replace"


def test_attach_adds_the_routing_handler_and_detach_takes_it_back_off(make_ctx):
    """The handler joins the routing in place at attach and leaves at detach."""
    ctx = make_ctx(plugins_demo, plugins_builtins, plugins_operators_attribute)
    routing = ctx.container.get(ChainRoutingAPI)
    applier = ctx.container.get(ReplacerApplier)
    plugin = ReplacerPlugin()

    ctx.container.call(plugin.detach)
    assert "replacer" not in routing

    ctx.container.call(plugin.attach)
    assert routing["replacer"] is applier


def test_after_detach_a_replacer_chain_finds_no_handler(make_ctx):
    """The routing is consulted live: a query whose chain has a replacer step gets the advice."""
    ctx = make_ctx(
        plugins_demo, plugins_builtins, plugins_operators_attribute, tests.plugins_test, tests.plugins_test_replacer
    )
    qp = make_qp(ctx)
    plugin = ReplacerPlugin()
    ctx.container.call(plugin.detach)

    _forest, _attrs, _render, out = qp.execute_query("insert_test_numbers_1_to_4, replacer_upper")

    assert out == (
        "A 'replacer' tool forms the chain, but no enabled package applies its kind: the "
        "package owning 'replacer' is not in udan_plugin_modules, so the query cannot run. "
        "Enable that package, or drop the 'replacer' step."
    )


def test_engine_without_the_registered_applicator_applies_no_replacers(make_ctx):
    """The engine knows no replacer: its dispatch learns the kind from the applier's registration."""
    ctx = make_ctx(plugins_demo, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, tests.plugins_test_replacer.__name__)
    engine = OperatorsEngine(registry=ctx.registry, types_registry=TypesRegistry())
    exec_ctx = _exec_context(ctx)
    attr_context = _attr_context(ctx, exec_ctx)
    forest = Forest(items=[opd("replacer_upper"), "a", "b"], depths=[0, 0, 0])

    with pytest.raises(ValueError, match="Operator with type=replacer not found"):
        engine._apply_operators_in_forest(forest, exec_ctx, attr_context)

    engine.register_applicator(REPLACER, _apply_replacer)

    forest_fixed = engine._apply_operators_in_forest(forest, exec_ctx, attr_context)
    assert forest_fixed.items == ["A", "B"]
    assert forest_fixed.depths == [0, 0]


def test_flat_replacer_replaces_per_level_and_keeps_the_shape(make_ctx):
    ctx = make_ctx(plugins_demo, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, tests.plugins_test_replacer.__name__)

    forest = _apply(ctx, [opd("replacer_upper")], ["a", "b", "c", "d", "e", "f"], [0, 0, 0, 1, 1, 1])

    assert forest.items == ["A", "B", "C", "D", "E", "F"]
    assert forest.depths == [0, 0, 0, 1, 1, 1]


def test_nested_replacer_turns_depth_item_pairs_back_into_nodes(make_ctx):
    ctx = make_ctx(plugins_demo, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, tests.plugins_test.__name__)

    # extend_multiply: 0 -> [0], 1 -> [2], 2 -> [4]; flatten flattens the tree to depth 0
    forest = _apply(ctx, [opd("insert_test_numbers"), opd("extend_multiply", {"mults": [2]}), opd("flatten")], [], [])

    assert forest.items == [0, 0, 1, 2, 2, 4]
    assert forest.depths == [0, 0, 0, 0, 0, 0]


def test_nested_replacer_receives_the_nodes_it_declares(make_ctx):
    """`sgrep depth=1` declares `nodes` and reads the subtree through them; the package's
    own nested replacer returns the pairs it was handed."""
    ctx = make_ctx(plugins_demo, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, tests.plugins_test.__name__)
    register_tools_from_module(ctx, tests.plugins_test_replacer.__name__)

    for op_d, expected in (
        (opd("sgrep", {"pattern": "depth=1"}), ([0, 2, 4], [0, 0, 0])),
        (opd("replacer_depths"), ([0, 0, 1, 2, 2, 4], [0, 1, 0, 1, 0, 1])),
    ):
        forest = _apply(
            ctx,
            [opd("insert_test_numbers"), opd("extend_multiply", {"mults": [2]}), op_d],
            [],
            [],
        )

        assert forest.items == expected[0]
        assert forest.depths == expected[1]


def test_applier_chain_step_returns_what_the_engine_step_returns(make_ctx):
    ctx = make_ctx(plugins_demo, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, tests.plugins_test_replacer.__name__)
    applier = ctx.container.get(ReplacerApplier)
    stage = Forest.from_items(["a", "b", "c"])
    exec_ctx = _exec_context(ctx)
    attr_context = _attr_context(ctx, exec_ctx)

    stepped = applier.apply_chain_step([opd("replacer_upper")], stage, attr_context, exec_ctx)
    engine_stepped = _engine(ctx).apply_chain_step([opd("replacer_upper")], stage, attr_context, exec_ctx)

    assert stepped.items == engine_stepped.items == ["A", "B", "C"]
    assert stepped.depths == engine_stepped.depths == [0, 0, 0]
    assert stepped.types == stage.types


def test_replacer_group_in_a_mixed_chain_keeps_the_written_order(make_ctx):
    """A replacer run is its own chain group now; the written order still decides what applies."""
    ctx = make_ctx(
        plugins_demo, plugins_builtins, plugins_operators_attribute, tests.plugins_test, tests.plugins_test_replacer
    )
    qp = make_qp(ctx)

    _forest, _attrs, _render, out_first = qp.execute_query("insert_test_numbers_1_to_4, replacer_upper, limit 2")
    _forest, _attrs, _render, out_second = qp.execute_query("insert_test_numbers_1_to_4, limit 2, replacer_upper")
    _forest, _attrs, _render, out_third = qp.execute_query("insert_test_numbers_1_to_4, limit 2, filter_keep_div div=2")
    _forest, _attrs, _render, out_fourth = qp.execute_query(
        "insert_test_numbers_1_to_4, filter_keep_div div=2, limit 2"
    )

    assert out_first == "- 1\n- 2"
    assert out_second == "- 1\n- 2"
    assert out_third == "- 2"
    assert out_fourth == "- 2\n- 4"


def _engine(ctx):
    """The operators engine, resolved from the container the fixture built."""
    return ctx.container.get(OperatorsEngineAPI)
