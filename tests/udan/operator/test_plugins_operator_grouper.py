"""Tests for udan.operator.plugins_operator_grouper: the grouper kind's service.

The applicator is exercised through the operators engine's dispatch (the path a
grouper descriptor nested inside a run takes), and the chain contract through the
orchestrator's routing (the path a grouper chain group takes), so both ways the
service is reached are covered. The registration contract is tested directly: an
engine without the registered applicator does not apply groupers, the
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
from udan.core_tools_loading.api_types import Group
from udan.operator.api_operator_engine import OperatorsEngineAPI
from udan.operator.plugins_operator import OperatorsEngine
from udan.operator.plugins_operator_grouper import GROUPER, GrouperApplier, GrouperPlugin, _apply_grouper
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


def test_applier_owns_the_grouper_kind():
    """The kind is the package's declaration: the engine's KINDS do not name it."""
    assert GrouperApplier.KINDS == (GROUPER,)
    assert GROUPER not in OperatorsEngine.KINDS
    assert GROUPER.query_keyword == "group"
    assert GROUPER.requires_item_parameter is True


def test_attach_adds_the_routing_handler_and_detach_takes_it_back_off(make_ctx):
    """The handler joins the routing in place at attach and leaves at detach."""
    ctx = make_ctx(plugins_demo, plugins_builtins, plugins_operators_attribute)
    routing = ctx.container.get(ChainRoutingAPI)
    applier = ctx.container.get(GrouperApplier)
    plugin = GrouperPlugin()

    ctx.container.call(plugin.detach)
    assert "grouper" not in routing

    ctx.container.call(plugin.attach)
    assert routing["grouper"] is applier


def test_after_detach_a_grouper_chain_finds_no_handler(make_ctx):
    """The routing is consulted live: a query whose chain has a grouper step gets the advice."""
    ctx = make_ctx(plugins_demo, plugins_builtins, plugins_operators_attribute, tests.plugins_test)
    qp = make_qp(ctx)
    plugin = GrouperPlugin()
    ctx.container.call(plugin.detach)

    _forest, _attrs, _render, out = qp.execute_query("insert_test_numbers_1_to_4, group_by_parity")

    assert out == (
        "A 'grouper' tool forms the chain, but no enabled package applies its kind: the "
        "package owning 'grouper' is not in udan_plugin_modules, so the query cannot run. "
        "Enable that package, or drop the 'grouper' step."
    )


def test_engine_without_the_registered_applicator_applies_no_groupers(make_ctx):
    """The engine knows no grouper: its dispatch learns the kind from the applier's registration."""
    ctx = make_ctx(plugins_demo, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, tests.plugins_test.__name__)
    engine = OperatorsEngine(registry=ctx.registry, types_registry=TypesRegistry())
    exec_ctx = _exec_context(ctx)
    attr_context = _attr_context(ctx, exec_ctx)
    forest = Forest(items=[opd("group_by_parity"), 1, 2], depths=[0, 0, 0])

    with pytest.raises(ValueError, match="Operator with type=grouper not found"):
        engine._apply_operators_in_forest(forest, exec_ctx, attr_context)

    engine.register_applicator(GROUPER, _apply_grouper)

    forest_fixed = engine._apply_operators_in_forest(forest, exec_ctx, attr_context)
    assert forest_fixed.items == [Group(key="odd"), 1, Group(key="even"), 2]
    assert forest_fixed.depths == [0, 1, 0, 1]


def test_grouper_wraps_the_nodes_into_group_nodes(make_ctx):
    ctx = make_ctx(plugins_demo, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, tests.plugins_test.__name__)

    forest = _apply(ctx, [opd("group_by_parity")], [1, 2, 3, 4], [0, 0, 0, 0])

    assert forest.items == [Group(key="odd"), 1, 3, Group(key="even"), 2, 4]
    assert forest.depths == [0, 1, 1, 0, 1, 1]


def test_applier_chain_step_returns_what_the_engine_step_returns(make_ctx):
    ctx = make_ctx(plugins_demo, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, tests.plugins_test.__name__)
    applier = ctx.container.get(GrouperApplier)
    stage = Forest.from_items([1, 2])
    exec_ctx = _exec_context(ctx)
    attr_context = _attr_context(ctx, exec_ctx)

    stepped = applier.apply_chain_step([opd("group_by_parity")], stage, attr_context, exec_ctx)
    engine_stepped = _engine(ctx).apply_chain_step([opd("group_by_parity")], stage, attr_context, exec_ctx)

    assert stepped.items == engine_stepped.items == [Group(key="odd"), 1, Group(key="even"), 2]
    assert stepped.depths == engine_stepped.depths == [0, 1, 0, 1]
    assert stepped.types == stage.types


def test_grouper_group_in_a_mixed_chain_keeps_the_written_order(make_ctx):
    """A grouper run is its own chain group now; the written order still decides what applies."""
    ctx = make_ctx(plugins_demo, plugins_builtins, plugins_operators_attribute, tests.plugins_test)
    qp = make_qp(ctx)

    _forest, _attrs, _render, out_grouper_first = qp.execute_query(
        "insert_test_numbers_1_to_4, group_by_parity, filter_keep_div div=2"
    )
    _forest, _attrs, _render, out_filter_first = qp.execute_query(
        "insert_test_numbers_1_to_4, filter_keep_div div=2, group_by_parity"
    )

    # grouper first: the filter tests the Group titles and rejects every group;
    # filter first: only the two survivors reach the grouper
    assert out_grouper_first == ""
    assert out_filter_first == "- group=even\n  - 2\n  - 4"


def _engine(ctx):
    """The operators engine, resolved from the container the fixture built."""
    return ctx.container.get(OperatorsEngineAPI)
