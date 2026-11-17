"""Tests for udan.operator.plugins_operator_mapper: the mapper kind's service.

The applicator is exercised through the operators engine's dispatch (the path a
mapper descriptor nested inside a run takes), and the chain contract through the
orchestrator's routing (the path a mapper chain group takes), so both ways the
service is reached are covered. The registration contract is tested directly: an
engine without the registered applicator does not apply mappers, the
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
from udan.operator.plugins_operator_mapper import MAPPER, MapperApplier, MapperPlugin, _apply_mapper
from udan.plugins_tools_demo import plugins_demo
from udan.plugins_tools_examples import plugins_builtins, plugins_peval

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


def test_applier_owns_the_mapper_kind():
    """The kind is the package's declaration: the engine's KINDS do not name it."""
    assert MapperApplier.KINDS == (MAPPER,)
    assert MAPPER not in OperatorsEngine.KINDS
    assert MAPPER.query_keyword is None
    assert MAPPER.rewrites_items is True


def test_attach_adds_the_routing_handler_and_detach_takes_it_back_off(make_ctx):
    """The handler joins the routing in place at attach and leaves at detach."""
    ctx = make_ctx(plugins_demo, plugins_builtins, plugins_operators_attribute)
    routing = ctx.container.get(ChainRoutingAPI)
    applier = ctx.container.get(MapperApplier)
    plugin = MapperPlugin()

    ctx.container.call(plugin.detach)
    assert "mapper" not in routing

    ctx.container.call(plugin.attach)
    assert routing["mapper"] is applier


def test_after_detach_a_mapper_chain_finds_no_handler(make_ctx):
    """The routing is consulted live: a query whose chain has a mapper step gets the advice."""
    ctx = make_ctx(plugins_demo, plugins_builtins, plugins_operators_attribute, tests.plugins_test, plugins_peval)
    qp = make_qp(ctx)
    plugin = MapperPlugin()
    ctx.container.call(plugin.detach)

    _forest, _attrs, _render, out = qp.execute_query('insert_test_numbers_1_to_4, peval "it * 10"')

    assert out == (
        "A 'mapper' tool forms the chain, but no enabled package applies its kind: the "
        "package owning 'mapper' is not in udan_plugin_modules, so the query cannot run. "
        "Enable that package, or drop the 'mapper' step."
    )


def test_engine_without_the_registered_applicator_applies_no_mappers(make_ctx):
    """The engine knows no mapper: its dispatch learns the kind from the applier's registration."""
    ctx = make_ctx(plugins_demo, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, plugins_peval.__name__)
    engine = OperatorsEngine(registry=ctx.registry, types_registry=TypesRegistry())
    exec_ctx = _exec_context(ctx)
    attr_context = _attr_context(ctx, exec_ctx)
    forest = Forest(items=[opd("peval", {"expr": "it * 2"}), 3, 4], depths=[0, 0, 0])

    with pytest.raises(ValueError, match="Operator with type=mapper not found"):
        engine._apply_operators_in_forest(forest, exec_ctx, attr_context)

    engine.register_applicator(MAPPER, _apply_mapper)

    forest_fixed = engine._apply_operators_in_forest(forest, exec_ctx, attr_context)
    assert forest_fixed.items == [6, 8]
    assert forest_fixed.depths == [0, 0]


def test_mapper_rewrites_the_items_and_keeps_the_shape(make_ctx):
    ctx = make_ctx(plugins_demo, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, plugins_peval.__name__)

    forest = _apply(ctx, [opd("peval", {"expr": "it * 2"})], [3, 4], [0, 0])

    assert forest.items == [6, 8]
    assert forest.depths == [0, 0]


def test_applier_chain_step_returns_what_the_engine_step_returns(make_ctx):
    ctx = make_ctx(plugins_demo, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, plugins_peval.__name__)
    applier = ctx.container.get(MapperApplier)
    stage = Forest.from_items([3, 4])
    exec_ctx = _exec_context(ctx)
    attr_context = _attr_context(ctx, exec_ctx)

    stepped = applier.apply_chain_step([opd("peval", {"expr": "it * 2"})], stage, attr_context, exec_ctx)
    engine_stepped = _engine(ctx).apply_chain_step([opd("peval", {"expr": "it * 2"})], stage, attr_context, exec_ctx)

    assert stepped.items == engine_stepped.items == [6, 8]
    assert stepped.depths == engine_stepped.depths == [0, 0]
    assert stepped.types == stage.types


def test_mapper_group_in_a_mixed_chain_keeps_the_written_order(make_ctx):
    """A mapper run is its own chain group now; the written order still decides what applies."""
    ctx = make_ctx(plugins_demo, plugins_builtins, plugins_operators_attribute, tests.plugins_test, plugins_peval)
    qp = make_qp(ctx)

    _forest, _attrs, _render, out_mapper_first = qp.execute_query(
        'insert_test_numbers_1_to_4, peval "it * 10", filter_greater_than threshold=20'
    )
    _forest, _attrs, _render, out_filter_first = qp.execute_query(
        'insert_test_numbers_1_to_4, filter_greater_than threshold=2, peval "it * 10"'
    )

    # the mapper rewrites every item either way, so the two orders read the same;
    # which group the filter belongs to is what the written order decides
    assert out_mapper_first == "- 30\n- 40"
    assert out_filter_first == "- 30\n- 40"


def _engine(ctx):
    """The operators engine, resolved from the container the fixture built."""
    return ctx.container.get(OperatorsEngineAPI)
