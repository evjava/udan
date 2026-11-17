"""Tests for udan.operator.plugins_operator_extender: the extender kind's service.

The applicator is exercised through the operators engine's dispatch (the path an
extender descriptor nested inside a run takes), and the chain contract through the
orchestrator's routing (the path an extender chain group takes), so both ways the
service is reached are covered. The registration contract is tested directly: an
engine without the registered applicator does not apply extenders, the
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
from udan.operator.plugins_operator_extender import EXTENDER, ExtenderApplier, ExtenderPlugin, _apply_extender
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


def test_applier_owns_the_extender_kind():
    """The kind is the package's declaration: the engine's KINDS do not name it."""
    assert ExtenderApplier.KINDS == (EXTENDER,)
    assert EXTENDER not in OperatorsEngine.KINDS
    assert EXTENDER.query_keyword == "extend"


def test_attach_adds_the_routing_handler_and_detach_takes_it_back_off(make_ctx):
    """The handler joins the routing in place at attach and leaves at detach."""
    ctx = make_ctx(plugins_demo, plugins_builtins, plugins_operators_attribute)
    routing = ctx.container.get(ChainRoutingAPI)
    applier = ctx.container.get(ExtenderApplier)
    plugin = ExtenderPlugin()

    ctx.container.call(plugin.detach)
    assert "extender" not in routing

    ctx.container.call(plugin.attach)
    assert routing["extender"] is applier


def test_after_detach_an_extender_chain_finds_no_handler(make_ctx):
    """The routing is consulted live: a query whose chain has an extender step gets the advice."""
    ctx = make_ctx(plugins_demo, plugins_builtins, plugins_operators_attribute, tests.plugins_test)
    qp = make_qp(ctx)
    plugin = ExtenderPlugin()
    ctx.container.call(plugin.detach)

    _forest, _attrs, _render, out = qp.execute_query("insert_test_numbers_1_to_4, extend_div2")

    assert out == (
        "A 'extender' tool forms the chain, but no enabled package applies its kind: the "
        "package owning 'extender' is not in udan_plugin_modules, so the query cannot run. "
        "Enable that package, or drop the 'extender' step."
    )


def test_engine_without_the_registered_applicator_applies_no_extenders(make_ctx):
    """The engine knows no extender: its dispatch learns the kind from the applier's registration."""
    ctx = make_ctx(plugins_demo, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, tests.plugins_test.__name__)
    engine = OperatorsEngine(registry=ctx.registry, types_registry=TypesRegistry())
    exec_ctx = _exec_context(ctx)
    attr_context = _attr_context(ctx, exec_ctx)
    forest = Forest(items=[opd("extend_div2"), 2, 4], depths=[0, 0, 0])

    with pytest.raises(ValueError, match="Operator with type=extender not found"):
        engine._apply_operators_in_forest(forest, exec_ctx, attr_context)

    engine.register_applicator(EXTENDER, _apply_extender)

    forest_fixed = engine._apply_operators_in_forest(forest, exec_ctx, attr_context)
    assert forest_fixed.items == [2, 1, 4, 2]
    assert forest_fixed.depths == [0, 1, 0, 1]


def test_extender_extends_the_level_and_keeps_the_items(make_ctx):
    ctx = make_ctx(plugins_demo, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, tests.plugins_test.__name__)

    forest = _apply(ctx, [opd("insert_test_numbers_1_to_4"), opd("extend_div2")], [], [])

    assert forest.items == [1, 2, 1, 3, 4, 2]
    assert forest.depths == [0, 0, 1, 0, 0, 1]


def test_extender_on_depth_extends_the_named_level(make_ctx):
    ctx = make_ctx(plugins_demo, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, tests.plugins_test.__name__)

    forest = _apply(
        ctx,
        [
            opd("insert_test_numbers_1_to_4"),
            opd("extend_multiply", {"mults": [2]}),
            opd("extend_div2", tool_args=[("on_depth", 1)]),
        ],
        [],
        [],
    )

    assert forest.items == [1, 2, 1, 2, 4, 2, 3, 6, 3, 4, 8, 4]
    assert forest.depths == [0, 1, 2, 0, 1, 2, 0, 1, 2, 0, 1, 2]


def test_extender_position_extends_one_node(make_ctx):
    ctx = make_ctx(plugins_demo, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, tests.plugins_test.__name__)

    forest = _apply(
        ctx,
        [
            opd("insert_test_numbers_1_to_4"),
            opd("extend_multiply", {"mults": [2]}),
            opd("extend_div2", tool_args=[("position", (1,))]),
        ],
        [],
        [],
    )

    assert forest.items == [1, 2, 2, 4, 1, 3, 6, 4, 8]
    assert forest.depths == [0, 1, 0, 1, 1, 0, 1, 0, 1]


def test_extender_max_depth_reapplies_to_the_created_items(make_ctx):
    ctx = make_ctx(plugins_demo, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, tests.plugins_test.__name__)

    forest = _apply(
        ctx,
        [opd("insert_single_number"), opd("extend_div2", tool_args=[("max_depth", 2)])],
        [],
        [],
    )

    assert forest.items == [4, 2, 1]
    assert forest.depths == [0, 1, 2]


def test_applier_chain_step_returns_what_the_engine_step_returns(make_ctx):
    ctx = make_ctx(plugins_demo, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, tests.plugins_test.__name__)
    applier = ctx.container.get(ExtenderApplier)
    stage = Forest.from_items([1, 2])
    exec_ctx = _exec_context(ctx)
    attr_context = _attr_context(ctx, exec_ctx)

    stepped = applier.apply_chain_step([opd("extend_div2")], stage, attr_context, exec_ctx)
    engine_stepped = _engine(ctx).apply_chain_step([opd("extend_div2")], stage, attr_context, exec_ctx)

    assert stepped.items == engine_stepped.items == [1, 2, 1]
    assert stepped.depths == engine_stepped.depths == [0, 0, 1]
    assert stepped.types == stage.types


def test_extender_group_in_a_mixed_chain_keeps_the_written_order(make_ctx):
    """An extender run is its own chain group now; the written order still decides what applies."""
    ctx = make_ctx(plugins_demo, plugins_builtins, plugins_operators_attribute, tests.plugins_test)
    qp = make_qp(ctx)

    _forest, _attrs, _render, out_extender_first = qp.execute_query(
        "insert_test_numbers_1_to_4, extend_div2, filter_keep_div div=2 --on-depth=all"
    )
    _forest, _attrs, _render, out_filter_first = qp.execute_query(
        "insert_test_numbers_1_to_4, filter_keep_div div=2 --on-depth=all, extend_div2"
    )

    # extender first: the 1 the extender created under the 2 is filtered out afterwards;
    # filter first: the extender extends the two survivors, keeping what it created
    assert out_extender_first == "- 2\n- 4\n  - 2"
    assert out_filter_first == "- 2\n  - 1\n- 4\n  - 2"


def _engine(ctx):
    """The operators engine, resolved from the container the fixture built."""
    return ctx.container.get(OperatorsEngineAPI)
