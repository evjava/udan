"""Tests for the tool kinds.

A kind is data: `ToolKind` carries the rules the framework applies to it, and every
kind is instantiated once, in the module that owns its domain. The vocabulary itself is
the `ToolKindsRegistry` component: built empty by the IoC container and filled by the
services that own kinds.
"""

import pytest

from tests import plugins_test_kinds
from udan.attributes import plugins_attributes
from udan.core.api_attributes import ATTRIBUTE
from udan.core.api_operators import OperatorMetadata
from udan.core.config import UdanConfig
from udan.core.impl_ioc import create_udan_container
from udan.core.impl_udan_context import UdanContext
from udan.core_tools_loading.api_tool_kinds import ToolKindsRegistryAPI, get_kind_services
from udan.core_tools_loading.api_tools import ToolKind, ToolMetadata
from udan.core_tools_loading.impl_tool_kinds import ToolKindsRegistry
from udan.core_tools_loading.impl_utils_tools_loader import (
    _convert_tool_to_metadata,
    _item_type_kwargs,
)
from udan.operator import (
    plugins_operator,
    plugins_operator_extender,
    plugins_operator_filter,
    plugins_operator_grouper,
    plugins_operator_inserter,
    plugins_operator_mapper,
    plugins_operator_replacer,
    plugins_operator_sorter,
)
from udan.operator.plugins_operator import OperatorsEngine
from udan.operator.plugins_operator_extender import EXTENDER
from udan.operator.plugins_operator_filter import FILTER
from udan.operator.plugins_operator_grouper import GROUPER
from udan.operator.plugins_operator_inserter import INSERTER
from udan.operator.plugins_operator_mapper import MAPPER
from udan.operator.plugins_operator_replacer import REPLACER
from udan.operator.plugins_operator_sorter import SORTER
from udan.renders import impl_render_engine
from udan.renders.api_renders import RENDER
from udan.renders.impl_render_engine import RenderEngineImpl as RenderEngine

# The kinds whose objects core publishes, one instantiation each, next to their domain:
# core declares no operator kind any more, so these are the attribute and the render;
# every operator kind is instantiated beside the plugin package that owns it.
ALL_CORE_KINDS: tuple[ToolKind, ...] = (ATTRIBUTE, RENDER)
# The operator kinds, all of them plugin kinds now, in query-keyword order where one exists.
OPERATOR_KINDS: tuple[ToolKind, ...] = (INSERTER, FILTER, EXTENDER, GROUPER, SORTER, MAPPER, REPLACER)


def _tool(name: str, meta: dict) -> dict:
    """Minimal tool schema shaped like what the annotated decorator harvests."""
    return {
        "name": name,
        "description": f"{name} description.",
        "tags": [],
        "meta": meta,
        "parameters": {"properties": {}, "required": [], "type": "object"},
        "output_schema": {},
    }


def _noop(item) -> list:
    return [item]


def test_every_kind_is_instantiated_in_its_own_module():
    assert ATTRIBUTE.name == "attribute"
    assert RENDER.name == "render"
    # an operator kind is instantiated beside the plugin that owns it, not in core:
    # core's api_operators publishes no kind object any more
    assert INSERTER.name == "inserter"
    assert INSERTER.query_keyword == "insert"
    assert FILTER.name == "filter"
    assert FILTER.query_keyword == "filter"
    assert EXTENDER.name == "extender"
    assert EXTENDER.query_keyword == "extend"
    assert GROUPER.name == "grouper"
    assert GROUPER.query_keyword == "group"
    assert SORTER.name == "sorter"
    assert SORTER.query_keyword == "sort"
    assert MAPPER.name == "mapper"
    assert MAPPER.query_keyword is None
    assert REPLACER.name == "replacer"
    assert REPLACER.query_keyword == "replace"
    for kind in OPERATOR_KINDS:
        assert kind not in OperatorsEngine.KINDS


def test_kind_equality_and_hash_are_by_name():
    """A kind is its name: two instances of one kind compare equal and hash alike."""
    assert ATTRIBUTE == ToolKind(name="attribute")
    assert ATTRIBUTE == "attribute"
    assert ATTRIBUTE != INSERTER
    assert ATTRIBUTE != "inserter"
    assert hash(ATTRIBUTE) == hash(ToolKind(name="attribute"))
    assert str(ATTRIBUTE) == "attribute"


def test_component_starts_empty():
    kinds = ToolKindsRegistry()

    assert len(kinds) == 0
    assert "inserter" not in kinds
    assert list(kinds) == []


def test_built_in_kind_rules():
    """The rules the framework applies per kind ride on the kind, not on branches."""
    assert FILTER.requires_item_parameter is True
    assert GROUPER.requires_item_parameter is True
    assert INSERTER.requires_item_parameter is False
    assert INSERTER.derives_item_type is False
    assert RENDER.filter_group == "render"
    assert ATTRIBUTE.filter_group == "attribute"
    assert FILTER.filter_group == "operator"
    assert INSERTER.query_keyword == "insert"
    assert MAPPER.query_keyword is None
    assert EXTENDER.required_item_type_keys == ("output_type",)
    # the declarations the framework reads instead of comparing kinds
    assert MAPPER.rewrites_items is True
    assert EXTENDER.rewrites_items is False
    assert REPLACER.injected_args == ("items", "nodes")
    assert REPLACER.rewrites_items is True
    assert REPLACER.declares_output is True
    assert FILTER.injected_args == ()


def test_register_extends_vocabulary():
    kinds = ToolKindsRegistry()
    kind = ToolKind(name="test_ranker")

    stored = kinds.register(kind)

    assert stored is kind
    assert "test_ranker" in kinds
    assert kinds["test_ranker"] is kind


def test_register_is_additive_for_known_kind():
    """Re-registering a known kind fills the fields the first left open and keeps the rest."""
    kinds = ToolKindsRegistry()
    stored = kinds.register(ToolKind(name="test_pinner"))
    merged = kinds.register(ToolKind(name="test_pinner"))

    assert merged is stored
    assert len(kinds) == 1

    filled = kinds.register(ToolKind(name="test_pinner", query_keyword="pin"))

    assert filled.item_type_keys == ()
    assert filled.query_keyword == "pin"
    assert kinds["test_pinner"] is filled


def test_register_conflict_raises():
    """A registration contradicting a field already set is an error, not a silent overwrite."""
    kinds = ToolKindsRegistry()
    kinds.register(ToolKind(name="test_doubler", query_keyword="double"))

    with pytest.raises(ValueError, match="Conflicting ToolKind"):
        kinds.register(ToolKind(name="test_doubler", query_keyword="double_again"))


def test_unknown_kind_lookup_raises():
    kinds = ToolKindsRegistry()

    with pytest.raises(KeyError, match="Unknown tool kind"):
        kinds["no-such-kind"]


def test_container_fills_the_vocabulary_from_its_services():
    """The component is a container service: the engines declare the kinds they own."""
    container = create_udan_container(UdanConfig())
    container.get(UdanContext)
    kinds = container.get(ToolKindsRegistryAPI)

    assert isinstance(kinds, ToolKindsRegistryAPI)
    for kind in ALL_CORE_KINDS:
        assert kind.name in kinds, kind.name
    # the vocabulary holds the core kinds plus the operator kinds the default config
    # enables: every operator kind is instantiated beside its package and reaches the
    # vocabulary through its kind service's KINDS - a container built without a
    # kind's package sees none of that kind
    assert set(kinds) - {kind.name for kind in ALL_CORE_KINDS} == {kind.name for kind in OPERATOR_KINDS}
    # the rules survive the registration: the kinds the engines declared are the ones
    # every other component reads
    assert kinds.get("filter").requires_item_parameter is True
    assert kinds.get("extender").required_item_type_keys == ("output_type",)
    assert kinds.get("replacer").query_keyword == "replace"
    assert kinds.get("sorter").query_keyword == "sort"


def test_vocabulary_is_filled_when_the_component_is_built():
    """The vocabulary is built filled: which services happen to be constructed first must not matter.

    A kind service declares its kinds and the container registers them when it builds
    the vocabulary - registration is not a side effect of some other service's
    construction, so reading the vocabulary alone yields every core kind, with its rules.
    """
    container = create_udan_container(UdanConfig())
    kinds = container.get(ToolKindsRegistryAPI)

    for kind in ALL_CORE_KINDS:
        assert kind.name in kinds, kind.name
    assert kinds.get("filter").requires_item_parameter is True


def test_core_kind_services_are_marked_and_declare_their_kinds():
    """The services that own the core kinds are marked and declare them, like plugins do."""
    for module, kind_service in (
        (plugins_operator, OperatorsEngine),
        (impl_render_engine, RenderEngine),
    ):
        assert get_kind_services(module) == [kind_service]
        for kind in kind_service.KINDS:
            assert kind in ALL_CORE_KINDS
    # the plugin side of the same contract: every operator kind's package owns its kind,
    # the test package's own kind service declares its own
    assert get_kind_services(plugins_operator_inserter) == [plugins_operator_inserter.InserterApplier]
    assert get_kind_services(plugins_operator_filter) == [plugins_operator_filter.FilterApplier]
    assert get_kind_services(plugins_operator_extender) == [plugins_operator_extender.ExtenderApplier]
    assert get_kind_services(plugins_operator_grouper) == [plugins_operator_grouper.GrouperApplier]
    assert get_kind_services(plugins_operator_sorter) == [plugins_operator_sorter.SorterApplier]
    assert get_kind_services(plugins_operator_mapper) == [plugins_operator_mapper.MapperApplier]
    assert get_kind_services(plugins_operator_replacer) == [plugins_operator_replacer.ReplacerApplier]
    assert get_kind_services(plugins_attributes) == [plugins_attributes.AttributeRuntime]
    assert get_kind_services(plugins_test_kinds) == [plugins_test_kinds.CheckKindService]


def test_services_registering_the_same_kinds_twice_is_idempotent(make_ctx):
    """Two containers register the same kinds; the vocabulary does not complain."""
    kinds = ToolKindsRegistry()
    for kind in ALL_CORE_KINDS:
        kinds.register(kind)
    for kind in ALL_CORE_KINDS:
        kinds.register(kind)

    assert len(kinds) == len(ALL_CORE_KINDS)


def test_registry_kind_gate_uses_the_vocabulary(make_ctx):
    """The registry validates `kind` arguments against the vocabulary component."""
    ctx = make_ctx()

    with pytest.raises(ValueError, match="Unknown tool kind: 'no-such-kind'"):
        ctx.registry.get_tools(kind="no-such-kind")
    assert ctx.registry.get_tools(kind="render") is not None


def test_matches_type_filter_uses_the_kind_group():
    kinds = ToolKindsRegistry()
    kinds.register(ATTRIBUTE)
    metadata = _convert_tool_to_metadata(_noop, _tool("test_attr", {}), None, kinds)

    assert metadata.matches_type_filter("attribute") is True
    assert metadata.matches_type_filter("operator") is False
    assert metadata.matches_type_filter("render") is False
    assert metadata.matches_type_filter("") is True
    assert metadata.matches_type_filter("attribute") is (metadata.tool_type.filter_group == "attribute")


def test_item_type_keys_come_from_the_kind():
    kinds = ToolKindsRegistry()
    typed = kinds.register(ToolKind(name="test_typed", item_type_keys=("item_type", "output_type")))
    untyped = kinds.register(ToolKind(name="test_untyped"))

    assert _item_type_kwargs(typed, "test_typed_thing", {"item_type": "str", "output_type": "int"}) == {
        "item_type": "str",
        "output_type": "int",
    }
    assert _item_type_kwargs(untyped, "test_untyped_thing", {"item_type": "str"}) == {}
    with pytest.raises(ValueError, match="declares unsupported item type/semantic key"):
        _item_type_kwargs(typed, "test_typed_thing", {"output_semantic": "count"})


def test_query_keyword_infers_the_kind():
    """A name prefix resolves to the kind whose query keyword it is."""
    kinds = ToolKindsRegistry()
    checker = kinds.register(ToolKind(name="test_checker", query_keyword="probe"))

    metadata = _convert_tool_to_metadata(_noop, _tool("probe_thing", {}), None, kinds)

    assert metadata.tool_type == checker


def test_unknown_kind_builds_the_base_metadata():
    """An tool_type outside the vocabulary becomes a bare kind: no rules, base metadata.

    A bare kind carries nothing - no item contract keys, no metadata class - so the
    loader builds the base class. The kinds that need the operator marker declare
    OperatorMetadata; an unknown name cannot.
    """
    metadata = _convert_tool_to_metadata(_noop, _tool("test_odd", {"tool_type": "test_odd"}), None)

    assert type(metadata) is ToolMetadata
    assert metadata.tool_type == "test_odd"


def test_metadata_holds_a_kind():
    """tool_type is a ToolKind, and a kind name in its place is coerced.

    The default kind of a vocabulary is the one its package declares: with the
    attribute kind registered, an undeclared tool resolves to it.
    """
    kinds = ToolKindsRegistry()
    kinds.register(ATTRIBUTE)
    metadata = _convert_tool_to_metadata(_noop, _tool("test_attr", {}), None, kinds)

    assert isinstance(metadata.tool_type, ToolKind)
    assert metadata.tool_type == ATTRIBUTE

    by_name = ToolMetadata(
        name="by_name",
        parameters={"properties": {}, "required": [], "type": "object"},
        output_schema={},
        fn_path="tests.test_tool_kinds.by_name",
        tool_type="render",
    )
    assert isinstance(by_name.tool_type, ToolKind)
    assert by_name.tool_type == RENDER


def test_load_plugins_registers_module_kind_services():
    """A plugin defines its kinds in a ToolKindService subclass.

    The kind is the service's own declaration, so everything it sets is proof that the
    service was harvested: nothing else in the suite declares this kind.
    """
    container = create_udan_container(UdanConfig())
    ctx = container.get(UdanContext)
    ctx.container = container
    kinds = container.get(ToolKindsRegistryAPI)

    ctx.registry.load_plugins(plugins_test_kinds, injector=ctx.injector)

    stored = kinds["test_validator"]
    assert stored == plugins_test_kinds.CheckKindService.KINDS[0]
    assert stored.query_keyword == "check"
    assert stored.item_type_keys == ("item_type", "output_type")

    # The module's tool is registered under the service-declared kind, with the
    # item contract the kind allows promoted onto the metadata.
    names = ctx.registry.get_tools(kind="test_validator")
    assert len(names) == 1
    metadata = ctx.registry.get_metadata(names[0])
    assert isinstance(metadata, OperatorMetadata)
    assert metadata.tool_type.name == "test_validator"
    assert metadata.item_type == "str"
    assert metadata.output_type == "str"


def test_registry_accepts_a_kind_or_its_name(make_ctx):
    ctx = make_ctx()
    ctx.registry.load_plugins(plugins_test_kinds, injector=ctx.injector)

    by_kind = ctx.registry.get_tools(kind=plugins_test_kinds.CheckKindService.KINDS[0])
    by_name = ctx.registry.get_tools(kind="test_validator")

    assert by_kind == by_name
    assert by_name
