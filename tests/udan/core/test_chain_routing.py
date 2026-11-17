"""Unit tests for the chain routing: which service applies which kind inside a chain.

The routing is the kind-to-service table the orchestrator's walk dispatches through,
built from what the kind services declare (`KINDS`) and checked at construction. The
two `apply_chain_step` entries are here too: they are the services' side of that table.
"""

import pytest

import tests.plugins_test
from tests.conftest import register_tools_from_module
from udan.attributes import plugins_aggregates_attribute, plugins_operators_attribute
from udan.attributes.api_attribute_runtime import AttributeRuntimeAPI
from udan.attributes.impl_attribute_storage import AttributeStorage
from udan.attributes.plugins_attributes import AttributeRuntime
from udan.core.api_attributes import ATTRIBUTE, AttributeDescriptor, AttributeMetadata
from udan.core.api_chain_routing import ChainStepServiceAPI
from udan.core.api_forests import Forest
from udan.core.api_operators import OperatorDescriptor
from udan.core.api_query_processor import QueryProcessorAPI
from udan.core.impl_chain_routing import ChainRouting
from udan.core.impl_debug_logger import DebugLogger
from udan.core.impl_exec_context import ExecContext
from udan.core_tools_loading.api_tools import ToolKind
from udan.core_tools_loading.impl_tool_kinds import ToolKindsRegistry
from udan.core_tools_loading.impl_tools_registry import ToolsRegistry
from udan.operator.api_operator_engine import OperatorsEngineAPI
from udan.operator.plugins_operator_extender import ExtenderApplier
from udan.operator.plugins_operator_filter import FilterApplier
from udan.operator.plugins_operator_grouper import GrouperApplier
from udan.operator.plugins_operator_inserter import InserterApplier
from udan.operator.plugins_operator_mapper import MapperApplier
from udan.operator.plugins_operator_replacer import ReplacerApplier
from udan.operator.plugins_operator_sorter import SorterApplier
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.plugins_tools_examples import plugins_builtins
from udan.renders.api_renders import RenderDescriptor


@pytest.fixture
def ctx_routing(make_ctx):
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, tests.plugins_test.__name__)
    return ctx


@pytest.fixture
def qp(ctx_routing) -> QueryProcessorAPI:
    return ctx_routing.container.get(QueryProcessorAPI)


def _exec_context(ctx):
    return ExecContext(logger=DebugLogger(log_time=False), symbols_env=ctx.symbols_env)


def _attr_context(ctx, exec_ctx):
    return ctx.container.get(AttributeRuntimeAPI).create_attributes_context(
        attribute_storage=AttributeStorage(), requested_attributes=[], ctx=exec_ctx
    )


# --- the routing table ---


def test_routing_maps_operator_kinds_to_the_appliers(ctx_routing):
    """Every operator kind is a plugin kind: the routing hands it to its package."""
    routing = ctx_routing._chain_routing
    assert routing["inserter"] is ctx_routing.container.get(InserterApplier)
    assert routing["filter"] is ctx_routing.container.get(FilterApplier)
    assert routing["extender"] is ctx_routing.container.get(ExtenderApplier)
    assert routing["grouper"] is ctx_routing.container.get(GrouperApplier)
    assert routing["mapper"] is ctx_routing.container.get(MapperApplier)


def test_routing_maps_extender_to_the_applier(ctx_routing):
    routing = ctx_routing._chain_routing
    assert routing["extender"] is ctx_routing.container.get(ExtenderApplier)


def test_routing_maps_replacer_to_the_applier(ctx_routing):
    routing = ctx_routing._chain_routing
    assert routing["replacer"] is ctx_routing.container.get(ReplacerApplier)


def test_routing_maps_sorter_to_the_applier(ctx_routing):
    routing = ctx_routing._chain_routing
    assert routing["sorter"] is ctx_routing.container.get(SorterApplier)


def test_routing_maps_attribute_to_the_runtime(ctx_routing):
    routing = ctx_routing._chain_routing
    assert routing["attribute"] is ctx_routing.container.get(AttributeRuntimeAPI)


def test_render_is_not_in_the_routing(ctx_routing):
    routing = ctx_routing._chain_routing
    assert "render" not in routing


def test_handler_for_operator_descriptor(ctx_routing):
    routing = ctx_routing._chain_routing
    op_d = OperatorDescriptor.create("greps", {"patterns": ["banana"]})
    assert routing.handler_for(op_d) is ctx_routing.container.get(FilterApplier)


def test_handler_for_attribute_descriptor(ctx_routing):
    routing = ctx_routing._chain_routing
    assert routing.handler_for(AttributeDescriptor.create("double")) is ctx_routing.container.get(AttributeRuntimeAPI)


def test_handler_for_a_non_chain_kind_is_none(ctx_routing):
    routing = ctx_routing._chain_routing
    assert routing.handler_for(RenderDescriptor.create("list")) is None


def test_handler_for_an_unregistered_name_is_none(ctx_routing):
    routing = ctx_routing._chain_routing
    assert routing.handler_for(OperatorDescriptor.create("no_such_tool")) is None


def test_a_chain_forming_kind_without_a_handler_fails_the_validation():
    kinds = ToolKindsRegistry()
    kinds.register(ToolKind(name="orphan_kind", forms_chain=True))
    routing = ChainRouting([], kinds=kinds, registry=_registry_for_kinds(kinds))

    with pytest.raises(ValueError, match="orphan_kind"):
        routing.validate()


def test_the_completeness_check_passes_when_every_chain_forming_kind_is_handled():
    kinds = ToolKindsRegistry()
    kind = ToolKind(name="guarded_kind", forms_chain=True)
    kinds.register(kind)

    class Handler(ChainStepServiceAPI):
        KINDS = (kind,)

        def apply_chain_step(self, descriptors, stage, attr_context, ctx, item_cap=None) -> Forest:
            raise NotImplementedError

    routing = ChainRouting([Handler()], kinds=kinds, registry=_registry_for_kinds(kinds))

    routing.validate()


def test_with_handler_adds_a_handler_and_keeps_the_table_readable():
    kinds = ToolKindsRegistry()
    kind = ToolKind(name="late_kind", forms_chain=True)
    kinds.register(kind)

    class Handler(ChainStepServiceAPI):
        KINDS = (kind,)

        def apply_chain_step(self, descriptors, stage, attr_context, ctx, item_cap=None) -> Forest:
            raise NotImplementedError

    routing = ChainRouting([], kinds=kinds, registry=_registry_for_kinds(kinds))
    extended = routing.with_handler(Handler())

    assert "late_kind" not in routing
    assert "late_kind" in extended
    assert extended["late_kind"] is not None


def test_add_handler_extends_the_table_in_place():
    kinds = ToolKindsRegistry()
    kind = ToolKind(name="attached_kind", forms_chain=True)
    kinds.register(kind)

    class Handler(ChainStepServiceAPI):
        KINDS = (kind,)

        def apply_chain_step(self, descriptors, stage, attr_context, ctx, item_cap=None) -> Forest:
            raise NotImplementedError

    routing = ChainRouting([], kinds=kinds, registry=_registry_for_kinds(kinds))
    handler = Handler()

    routing.add_handler(handler)

    assert routing["attached_kind"] is handler


def test_remove_handler_takes_the_handler_back_off_the_table():
    kinds = ToolKindsRegistry()
    kind = ToolKind(name="attached_kind", forms_chain=True)
    kinds.register(kind)

    class Handler(ChainStepServiceAPI):
        KINDS = (kind,)

        def apply_chain_step(self, descriptors, stage, attr_context, ctx, item_cap=None) -> Forest:
            raise NotImplementedError

    routing = ChainRouting([], kinds=kinds, registry=_registry_for_kinds(kinds))
    handler = Handler()
    routing.add_handler(handler)

    routing.remove_handler(handler)

    assert "attached_kind" not in routing


def _registry_for_kinds(kinds):
    """A registry holding only the given vocabulary, for the construction-time checks."""
    return ToolsRegistry(DebugLogger(), loader=None, preferences={}, kinds=kinds)


def test_two_services_claiming_one_kind_fails_at_construction():
    kinds = ToolKindsRegistry()
    kind = ToolKind(name="shared_kind", forms_chain=True)
    kinds.register(kind)

    class First(ChainStepServiceAPI):
        KINDS = (kind,)

        def apply_chain_step(self, descriptors, stage, attr_context, ctx, item_cap=None) -> Forest:
            raise NotImplementedError

    class Second(ChainStepServiceAPI):
        KINDS = (kind,)

        def apply_chain_step(self, descriptors, stage, attr_context, ctx, item_cap=None) -> Forest:
            raise NotImplementedError

    with pytest.raises(ValueError, match="shared_kind"):
        ChainRouting([First(), Second()], kinds=kinds, registry=_registry_for_kinds(kinds))


def test_a_kind_service_without_the_chain_step_contract_fails_at_construction():
    kinds = ToolKindsRegistry()
    kind = ToolKind(name="unhandled_kind", forms_chain=True)
    kinds.register(kind)

    class NotAHandler:
        KINDS = (kind,)

    with pytest.raises(ValueError, match="cannot apply a chain step"):
        ChainRouting([NotAHandler()], kinds=kinds, registry=_registry_for_kinds(kinds))


# --- OperatorsEngine.apply_chain_step ---


def test_engine_chain_step_matches_whole_forest_application(ctx_routing):
    op_d = OperatorDescriptor.create("filter_keep_div", {"div": 2})
    stage = Forest.from_items([0, 1, 2, 3, 4])
    exec_ctx = _exec_context(ctx_routing)
    attr_context = _attr_context(ctx_routing, exec_ctx)

    stepped = ctx_routing.container.get(OperatorsEngineAPI).apply_chain_step([op_d], stage, attr_context, exec_ctx)
    whole = ctx_routing.container.get(OperatorsEngineAPI)._apply_operators_in_forest(
        Forest(items=[op_d, *stage.items], depths=[0] * 6, types=stage.types), exec_ctx, attr_context
    )

    assert stepped.items == whole.items == [0, 2, 4]
    assert stepped.depths == whole.depths == [0, 0, 0]


def test_engine_chain_step_keeps_the_stage_types(ctx_routing):
    op_d = OperatorDescriptor.create("filter_keep_div", {"div": 2})
    stage = Forest.from_items([0, 1, 2, 3, 4])
    exec_ctx = _exec_context(ctx_routing)
    attr_context = _attr_context(ctx_routing, exec_ctx)

    stepped = ctx_routing.container.get(OperatorsEngineAPI).apply_chain_step([op_d], stage, attr_context, exec_ctx)

    assert stepped.types == stage.types


# --- AttributeRuntime.apply_chain_step ---


def test_runtime_chain_step_computes_an_aggregate_over_the_stage(ctx_routing):
    register_tools_from_module(ctx_routing, plugins_aggregates_attribute.__name__)
    runtime = ctx_routing.container.get(AttributeRuntimeAPI)
    stage = Forest.from_items([1, 2, 3])
    exec_ctx = _exec_context(ctx_routing)
    attr_context = _attr_context(ctx_routing, exec_ctx)

    result = runtime.apply_chain_step([AttributeDescriptor.create("count")], stage, attr_context, exec_ctx)

    storage = runtime.attribute_storage
    assert result is stage
    assert storage.get_attr_value(AttributeDescriptor.create("count"), "forest") == 3


def test_runtime_chain_step_computes_a_per_item_attribute(ctx_routing):
    runtime = ctx_routing.container.get(AttributeRuntimeAPI)
    stage = Forest.from_items([2, 4])
    exec_ctx = _exec_context(ctx_routing)
    attr_context = _attr_context(ctx_routing, exec_ctx)
    at_d = AttributeDescriptor.create("double")

    result = runtime.apply_chain_step([at_d], stage, attr_context, exec_ctx)

    assert result is stage
    assert attr_context.get_attr_value_from_storage(at_d, 2) == 4
    assert attr_context.get_attr_value_from_storage(at_d, 4) == 8


def test_runtime_chain_step_skips_a_column_definition(ctx_routing):
    """A column-definition attribute has no value of its own: the walk skips it."""
    runtime = ctx_routing.container.get(AttributeRuntimeAPI)
    column_metadata = AttributeMetadata(
        name="col_def",
        description="column definition under test",
        tags=[],
        meta={"attribute_type": "column"},
        parameters={"properties": {}, "required": [], "type": "object"},
        output_schema={"properties": {}, "required": [], "type": "object"},
        fn_path="tests.plugins_test.col_def",
        attribute_type="column",
        tool_type=ATTRIBUTE,
    )
    ctx_routing._register_metadata(column_metadata, lambda **kwargs: "col_a")
    stage = Forest.from_items([1, 2])
    exec_ctx = _exec_context(ctx_routing)
    attr_context = _attr_context(ctx_routing, exec_ctx)

    computed: list[str] = []
    original = AttributeRuntime.calculate_attribute_descriptor_in_node

    def spy(self, context, at_d, node):
        computed.append(at_d.name)
        return original(self, context, at_d, node)

    AttributeRuntime.calculate_attribute_descriptor_in_node = spy
    try:
        result = runtime.apply_chain_step([AttributeDescriptor.create("col_def")], stage, attr_context, exec_ctx)
    finally:
        AttributeRuntime.calculate_attribute_descriptor_in_node = original

    assert computed == []
    assert result is stage


def test_runtime_chain_step_leaves_the_stage_unchanged(ctx_routing):
    runtime = ctx_routing.container.get(AttributeRuntimeAPI)
    stage = Forest.from_items([1, 2])
    exec_ctx = _exec_context(ctx_routing)
    attr_context = _attr_context(ctx_routing, exec_ctx)

    result = runtime.apply_chain_step([AttributeDescriptor.create("double")], stage, attr_context, exec_ctx)

    assert result is stage
    assert result.items == [1, 2]
