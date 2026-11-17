"""Tests for exec module (query execution)."""

import importlib

import pytest

import tests.plugins_test
import udan.attributes
import udan.plugins_tools_demo.plugins_demo
import udan.plugins_tools_demo.plugins_fruits
from tests.conftest import kinds_vocabulary, load_enabled_plugins, make_qp, register_tools_from_module
from udan.attributes import plugins_operators_attribute
from udan.core.api_item_types import fits_chain, is_item_type_accepted
from udan.core.api_operators import OperatorDescriptor
from udan.core.api_type_system import ForestTypeDescriptor
from udan.core.impl_type_system import TypeSystem
from udan.core_tools_loading.api_tool_kinds import ToolKindsRegistryAPI
from udan.core_tools_loading.api_types import Group
from udan.core_tools_loading.impl_tools_loader import ToolsLoader
from udan.core_tools_loading.impl_utils_tools_loader import _derive_item_param_type
from udan.plugins_tools_core import plugins_system
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.plugins_tools_examples import plugins_builtins
from udan.renders import plugins_renders


def test_exec_simple_query(make_ctx):
    """Test executing a simple query with custom operator."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)

    _, attrs, render_specs, out = qp.execute_query("range 3, :list")
    assert out == "[0, 1, 2]"


def test_exec_with_debug(make_ctx):
    """Test executing a query with debug mode."""

    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)
    register_tools_from_module(ctx, udan.attributes.plugins_operators_attribute.__name__)
    register_tools_from_module(ctx, tests.plugins_test.__name__)

    _, attrs, render_specs, out = qp.execute_query("debug, range 3")

    # Debug mode should include debug log in output
    # Extract number lines and compare exactly
    assert out.startswith("# ")
    lines = out.split("\n")
    number_lines = [line for line in lines if line.startswith("- ")]
    assert number_lines == ["- 0", "- 1", "- 2"]


def test_exec_with_filter(make_ctx):
    """Test executing a query with filter operator."""

    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, tests.plugins_test.__name__)

    _, attrs, render_specs, out = qp.execute_query("range 3, filter_keep_div 2, :list")

    assert out == "[0, 2]"


def test_exec_with_custom_context(make_ctx):
    """Test executing with a custom execution context."""

    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)

    _, attrs, render_specs, out = qp.execute_query("range 3, :list")

    assert out == "[0, 1, 2]"


def test_exec_invalid_query(make_ctx):
    """Test executing an invalid operator with arguments raises an error."""
    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, tests.plugins_test.__name__)

    # Query with arguments (clearly being used as an operator)
    _, attrs, render_specs, out = qp.execute_query("nonexistent_operator arg1")

    # Should return error output, not crash
    assert _ is None
    assert len(out) > 0
    # Should show error message about operator not found
    assert "not found" in out
    assert "nonexistent_operator" in out


def test_exec_invalid_query_leaf_item(make_ctx):
    """Test that a leaf item (no arguments) that can't be resolved raises an error."""
    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, tests.plugins_test.__name__)

    # Plain item with no arguments - should raise an error, not treat as data
    _, attrs, render_specs, out = qp.execute_query("nonexistent_operator")

    # Should return error output
    assert _ is None
    assert len(out) > 0
    # Should show error message about bare literal not allowed
    assert "Bare literal" in out or "not allowed" in out
    assert "nonexistent_operator" in out


def test_exec_quoted_literal(make_ctx):
    """Test that quoted literals work correctly."""
    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, tests.plugins_test.__name__)

    # Quoted string should work and be rendered as data
    _, attrs, render_specs, out = qp.execute_query('"abcdef"')

    # Should return output with the quoted string as-is
    assert _ is not None
    assert len(out) > 0
    # Quoted string is rendered as a data item
    assert out == "- abcdef"


def test_exec_with_attribute(make_ctx):
    """Test executing a query with attribute display."""

    ctx = make_ctx()
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)
    register_tools_from_module(ctx, udan.attributes.plugins_operators_attribute.__name__)
    register_tools_from_module(ctx, tests.plugins_test.__name__)

    # Query to show numbers with is_odd attribute
    # Need to increase max_out to get more interesting results
    ctx2 = ctx
    qp2 = make_qp(ctx2)
    register_tools_from_module(ctx2, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx2, udan.plugins_tools_demo.plugins_fruits.__name__)
    register_tools_from_module(ctx2, tests.plugins_test.__name__)
    register_tools_from_module(ctx2, plugins_renders.__name__)
    _, attrs, render_specs, out = qp2.execute_query("range 5, is_odd")

    # The term-list-item render shows attributes with :: separator
    # Items with attr_value are displayed as "- item :: value"
    expected_lines = [
        "- 0 :: False",
        "- 1 :: True",
        "- 2 :: False",
        "- 3 :: True",
        "- 4 :: False",
    ]
    expected = "\n".join(expected_lines)
    assert expected == out


def test_exec_group_by_attribute(make_ctx):
    """Test executing a query with group_by_attribute."""

    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)
    register_tools_from_module(ctx, udan.attributes.plugins_operators_attribute.__name__)
    register_tools_from_module(ctx, tests.plugins_test.__name__)
    register_tools_from_module(ctx, plugins_builtins.__name__)
    register_tools_from_module(ctx, plugins_renders.__name__)

    # Group numbers by is_even attribute
    forest, attrs, render_specs, out = qp.execute_query("range 5, group_by_attribute is_even")

    # Group items are rendered as headers with their children below
    # Output shows group structure with group key
    expected_lines = [
        "- True ::",
        "  - 0",
        "  - 2",
        "  - 4",
        "- False ::",
        "  - 1",
        "  - 3",
    ]
    expected = "\n".join(expected_lines)
    assert out == expected

    # Verify that Group items exist in the forest

    group_items = [item for item in forest.items if isinstance(item, Group)]
    assert len(group_items) == 2
    # Check group keys
    group_true = next((g for g in group_items if g.key is True), None)
    assert group_true is not None
    group_false = next((g for g in group_items if g.key is False), None)
    assert group_false is not None


def test_register_without_function_raises_error(make_ctx):
    """Test that registering a tool without a function raises ValueError."""
    ctx = make_ctx()

    # Load tools from builtins module
    loader = ToolsLoader(cache_dir=None, use_cache=False, kinds=kinds_vocabulary())
    metadata_fns = loader.load_from_module(plugins_builtins)

    # Try to register a tool without a function (pass None)
    metadata, _ = metadata_fns[0]  # Get first tool metadata

    with pytest.raises(ValueError, match="Function is required for tool"):
        ctx._register_metadata(metadata, fn=None)


def test_filter_boolean_shorthand(make_ctx):
    """Test that filter_by_attribute with boolean attribute works as shorthand for == True."""
    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)
    register_tools_from_module(ctx, udan.attributes.plugins_operators_attribute.__name__)
    register_tools_from_module(ctx, tests.plugins_test.__name__)
    register_tools_from_module(ctx, plugins_builtins.__name__)

    # Test shorthand: `filter_by_attribute is_even` should work like
    # `filter_by_attribute is_even == True`
    _, attrs, render_specs, out = qp.execute_query("range 5, filter_by_attribute is_even")

    # Should contain only even numbers (0, 2, 4)
    # Output is in tree format: "- 0"
    lines = out.strip().split("\n")
    assert len(lines) == 3, f"Expected 3 even numbers, got {len(lines)}: {lines}"
    # Extract numbers from tree format "- 0" -> 0
    numbers = [int(line.strip().split(" ", 1)[1]) for line in lines]
    assert all(num % 2 == 0 for num in numbers), "All numbers should be even"

    # Compare with explicit syntax: should get same result
    # Note: The explicit syntax uses "True" which gets converted to boolean
    # True
    _, attrs2, render_specs2, out2 = qp.execute_query("range 5, filter_by_attribute is_even == True")
    assert out == out2, "Shorthand and explicit syntax should produce same result"


def test_filter_boolean_shorthand_negation(make_ctx):
    """Test that filter_by_attribute with !bool-attr works as shorthand for == False."""
    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)
    register_tools_from_module(ctx, udan.attributes.plugins_operators_attribute.__name__)
    register_tools_from_module(ctx, tests.plugins_test.__name__)
    register_tools_from_module(ctx, plugins_builtins.__name__)

    # Test negation shorthand: `filter_by_attribute !is_even` should work like
    # `filter_by_attribute is_even == False`
    _, attrs, render_specs, out = qp.execute_query("range 5, filter_by_attribute !is_even")

    # Should contain only odd numbers (1, 3)
    # Output is in tree format: "- 1"
    lines = out.strip().split("\n")
    assert len(lines) == 2, f"Expected 2 odd numbers, got {len(lines)}: {lines}"
    # Extract numbers from tree format "- 1" -> 1
    numbers = [int(line.strip().split(" ", 1)[1]) for line in lines]
    assert all(num % 2 == 1 for num in numbers), "All numbers should be odd"

    # Compare with explicit syntax: should get same result
    _, attrs2, render_specs2, out2 = qp.execute_query("range 5, filter_by_attribute is_even == False")
    assert out == out2, "Negation shorthand and explicit syntax should produce same result"


def test_filter_boolean_shorthand_with_on_depth(make_ctx):
    """Test that the boolean shorthand still applies when framework flags are written beside the attribute.

    UDAN-440: `filter_by_attribute is_even --on-depth=N` used to skip the shorthand
    (the flag counted as a second argument) and compare the attribute against None,
    which rejected every targeted item.
    """
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)

    _, attrs, render_specs, out = qp.execute_query(
        "range 1 5, extend_multiply 2 3, filter_by_attribute is_even --on-depth=0, :list"
    )
    _, attrs2, render_specs2, out2 = qp.execute_query(
        "range 1 5, extend_multiply 2 3, filter_by_attribute is_even == True --on-depth=0, :list"
    )
    assert out == "[2, [4], [6], 4, [8], [12]]"
    assert out == out2, "Shorthand and explicit syntax should produce same result at --on-depth=0"

    _, attrs3, render_specs3, out3 = qp.execute_query(
        "range 1 5, extend_multiply 2 3, filter_by_attribute is_even --on-depth=1, :list"
    )
    _, attrs4, render_specs4, out4 = qp.execute_query(
        "range 1 5, extend_multiply 2 3, filter_by_attribute is_even == True --on-depth=1, :list"
    )
    assert out3 == "[1, [2], 2, [4], [6], 3, [6], 4, [8], [12]]"
    assert out3 == out4, "Shorthand and explicit syntax should produce same result at --on-depth=1"


def test_filter_boolean_shorthand_negation_with_on_depth(make_ctx):
    """Test that the !attr negation keeps the framework flags written beside it.

    The negation path used to rebuild the argument list from the attribute alone,
    so `filter_by_attribute !is_even --on-depth=1` lost the --on-depth flag.
    """
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)

    _, attrs, render_specs, out = qp.execute_query(
        "range 1 5, extend_multiply 2 3, filter_by_attribute !is_even --on-depth=1, :list"
    )
    _, attrs2, render_specs2, out2 = qp.execute_query(
        "range 1 5, extend_multiply 2 3, filter_by_attribute is_even == False --on-depth=1, :list"
    )
    assert out == "[1, [3], 2, 3, [9], 4]"
    assert out == out2, "Negation shorthand and explicit syntax should produce same result at --on-depth=1"


def test_empty_query_defaults_to_help(make_ctx):
    """Test that an empty query string defaults to help (?)."""
    # Create context and load tools like the old execute_query did
    # when ctx=None

    ctx = make_ctx()
    qp = make_qp(ctx)
    load_enabled_plugins(ctx)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)
    _, attrs, render_specs, out = qp.execute_query("")

    # Should show available tools (help output)
    # Check that output contains some expected tools
    assert "builtins ::" in out
    assert "render_attr" in out or "attr" in out
    assert "vars" in out
    assert "plugins" in out


def test_query_ending_with_comma_adds_help(make_ctx):
    """Test that a query ending with comma adds '?' to show help."""

    ctx = make_ctx()
    qp = make_qp(ctx)
    load_enabled_plugins(ctx)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)
    _, attrs, render_specs, out = qp.execute_query("fruits,")

    # Should show available tools (help output)
    # Check that output contains some expected tools
    assert "builtins ::" in out
    assert "demo ::" in out
    # Completions are chain-aware: dict contracts fit the fruit items, inserters do not
    assert "- fruits.similar_fruits ::" in out
    assert "- fruits.insert_fruits ::" not in out


def _listed_help_names(out: str) -> set[str]:
    """Display names of the entries in a help listing (two-space indented lines)."""
    return {line.strip()[2:].split(" ::")[0] for line in out.split("\n") if line.startswith("  - ")}


def test_question_suggestions_all_fit_the_chain(make_ctx):
    """Guard: every tool suggested after `range 5,` fits int items.

    The listed names must equal the type system's verdict over the whole registry:
    each tool's item contract (declared in meta or derived from the item
    parameter annotation) must accept int, and every fitting tool must be
    listed - neither a leak nor an over-filter.
    """
    ctx = make_ctx()
    qp = make_qp(ctx)
    load_enabled_plugins(ctx)

    _, _, _, out, _ = qp.execute_query_split_debug("range 5, ?")
    listed = _listed_help_names(out)

    inferer = TypeSystem(ctx.registry, kinds=ctx.container.get(ToolKindsRegistryAPI))
    ftd = inferer.combine(ForestTypeDescriptor(), OperatorDescriptor.create("range"))
    levels = [depth.name for depth in ftd.depths]
    expected = set()
    for name in ctx.registry.get_tools():
        metadata = ctx.registry.get_metadata(name)
        if metadata is None or name != metadata.name:
            continue
        if not fits_chain(metadata, levels):
            continue
        domain = metadata.meta.get("domain", "") or "builtins"
        expected.add(name if domain == "builtins" else f"{domain}.{name}")

    assert listed == expected


def test_derived_contracts_match_item_annotations(make_ctx):
    """Guard: a tool suggested on an int chain must have an int-compatible item annotation.

    Independent of the loader's own derivation: the raw annotation of the injected
    'item' parameter is read here, and whenever it names a concrete non-int type the
    metadata contract must exclude the tool from int chains - otherwise the
    annotation was ignored and the suggestion is a bug.
    """
    ctx = make_ctx()
    load_enabled_plugins(ctx)

    for name in ctx.registry.get_tools():
        metadata = ctx.registry.get_metadata(name)
        if metadata is None or name != metadata.name or not metadata.fn_path:
            continue
        module_name, fn_name = metadata.fn_path.rsplit(".", 1)
        fn = getattr(importlib.import_module(module_name), fn_name, None)
        annotation = _derive_item_param_type(fn) if fn else None
        if annotation is None or is_item_type_accepted(annotation, ["int"]):
            continue
        assert not fits_chain(metadata, ["int"]), (
            f"'{name}' takes items of type {annotation!r} but is still suggested after `range 5,`"
        )


def test_question_after_bare_number_fits_int(make_ctx):
    """Guard: completions after a bare number are filtered by its exact int type.

    The literal types its own level ("int"), so `3, ?` must list exactly the
    tools the type system accepts for an int chain - same as `range 5, ?` -
    with no inserters among them.
    """
    ctx = make_ctx()
    qp = make_qp(ctx)
    load_enabled_plugins(ctx)

    _, _, _, out, _ = qp.execute_query_split_debug("3, ?")
    listed = _listed_help_names(out)

    levels = ["int"]
    expected = set()
    for name in ctx.registry.get_tools():
        metadata = ctx.registry.get_metadata(name)
        if metadata is None or name != metadata.name:
            continue
        if not fits_chain(metadata, levels):
            continue
        domain = metadata.meta.get("domain", "") or "builtins"
        expected.add(name if domain == "builtins" else f"{domain}.{name}")

    assert listed == expected
    assert not any(name.endswith((".range", ".menu")) for name in listed)


def test_question_suggestions_logged(make_ctx):
    """The `?` completions announce themselves in the debug log: which chain, how many fit."""
    ctx = make_ctx()
    qp = make_qp(ctx)
    load_enabled_plugins(ctx)

    _, _, _, _, debug = qp.execute_query_split_debug("range 5, ?", debug=True)

    assert "# [DEBUG] suggesting tools for ['int']: " in debug


def test_render_suggestions_logged(make_ctx):
    """The bare `:` listing announces the completions verdict in the debug log."""
    ctx = make_ctx()
    qp = make_qp(ctx)
    load_enabled_plugins(ctx)

    _, _, _, out = qp.execute_query("range 5, :", debug=True)

    assert "# [DEBUG] suggesting tools for ['int']:" in out
    assert "sort_by_field" in out


def test_bare_literal_typo_suggests_close_name(make_ctx):
    """Test that a typo suggests the tools it is close to.

    The suggestion is a list inside the bare-literal error - never the docs of one
    "similar" name standing in for the answer. Renders are not consulted: bare names
    never search renders, so 'fruit' (render_fruit's alias, which collides with the
    fruit inserter in the registry) is offered only as ':fruit'.
    """
    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)
    register_tools_from_module(ctx, udan.attributes.plugins_operators_attribute.__name__)
    register_tools_from_module(ctx, tests.plugins_test.__name__)

    _, attrs, render_specs, out = qp.execute_query("fruitz")

    assert _ is None
    assert "Bare literal" in out
    assert "Did you mean" in out
    assert "fruits" in out
    # Should NOT dump all tools
    assert "Available tools" not in out
    suggestion_lines = [line for line in out.split("\n") if line.strip().startswith("-")]
    assert suggestion_lines == ["  - fruits.fruits"]


def test_bare_literal_short_word_lists_no_unrelated_help(make_ctx):
    """A short word near half the registry by edit distance must not get unrelated help.

    'so_' is edit distance 2 from names like 'log'; the answer to it is the
    bare-literal error, never the docs of whatever the distance happened to find.
    """
    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, plugins_builtins.__name__)
    register_tools_from_module(ctx, plugins_system.__name__)
    register_tools_from_module(ctx, plugins_renders.__name__)

    _, attrs, render_specs, out = qp.execute_query("range 5, so_")

    assert "Bare literal 'so_' is not allowed" in out
    # 'so_' is edit distance 2 from builtins' 'log' and 3 from 'log_'-style names:
    # none of them may surface as help for a bare literal.
    assert "log" not in out
    assert "insert_fruits" not in out


def test_bare_literal_unrelated_name_has_no_suggestions(make_ctx):
    """Test that a name unrelated to every tool gets no arbitrary suggestions."""
    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)
    register_tools_from_module(ctx, udan.attributes.plugins_operators_attribute.__name__)
    register_tools_from_module(ctx, tests.plugins_test.__name__)

    _, attrs, render_specs, out = qp.execute_query("nonexistent_operator")

    assert _ is None
    assert "Bare literal" in out
    assert "Did you mean" not in out
    assert "fruits" not in out


def test_bare_literal_short_string_no_suggestions(make_ctx):
    """Test that a very short/unusual bare literal may show no suggestions."""
    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, tests.plugins_test.__name__)

    _, attrs, render_specs, out = qp.execute_query("abcdef")

    assert _ is None
    assert "Bare literal" in out
    assert "abcdef" in out


def test_bare_number_is_data(make_ctx):
    """Test that a bare number is a literal int item."""
    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, tests.plugins_test.__name__)

    _, attrs, render_specs, out = qp.execute_query("555555")

    assert out == "- 555555"
    assert attrs == []


def test_bare_number_not_resolved_by_substring(make_ctx):
    """Test that a bare number inside a tool name stays data.

    "3" is a substring of the demo attribute "div_3"; the number must become an
    int item, not silently resolve to the div_3 attribute.
    """
    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, tests.plugins_test.__name__)

    _, attrs, render_specs, out = qp.execute_query("3")

    assert out == "- 3"
    assert attrs == []


def test_bare_float_is_data(make_ctx):
    """Test that a decimal bare number is a float item."""
    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, tests.plugins_test.__name__)

    _, attrs, render_specs, out = qp.execute_query("3.5")

    assert out == "- 3.5"
    assert attrs == []


def test_bare_number_extends_with_appended_level(make_ctx):
    """Test that a bare number is a data source for extenders.

    `3, extend_multiply 2` multiplies the literal int item: 3 extended by 6.
    """
    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, tests.plugins_test.__name__)

    _, attrs, render_specs, out = qp.execute_query("3, extend_multiply 2")

    assert out == "- 3\n  - 6"
    assert attrs == []


def test_two_bare_numbers_are_two_data_sources(make_ctx):
    """Test that two bare numbers in one chain are rejected as two data sources."""
    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, tests.plugins_test.__name__)

    _, attrs, render_specs, out = qp.execute_query("3, 4")

    assert _ is None
    assert "Invalid chain: multiple data sources" in out
    assert "'3', '4'" in out


def test_query_with_trailing_comma_and_space(make_ctx):
    """Test that query with trailing comma and space adds '?'."""

    ctx = make_ctx()
    qp = make_qp(ctx)
    load_enabled_plugins(ctx)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)
    _, attrs, render_specs, out = qp.execute_query("fruits, ")

    # Should show available tools (help output)
    assert "builtins ::" in out
    assert "demo ::" in out
