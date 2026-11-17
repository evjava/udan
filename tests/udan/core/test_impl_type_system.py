"""Tests for TypeSystem: combining forest types with the next chain tool."""

import pytest

from tests import plugins_test
from tests.conftest import make_qp
from udan.attributes import plugins_operators_attribute
from udan.core.api_exceptions import OverrideForestException, TypeCombinationError
from udan.core.api_forests import Node
from udan.core.api_item_types import accepted_item_types, declared_item_type, fits_chain, is_item_type_accepted
from udan.core.api_operators import OperatorDescriptor
from udan.core.api_type_system import ForestTypeDescriptor
from udan.core.config import UdanConfig
from udan.core.impl_type_system import DummyTypeSystem, TypeSystem
from udan.core_tools_loading.api_tool_kinds import ToolKindsRegistryAPI
from udan.core_tools_loading.api_types import TypeDescriptor
from udan.plugins_tools_core import plugins_help, plugins_system
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.plugins_tools_examples import plugins_builtins
from udan.renders import plugins_renders
from udan.renders.api_renders import RENDER, RenderDescriptor
from udan.renders.plugins_renders import RenderTypeSystem

MODULES = (
    plugins_demo,
    plugins_fruits,
    plugins_builtins,
    plugins_operators_attribute,
    plugins_help,
    plugins_system,
    plugins_test,
    plugins_renders,
)

NO_SOURCE_MESSAGE = "extender 'extend_multiply' creates a level, but the chain has no data source"
INSERTERS_HEADING = "inserters that create a level:"
INSERT_ITEMS_EXPLANATION = "insert items first - start the chain with a level-creating tool"
MISMATCH_MESSAGE = "extender 'extend_multiply' consumes 'int', the chain has [dict]"
FRUITS_MISMATCH_MESSAGE = MISMATCH_MESSAGE.replace("[dict]", "[dict/fruit]")
MID_CHAIN_MISMATCH_MESSAGE = "extender 'extend_menu_fruits' consumes 'str', the chain has [dict/fruit]"
MISMATCH_EXPLANATION = "use a tool that fits the chain - produce 'int' first, or pick one of the fitting extenders"
RANGE_DESCRIPTION = "Generate a sequence of numbers, similar to Python's range()."
RANGE_LAZY_DESCRIPTION = "Lazily yield integers, tracing every item the engine pulls."
SIMILAR_FRUITS_DESCRIPTION = "Extend each fruit with 2-3 similar fruits."
FRUITS_MISMATCH_LINES = [
    f"- {FRUITS_MISMATCH_MESSAGE}",
    f"- {MISMATCH_EXPLANATION}",
    "- inserters producing 'int':",
    f"  - demo.range :: {RANGE_DESCRIPTION}",
    f"  - demo.range_lazy :: {RANGE_LAZY_DESCRIPTION}",
    "- extenders that fit [dict/fruit]:",
    f"  - fruits.similar_fruits :: {SIMILAR_FRUITS_DESCRIPTION}",
]


@pytest.fixture
def inferer(make_ctx):
    ctx = make_ctx(*MODULES)
    # The `:` ranking is the renders package's decoration of the core type system,
    # so the suggest tests exercise the type system the container actually serves
    kinds = ctx.container.get(ToolKindsRegistryAPI)
    return RenderTypeSystem(TypeSystem(ctx.registry, kinds=kinds), ctx.registry)


def test_combine_empty_with_inserter_declares_output(inferer):
    combined = inferer.combine(ForestTypeDescriptor(), OperatorDescriptor.create("range"))

    assert combined == ForestTypeDescriptor.from_created_level("int")


def test_combine_empty_with_inserter_without_output_type_is_any_level(inferer):
    combined = inferer.combine(ForestTypeDescriptor(), OperatorDescriptor.create("insert_test_numbers"))

    assert combined == ForestTypeDescriptor.unknown()
    assert str(combined) == "[any]"


def test_combine_extender_appends_level(inferer):
    combined = inferer.combine(
        ForestTypeDescriptor.from_created_level("int"), OperatorDescriptor.create("extend_multiply")
    )

    assert combined == ForestTypeDescriptor(depths=[TypeDescriptor(name="int"), TypeDescriptor(name="int")])


def test_combine_grouper_prepends_group_level(inferer):
    combined = inferer.combine(
        ForestTypeDescriptor.from_created_level("int"), OperatorDescriptor.create("group_by_modulo")
    )

    assert str(combined) == "[group, int]"


def test_combine_filter_keeps_types(inferer):
    fruits = ForestTypeDescriptor.from_created_level("dict")

    assert inferer.combine(fruits, OperatorDescriptor.create("limit")) == fruits


def test_combine_undeclared_source_still_accepts_extender(inferer):
    """Fail-open: an undeclared inserter is a source with unknown item types."""
    unknown = inferer.combine(ForestTypeDescriptor(), OperatorDescriptor.create("insert_test_numbers"))
    combined = inferer.combine(unknown, OperatorDescriptor.create("extend_multiply"))

    assert str(combined) == "[any, int]"


def test_combine_extender_without_source_raises(inferer):
    with pytest.raises(TypeCombinationError) as exc_info:
        inferer.combine(ForestTypeDescriptor(), OperatorDescriptor.create("extend_multiply"))

    assert str(exc_info.value) == NO_SOURCE_MESSAGE
    assert exc_info.value.suggestions[INSERTERS_HEADING]["demo.range"] == RANGE_DESCRIPTION


def test_combine_grouper_without_source_raises(inferer):
    with pytest.raises(TypeCombinationError):
        inferer.combine(ForestTypeDescriptor(), OperatorDescriptor.create("group_by_modulo"))


def test_combine_error_without_source_is_override_forest_exception(inferer):
    """The error rides the override flow: its forest renders as guidance instead of a traceback."""
    with pytest.raises(OverrideForestException) as exc_info:
        inferer.combine(ForestTypeDescriptor(), OperatorDescriptor.create("group_by_modulo"))

    error = exc_info.value
    assert isinstance(error, TypeCombinationError)
    assert error.forest.depths == [0, 0, 0] + [1] * len(error.suggestions[INSERTERS_HEADING])
    assert error.forest.items[0] == str(error)
    assert error.forest.items[1] == INSERT_ITEMS_EXPLANATION
    assert error.forest.items[2] == INSERTERS_HEADING


def test_query_without_source_renders_inserter_suggestions(make_ctx):
    ctx = make_ctx(*MODULES)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("extend_multiply")

    lines = out.strip().split("\n")
    assert lines[0] == f"- {NO_SOURCE_MESSAGE}"
    assert lines[1] == f"- {INSERT_ITEMS_EXPLANATION}"
    assert lines[2] == f"- {INSERTERS_HEADING}"
    assert f"  - demo.range :: {RANGE_DESCRIPTION}" in lines
    assert forest.items[0] == NO_SOURCE_MESSAGE


def test_query_with_source_extender_unchanged(make_ctx):
    ctx = make_ctx(*MODULES)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 5, extend_multiply")

    assert forest.types.depths == [TypeDescriptor(name="int"), TypeDescriptor(name="int")]
    assert forest.depths == [0, 1, 0, 1, 0, 1, 0, 1, 0, 1]


# ============ require_source_for_renders ============

RENDER_NO_SOURCE_MESSAGE = "'fruit' requested, but the chain has no data source"


def test_require_source_for_renders_empty_chain_raises(inferer):
    with pytest.raises(TypeCombinationError) as exc_info:
        inferer.require_source_for_output(
            ForestTypeDescriptor(), [RenderDescriptor.create("fruit")], Node.leaf("fruit")
        )

    assert str(exc_info.value) == RENDER_NO_SOURCE_MESSAGE
    assert exc_info.value.suggestions[INSERTERS_HEADING]["demo.range"] == RANGE_DESCRIPTION


def test_require_source_for_renders_with_source_passes(inferer):
    renders = [RenderDescriptor.create("fruit")]

    inferer.require_source_for_output(ForestTypeDescriptor.from_created_level("dict"), renders, Node.leaf("fruit"))


def test_require_source_for_renders_without_renders_passes(inferer):
    inferer.require_source_for_output(ForestTypeDescriptor(), [], Node.leaf("fruit"))


def test_require_source_for_renders_introspection_chain_passes(inferer):
    """Introspection overrides the output flow: the empty fold says nothing about its render."""
    node = Node.leaf(OperatorDescriptor.create("help", [("tool_type", "render")]))

    inferer.require_source_for_output(ForestTypeDescriptor(), [RenderDescriptor.create("fruit")], node)


def test_query_render_without_source_renders_inserter_suggestions(make_ctx):
    ctx = make_ctx(*MODULES)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query(":fruit")

    lines = out.strip().split("\n")
    assert lines[0] == f"- {RENDER_NO_SOURCE_MESSAGE}"
    assert lines[1] == f"- {INSERT_ITEMS_EXPLANATION}"
    assert lines[2] == f"- {INSERTERS_HEADING}"
    assert f"  - demo.range :: {RANGE_DESCRIPTION}" in lines
    assert forest.items[0] == RENDER_NO_SOURCE_MESSAGE


def test_query_render_without_source_types_disabled_passes(make_ctx):
    """Types disabled rejects nothing: the render-only chain renders to empty output as before."""
    ctx = make_ctx(*MODULES, config=UdanConfig(udan_types_enabled=False))
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query(":fruit")

    assert out == ""
    assert forest.types.depths == []


def test_accepted_item_types_splits_union():
    assert accepted_item_types("str|Path") == frozenset({"str", "Path"})


def test_accepted_item_types_expands_numeric_family():
    assert accepted_item_types("int") == frozenset({"int", "float", "bool"})


def test_accepted_item_types_expands_dict_family():
    """Tool metadata entries are dicts at runtime: contracts on the base type fit both."""
    assert accepted_item_types("dict") == frozenset({"dict", "tool_metadata"})
    assert accepted_item_types("tool_metadata") == frozenset({"tool_metadata", "dict"})


def test_accepted_item_types_expands_group_family():
    """A tool group level is a group: aggregate renders declared on "group" fit it."""
    assert accepted_item_types("group") == frozenset({"group", "tool_group"})
    assert accepted_item_types("tool_group") == frozenset({"tool_group", "group"})


def test_is_item_type_accepted_unconstrained_declarations():
    assert is_item_type_accepted(None, ["dict"]) is True
    assert is_item_type_accepted("any", ["dict"]) is True


def test_is_item_type_accepted_unknown_level_switches_check_off():
    """Fail-open: an undeclared source produces items of unknown type."""
    assert is_item_type_accepted("int", ["any"]) is True


def test_is_item_type_accepted_any_level_fits():
    assert is_item_type_accepted("dict", ["group", "dict"]) is True


def test_is_item_type_accepted_union_and_family_membership():
    assert is_item_type_accepted("str|Path", ["Path"]) is True
    assert is_item_type_accepted("float", ["int"]) is True


def test_is_item_type_accepted_rejects_missing_type():
    assert is_item_type_accepted("int", ["dict"]) is False


def test_is_item_type_accepted_empty_levels_left_to_source_check():
    """Empty depths mean no data source: reported by the source check, not a type mismatch."""
    assert is_item_type_accepted("int", []) is True


# ============ fits_chain (completions) ============


@pytest.fixture
def registry(make_ctx):
    return make_ctx(*MODULES).registry


def test_fits_chain_inserter_only_fits_empty_chain(registry):
    """Inserters have no input contract: they can only open a chain, never follow a source."""
    ins_m = registry.get_metadata("range")

    assert fits_chain(ins_m, []) is True
    assert fits_chain(ins_m, ["int"]) is False


def test_fits_chain_declared_input_must_fit_levels(registry):
    """fruits.similar_fruits declares dict: it fits a dict chain, not an int chain."""
    ext_m = registry.get_metadata("similar_fruits")

    assert fits_chain(ext_m, ["dict"]) is True
    assert fits_chain(ext_m, ["int"]) is False


def test_fits_chain_universal_input_fits_every_chain(registry):
    """filter_field declares "any": the field tools fit dict and int chains alike."""
    filter_m = registry.get_metadata("filter_field")

    assert fits_chain(filter_m, ["dict"]) is True
    assert fits_chain(filter_m, ["int"]) is True


def test_fits_chain_undeclared_input_fits_everywhere(registry):
    op_m = registry.get_metadata("limit")

    assert fits_chain(op_m, ["int"]) is True
    assert fits_chain(op_m, ["dict"]) is True


def test_fits_chain_empty_levels_accept_everything(registry):
    assert fits_chain(registry.get_metadata("limit"), []) is True
    assert fits_chain(registry.get_metadata("filter_field"), []) is True


def test_declared_item_type_render_uses_meta_item_type_not_promoted_field(registry):
    """Renders are OperatorMetadata instances, but their contract is the meta item_type, not the promoted field."""
    render_m = registry.get_metadata("render_attr")

    assert declared_item_type(render_m) == "dict"
    assert render_m.item_type is None
    assert fits_chain(render_m, ["dict"]) is True
    assert fits_chain(render_m, ["int"]) is False


def test_combine_input_mismatch_raises(inferer):
    with pytest.raises(TypeCombinationError) as exc_info:
        inferer.combine(ForestTypeDescriptor.from_created_level("dict"), OperatorDescriptor.create("extend_multiply"))

    assert str(exc_info.value) == MISMATCH_MESSAGE
    suggestions = exc_info.value.suggestions
    assert suggestions["inserters producing 'int':"] == {
        "demo.range": RANGE_DESCRIPTION,
        "demo.range_lazy": RANGE_LAZY_DESCRIPTION,
    }
    assert suggestions["extenders that fit [dict]:"] == {"fruits.similar_fruits": SIMILAR_FRUITS_DESCRIPTION}


def test_combine_matching_extender_input_passes(inferer):
    combined = inferer.combine(
        ForestTypeDescriptor.from_created_level("str"), OperatorDescriptor.create("extend_menu_fruits")
    )

    assert str(combined) == "[str, dict]"


def test_combine_input_fits_any_level(inferer):
    """Item-consuming operators apply at every depth, so a non-deepest level satisfies the contract."""
    chain = inferer.combine(
        ForestTypeDescriptor.from_created_level("str"), OperatorDescriptor.create("extend_menu_fruits")
    )

    combined = inferer.combine(chain, OperatorDescriptor.create("extend_menu_fruits"))

    assert str(combined) == "[str, dict, dict]"


def test_combine_dict_input_fits_grouped_chain(inferer):
    grouped = inferer.combine(
        ForestTypeDescriptor.from_created_level("dict"), OperatorDescriptor.create("group_by_field")
    )

    combined = inferer.combine(grouped, OperatorDescriptor.create("sort_by_field"))

    assert str(combined) == "[group, dict]"


def test_query_input_mismatch_renders_fitting_suggestions(make_ctx):
    ctx = make_ctx(*MODULES)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("fruits, extend_multiply")

    assert out.strip().split("\n") == FRUITS_MISMATCH_LINES
    assert forest.items[0] == FRUITS_MISMATCH_MESSAGE


def test_combine_inserter_reset_then_mismatch(inferer):
    """A mid-chain inserter resets the descriptor: the extender then faces dict instead of str."""
    chain = inferer.combine(ForestTypeDescriptor.from_created_level("str"), OperatorDescriptor.create("fruits"))

    assert str(chain) == "[dict/fruit]"

    with pytest.raises(TypeCombinationError) as exc_info:
        inferer.combine(chain, OperatorDescriptor.create("extend_menu_fruits"))

    assert str(exc_info.value) == MID_CHAIN_MISMATCH_MESSAGE


def test_query_matching_chain_types_unchanged(make_ctx):
    ctx = make_ctx(*MODULES)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("menu, extend_menu_fruits")

    assert forest.types.depths == [TypeDescriptor(name="str"), TypeDescriptor(name="dict")]


# ============ suggest ============


def test_suggest_renders_ranked_semantic_first(inferer):
    """The `:` narrowing ranks: render_introspect leads although its item_type is tool_group."""
    # Built directly: help is a chain-overriding replacer, so folding it
    # yields no levels - the tool_group level comes from the render's
    # item_type contract, not from a chain item.
    ftd = ForestTypeDescriptor(depths=[TypeDescriptor(name="tool_group")])

    sections = inferer.suggest(ftd, tool_type=RENDER, endorsed=["introspect-item"])

    assert list(sections) == ["Semantic renders:", "Type-compatible renders:"]
    assert "render_introspect" in sections["Semantic renders:"]  # suggested by the alias
    # group renders fit the tool_group level via the family; dict renders do not
    assert "render_group_header" in sections["Type-compatible renders:"]
    assert "render_attr" not in sections["Type-compatible renders:"]


def test_suggest_renders_empty_semantic_section_omitted(inferer):
    """range endorses no render: only the type-compatible section is returned."""
    ftd = inferer.combine(ForestTypeDescriptor(), OperatorDescriptor.create("range"))

    sections = inferer.suggest(ftd, tool_type=RENDER)

    assert list(sections) == ["Type-compatible renders:"]
    assert "render_raw" in sections["Type-compatible renders:"]
    assert "render_attr" not in sections["Type-compatible renders:"]


def _flat_suggested(sections: dict[str, dict]) -> dict:
    """Flatten suggestion sections into one canonical-name -> metadata dict."""
    return {name: metadata for entries in sections.values() for name, metadata in entries.items()}


def test_suggest_filters_by_chain(inferer):
    """The `?` completions set on an int chain: no inserters, fitting contracts only."""
    ftd = inferer.combine(ForestTypeDescriptor(), OperatorDescriptor.create("range"))
    levels = [depth.name for depth in ftd.depths]

    suggested = _flat_suggested(inferer.suggest(ftd))

    assert "range" not in suggested  # inserters fit only a sourceless chain
    assert "extend_multiply" in suggested  # int contract fits the int level
    assert all(name == metadata.name for name, metadata in suggested.items())
    assert all(fits_chain(metadata, levels) for metadata in suggested.values())


def test_suggest_sections_are_by_kind(inferer):
    """Without the render narrowing each kind lands in its own section."""
    ftd = inferer.combine(ForestTypeDescriptor(), OperatorDescriptor.create("range"))

    sections = inferer.suggest(ftd)

    assert "Inserters:" not in sections
    assert "extend_multiply" in sections["Extenders:"]
    assert "is_even" in sections["Attributes:"]


def test_suggest_narrows_by_pattern(inferer):
    """A pattern narrows inside the type system: only matching names come back."""
    ftd = inferer.combine(ForestTypeDescriptor(), OperatorDescriptor.create("range"))

    suggested = _flat_suggested(inferer.suggest(ftd, pattern="multiply"))

    assert suggested.keys() == {"extend_multiply"}


def test_suggest_narrows_by_kind(inferer):
    """The `:?` narrowing: tool_type="render" lists renders only."""
    ftd = inferer.combine(ForestTypeDescriptor(), OperatorDescriptor.create("range"))

    suggested = _flat_suggested(inferer.suggest(ftd, tool_type="render"))

    assert suggested, "expected renders for the int chain"
    assert all(metadata.tool_type == "render" for metadata in suggested.values())


def test_suggest_filters_attributes_by_chain(inferer):
    """A dict-typed attribute is suggested on a dict chain, not on an int one."""
    fruits = inferer.combine(ForestTypeDescriptor(), OperatorDescriptor.create("fruits"))

    assert "fruit_cost" in _flat_suggested(inferer.suggest(fruits))
    ints = inferer.suggest(ForestTypeDescriptor.from_created_level("int"))
    assert "fruit_cost" not in _flat_suggested(ints)


def test_suggest_empty_chain_accepts_everything(inferer):
    """No data source yet: the empty level list accepts everything - inserters included."""
    suggested = _flat_suggested(inferer.suggest(ForestTypeDescriptor()))

    assert "range" in suggested
    assert "extend_multiply" in suggested


def test_dummy_suggest_lists_everything(make_ctx):
    """Types disabled: nothing is type-filtered, inserters included; the query's own
    narrowing (pattern) still applies."""
    ctx = make_ctx(*MODULES)
    dummy = DummyTypeSystem(ctx.registry)

    suggested = _flat_suggested(dummy.suggest(ForestTypeDescriptor.from_created_level("int")))

    assert "range" in suggested
    assert "extend_multiply" in suggested
    assert all(name == metadata.name for name, metadata in suggested.items())
    narrowed = _flat_suggested(dummy.suggest(ForestTypeDescriptor(), pattern="multiply"))
    assert narrowed.keys() == {"extend_multiply"}
