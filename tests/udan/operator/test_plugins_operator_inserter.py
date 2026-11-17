"""Tests for udan.operator.plugins_operator_inserter: the inserter kind's service.

The applicator is exercised through the operators engine's dispatch (the path an
inserter descriptor nested inside a run takes), and the chain contract through the
orchestrator's routing (the path an inserter chain group takes), so both ways the
service is reached are covered. The registration contract is tested directly: an
engine without the registered applicator does not apply inserters, the
container-built one does. The routing handler is the plugin's verbs: attach adds it,
detach takes it back off, and the routing answers accordingly.
"""

import pytest

import tests.plugins_test
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
from udan.operator.plugins_operator_inserter import INSERTER, InserterApplier, InserterPlugin, _apply_inserter
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


def test_applier_owns_the_inserter_kind():
    """The kind is the package's declaration: the engine's KINDS do not name it."""
    assert InserterApplier.KINDS == (INSERTER,)
    assert INSERTER not in OperatorsEngine.KINDS
    assert INSERTER.query_keyword == "insert"


def test_attach_adds_the_routing_handler_and_detach_takes_it_back_off(make_ctx):
    """The handler joins the routing in place at attach and leaves at detach."""
    ctx = make_ctx(plugins_demo, plugins_builtins, plugins_operators_attribute)
    routing = ctx.container.get(ChainRoutingAPI)
    applier = ctx.container.get(InserterApplier)
    plugin = InserterPlugin()

    ctx.container.call(plugin.detach)
    assert "inserter" not in routing

    ctx.container.call(plugin.attach)
    assert routing["inserter"] is applier


def test_after_detach_an_inserter_chain_finds_no_handler(make_ctx):
    """The routing is consulted live: a query whose chain opens with an inserter gets the advice."""
    ctx = make_ctx(plugins_demo, plugins_builtins, plugins_operators_attribute, tests.plugins_test)
    qp = make_qp(ctx)
    plugin = InserterPlugin()
    ctx.container.call(plugin.detach)

    _forest, _attrs, _render, out = qp.execute_query("insert_test_numbers_1_to_4, filter_keep_div div=2")

    assert out == (
        "A 'inserter' tool forms the chain, but no enabled package applies its kind: the "
        "package owning 'inserter' is not in udan_plugin_modules, so the query cannot run. "
        "Enable that package, or drop the 'inserter' step."
    )


def test_engine_without_the_registered_applicator_applies_no_inserters(make_ctx):
    """The engine knows no inserter: its dispatch learns the kind from the applier's registration."""
    ctx = make_ctx(plugins_demo, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, tests.plugins_test.__name__)
    engine = OperatorsEngine(registry=ctx.registry, types_registry=TypesRegistry())
    exec_ctx = _exec_context(ctx)
    attr_context = _attr_context(ctx, exec_ctx)
    forest = Forest(items=[opd("insert_single_number"), 7, 8], depths=[0, 0, 0])

    with pytest.raises(ValueError, match="Operator with type=inserter not found"):
        engine._apply_operators_in_forest(forest, exec_ctx, attr_context)

    engine.register_applicator(INSERTER, _apply_inserter)

    forest_fixed = engine._apply_operators_in_forest(forest, exec_ctx, attr_context)
    assert forest_fixed.items == [7, 8, 4]
    assert forest_fixed.depths == [0, 0, 0]


def test_inserter_passes_the_stage_through_and_appends_its_items(make_ctx):
    ctx = make_ctx(plugins_demo, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, tests.plugins_test.__name__)

    forest = _apply(ctx, [opd("insert_single_number")], [7, 8], [0, 0])

    assert forest.items == [7, 8, 4]
    assert forest.depths == [0, 0, 0]


def test_applier_chain_step_returns_what_the_engine_step_returns(make_ctx):
    ctx = make_ctx(plugins_demo, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, tests.plugins_test.__name__)
    applier = ctx.container.get(InserterApplier)
    stage = Forest.from_items([])
    exec_ctx = _exec_context(ctx)
    attr_context = _attr_context(ctx, exec_ctx)

    stepped = applier.apply_chain_step([opd("insert_single_number")], stage, attr_context, exec_ctx)
    engine_stepped = _engine(ctx).apply_chain_step([opd("insert_single_number")], stage, attr_context, exec_ctx)

    assert stepped.items == engine_stepped.items == [4]
    assert stepped.depths == engine_stepped.depths == [0]
    assert stepped.types == stage.types


def test_inserter_group_in_a_mixed_chain_keeps_the_written_order(make_ctx):
    """An inserter run is its own chain group now; the routing hands it the chain's opening."""
    ctx = make_ctx(plugins_demo, plugins_builtins, plugins_operators_attribute, tests.plugins_test)
    qp = make_qp(ctx)

    _forest, _attrs, _render, out = qp.execute_query("insert_test_numbers_1_to_4, filter_keep_div div=2")

    # the inserter's group runs over the empty stage the chain starts from, and the
    # filter group runs over what it produced
    assert out == "- 2\n- 4"


def _engine(ctx):
    """The operators engine, resolved from the container the fixture built."""
    return ctx.container.get(OperatorsEngineAPI)
