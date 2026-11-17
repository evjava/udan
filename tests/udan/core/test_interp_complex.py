"""Tests for query interpretation.

This module contains complex tests that require attributes and operators.
Test-specific tools are now defined in plugins_test_interp_complex.py
for better modularity.
"""

import sys
from functools import partial

import pytest

from tests import plugins_test_interp_complex
from tests.conftest import kinds_vocabulary, make_qp
from tests.test_helpers import parse_and_interpret
from udan.attributes import plugins_operators_attribute
from udan.core.api_attributes import AttributeDescriptor
from udan.core.api_exceptions import ExceptionWithAdvice
from udan.core.api_forests import Node
from udan.core.api_operators import OperatorDescriptor, OperatorMetadata
from udan.core.api_query_processor import QueryProcessorAPI
from udan.core.config import UdanConfig
from udan.core.impl_ioc import create_udan_container
from udan.core.impl_udan_context import UdanContext
from udan.core_tools_loading.api_annotated import annotated
from udan.core_tools_loading.impl_tools_loader import ToolsLoader, _load_tool_metadata
from udan.parsing.api_query_parser import QueryParserAPI
from udan.parsing.impl_utils_parsing import parse_tree
from udan.plugins_history import plugins_history
from udan.plugins_tools_core import plugins_help, plugins_system
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.plugins_tools_examples import plugins_builtins
from udan.renders import plugins_renders


def assert_operator(result: Node, identity: str, args=(), tool_args=()):
    """Assert result is an OperatorDescriptor with expected values."""
    assert result is not None
    assert isinstance(result.item, OperatorDescriptor)
    assert result.item.name == identity
    # args can be tuple or list, convert for comparison
    assert list(result.item.args) == list(args)
    assert result.item.tool_args == tool_args


def assert_attribute(result: Node, identity: str):
    """Assert result is an AttributeDescriptor with expected identity."""
    assert result is not None
    assert isinstance(result.item, AttributeDescriptor)
    assert str(result.item.name) == identity


def test_queries_interpretation_help(make_ctx):
    """Test that the listing operator returns a help operator descriptor.

    The `?` sugar lowers to `help` in the query parser, so the processor
    only ever interprets the written form.
    """
    # Load builtins to get help operator
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_test_interp_complex,
    )
    loader = ToolsLoader(cache_dir=None, use_cache=False, kinds=kinds_vocabulary())
    bpmfs = loader.load_from_module(plugins_builtins)
    ctx._register_many_metadatas(bpmfs)

    result = parse_and_interpret(ctx, "help")

    assert result is not None
    assert isinstance(result.item, OperatorDescriptor)
    # ? returns help operator (which is an inserter that returns operator descriptors)
    assert result.item.name == "help"


def test_queries_interpretation_help_renders(make_ctx):
    """Test that the render-filtered listing returns a help descriptor with tool_type=render.

    The `:?` sugar lowers to `help --tool_type=render` in the parser.
    """
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_test_interp_complex,
    )
    result = parse_and_interpret(ctx, "help --tool_type=render")

    assert result is not None
    assert isinstance(result.item, OperatorDescriptor)
    assert result.item.name == "help"
    # Check that it has the tool_type="render" filter
    op_d = result.item
    # The args should contain tool_type="render"
    args_dict = dict(op_d.args)
    assert args_dict.get("tool_type") == "render"


def test_queries_interpretation_help_renders_pattern(make_ctx):
    """Test that the render-filtered listing narrows by the pattern.

    The `:?pattern` sugar lowers to `help --tool_type=render --pattern=pattern` in the parser.
    """
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_test_interp_complex,
    )
    result = parse_and_interpret(ctx, "help --tool_type=render --pattern=entries")

    assert result is not None
    assert isinstance(result.item, OperatorDescriptor)
    assert result.item.name == "help"
    args_dict = dict(result.item.args)
    assert args_dict.get("tool_type") == "render"
    assert args_dict.get("pattern") == "entries"


def test_queries_interpretation_tool_lookup(make_ctx):
    """Test that tool lookup works."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_test_interp_complex,
    )
    result = parse_and_interpret(ctx, "filter_even")

    assert_operator(result, "filter_even")


def test_queries_interpretation_tool_with_args(make_ctx):
    """Test that tool with arguments gets bound correctly."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_test_interp_complex,
    )
    result = parse_and_interpret(ctx, "operator_with_alias custom_pattern")

    assert_operator(result, "operator_with_alias", args=(("pattern", "custom_pattern"),))


def test_queries_interpretation_alias_resolution(make_ctx):
    """Test that operator aliases work."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_test_interp_complex,
    )
    result = parse_and_interpret(ctx, "operator_alias")

    # Default value for 'pattern' is now filled in
    assert_operator(result, "operator_alias", args=(("pattern", "test"),))


def test_queries_interpretation_attribute_descriptor(make_ctx):
    """Test that attribute descriptors are handled correctly."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_test_interp_complex,
    )
    result = parse_and_interpret(ctx, "attribute_square")

    assert_attribute(result, "attribute_square")


def test_queries_interpretation_multiple_matches(make_ctx):
    """Test that multiple matching tools are answered with the listing."""
    # 'e' matches 'filter_even', 'extender_double', 'replacer_list', etc.
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_test_interp_complex,
    )
    qp = make_qp(ctx)
    _, _, _, out = qp.execute_query("e")

    assert "filter_even" in out
    assert "extender_double" in out


def test_queries_interpretation_nested_children_assertion(make_ctx):
    """Test that nested children are supported: an unknown name inside them errors without a traceback."""
    # nested child: (nested value) creates a nested structure; 'nested' is not a
    # tool, so it answers with the not-found message instead of crashing
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_test_interp_complex,
    )
    qp = make_qp(ctx)
    _, _, _, out = qp.execute_query("operator_with_alias (nested value)")

    assert out == "Tool 'nested' not found.\nRun '?' to list the available tools."


def test_queries_interpretation_at_d_argument(make_ctx):
    """Test handling of 'at_d' arguments (attribute descriptors)."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_test_interp_complex,
    )
    result = parse_and_interpret(ctx, "operator_with_at_d attribute_square")

    assert result is not None
    assert isinstance(result.item, OperatorDescriptor)
    assert result.item.name == "operator_with_at_d"
    assert len(result.item.args) == 1
    arg_name, arg_value = result.item.args[0]
    assert arg_name == "at_d"
    assert isinstance(arg_value, AttributeDescriptor)
    assert str(arg_value.name) == "attribute_square"


def test_queries_interpretation_resolve_query_integration(make_ctx):
    """Test _walk as part of resolve_query integration."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_test_interp_complex,
    )
    query_node = parse_tree("debug, filter_even")

    # Call resolve_query which uses _walk internally
    forest, at_ds, render = ctx.container.get(QueryProcessorAPI).resolve_query(query_node, ctx.create_exec_context())

    # Check results
    assert len(at_ds) == 0  # No attribute descriptors
    assert len(render) == 0  # No render tools

    # Forest should contain the operator descriptor
    assert len(forest.items) == 1
    assert isinstance(forest.items[0], OperatorDescriptor)
    assert forest.items[0].name == "filter_even"


def test_queries_interpretation_tool_types(make_ctx):
    """Test that different operator types are recognized correctly."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_test_interp_complex,
    )
    for op_name in ["filter_even", "extender_double", "replacer_list", "operator_with_alias"]:
        result = parse_and_interpret(ctx, op_name)
        assert isinstance(result.item, OperatorDescriptor)


def test_queries_interpretation_inserter_as_attribute(make_ctx):
    """Test that inserter (without tool_type) is treated as attribute."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_test_interp_complex,
    )
    result = parse_and_interpret(ctx, "inserter_numbers")

    assert_attribute(result, "inserter_numbers")


def test_queries_interpretation_extract_metadata():
    """Test extracting metadata from annotated functions."""

    # Note: This function loads tools without a context for metadata inspection
    # The tools are not registered, just inspected

    config = UdanConfig()
    container = create_udan_container(config)
    _ctx = container.get(UdanContext)
    _ctx.container = container
    loader = ToolsLoader(cache_dir=None, use_cache=False, kinds=kinds_vocabulary())
    metadata_fns = loader.load_from_module(plugins_test_interp_complex)

    # Find get_numbers tool
    get_numbers_sp = [metadata_fn for metadata_fn in metadata_fns if metadata_fn[0].name == "get_numbers"]
    assert len(get_numbers_sp) == 1
    op_m_actual, op_m_f = get_numbers_sp[0]
    assert op_m_f(n=2, lim=2) == [0, 2]
    op_m_expected = OperatorMetadata(
        name="get_numbers",
        fn_path="tests.plugins_test_interp_complex.get_numbers",
        description="Test operator with parameters and tags.",
        tags=["numbers"],
        meta={"tool_type": "inserter", "domain": "test_interp_complex"},
        parameters={
            "properties": {"n": {"type": "integer"}, "lim": {"default": 3, "type": "integer"}},
            "required": ["n"],
            "type": "object",
        },
        output_schema={},
        tool_type="inserter",
        is_nested=False,
    )
    assert op_m_actual == op_m_expected


def test_queries_interpretation_resolving_tools(make_ctx):
    """Test resolving tools with arguments via walk."""
    # get_numbers requires 'n' argument
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_test_interp_complex,
    )
    with pytest.raises(ExceptionWithAdvice):
        parse_and_interpret(ctx, "get_numbers")  # Missing required 'n' arg

    # get_numbers with argument should work
    # Now with type conversion (string "5" -> int 5) and defaults (lim=3)
    result = parse_and_interpret(ctx, "get_numbers 5")
    assert_operator(result, "get_numbers", args=(("n", 5), ("lim", 3)))


def test_queries_interpretation_resolving_implicit_tool(make_ctx):
    """Test that implicit tools are registered correctly."""
    # get_numbers and insert_numbers_extra should be registered
    # Note: get_numbers is found, but insert_numbers_extra has a different name
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_test_interp_complex,
    )
    tools = ctx.registry.get_tools()
    assert "get_numbers" in tools
    assert "insert_numbers_extra" in tools


# Tests for bind_with_schema_ext
class MockMetadata:
    """Mock metadata object for testing."""

    def __init__(self, parameters, name="mock_tool"):
        self.parameters = parameters
        self.name = name
        self.meta = {}
        self.tool_type = "inserter"


def bind_with_schema_ext(
    ctx: UdanContext, metadata, args: list[Node]
) -> tuple[dict, int | None, int | None, tuple[int, ...] | None]:
    """Bind arg nodes to metadata through the descriptor factory, as the engine does."""
    exec_ctx = ctx.create_exec_context()
    interpret_fn = partial(ctx.container.get(QueryProcessorAPI)._interpret_query, ctx=exec_ctx)
    return ctx.container.get(QueryProcessorAPI)._descriptor_factory._bind_with_schema_ext(
        metadata, args, [], interpret_fn, exec_ctx
    )


def test_queries_interpretation_bind_ext_type_conversion(make_ctx):
    """Test that bind_with_schema_ext converts string args to proper types."""
    metadata = MockMetadata(
        {
            "properties": {
                "n": {"type": "integer"},
                "lim": {"type": "integer", "default": 3},
            },
            "required": ["n"],
        }
    )

    ctx = make_ctx()
    args = [Node.leaf("5")]  # String "5" should be converted to int 5

    result, on_depth, max_depth, position = bind_with_schema_ext(ctx, metadata, args)

    assert position is None
    assert result == {"n": 5, "lim": 3}
    assert on_depth is None
    assert max_depth is None


def test_queries_interpretation_bind_ext_defaults(make_ctx):
    """Test that bind_with_schema_ext fills in default values."""
    metadata = MockMetadata(
        {
            "properties": {
                "n": {"type": "integer", "default": 1},
                "lim": {"type": "integer", "default": 3},
            },
            "required": [],
        }
    )

    ctx = make_ctx()
    args = []  # No args provided

    result, on_depth, max_depth, position = bind_with_schema_ext(ctx, metadata, args)

    assert position is None
    assert result == {"n": 1, "lim": 3}
    assert on_depth is None
    assert max_depth is None


def test_queries_interpretation_bind_ext_missing_required(make_ctx):
    """Test that bind_with_schema_ext raises for missing required args."""
    metadata = MockMetadata(
        {
            "properties": {
                "n": {"type": "integer"},
            },
            "required": ["n"],
        }
    )

    ctx = make_ctx()
    args = []  # Missing required 'n'

    with pytest.raises(ExceptionWithAdvice) as exc_info:
        bind_with_schema_ext(ctx, metadata, args)

    assert "Missing required arguments" in str(exc_info.value)


def test_queries_interpretation_bind_ext_multiple_args(make_ctx):
    """Test binding multiple positional arguments."""
    metadata = MockMetadata(
        {
            "properties": {
                "n": {"type": "integer"},
                "lim": {"type": "integer"},
            },
            "required": ["n", "lim"],
        }
    )

    ctx = make_ctx()
    args = [Node.leaf("5"), Node.leaf("2")]

    result, on_depth, max_depth, position = bind_with_schema_ext(ctx, metadata, args)

    assert position is None
    assert result == {"n": 5, "lim": 2}
    assert on_depth is None
    assert max_depth is None


def test_queries_interpretation_introspect_tool_no_params(make_ctx):
    """Test that 'tool ?' shows metadata for tools without parameters."""
    # inserter_numbers has no parameters
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_test_interp_complex,
    )
    result = _resolve_single_item(ctx, "inserter_numbers ?")

    assert isinstance(result, OperatorDescriptor)
    assert result.name == "introspect_tool"

    # Check that it has the correct argument
    args_dict = dict(result.args)
    assert args_dict.get("tool_name") == "inserter_numbers"


def test_queries_interpretation_introspect_tool_with_params(make_ctx):
    """Test that 'tool ?' shows metadata for tools with parameters."""
    # operator_with_alias has parameters (pattern with default)
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_test_interp_complex,
    )
    result = _resolve_single_item(ctx, "operator_with_alias ?")

    assert isinstance(result, OperatorDescriptor)
    assert result.name == "introspect_tool"

    # Check that it has the correct argument
    args_dict = dict(result.args)
    assert args_dict.get("tool_name") == "operator_with_alias"


def test_queries_interpretation_introspect_tool_output(make_ctx):
    """Test that introspect_tool produces nested forest output."""
    # Also load builtins to get introspect_tool
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_test_interp_complex,
    )
    qp = make_qp(ctx)
    loader = ToolsLoader(cache_dir=None, use_cache=False, kinds=kinds_vocabulary())
    bpmfs = loader.load_from_module(plugins_builtins)
    ctx._register_many_metadatas(bpmfs)

    # Test the full execution with output
    forest, attrs, render_specs, out = qp.execute_query("operator_with_at_d ?")

    # Should show pretty formatted nested forest structure
    # Use exact line-by-line comparison
    lines = out.strip().split("\n")

    # Level 0: tool name and type with source location
    assert lines[0] == "- test_interp_complex.operator_with_at_d (extender) [tests/plugins_test_interp_complex.py:47]"

    # Level 1: description, level 2: parameter info (at_d is the only explicit parameter)
    # Format: "name: type!" where ! marks required
    assert lines[1] == "  - Test operator that takes an at_d parameter."
    assert lines[2] == "  - at_d: string!"


def test_question_mark_separate_expression_lists_all(make_ctx):
    """Test that a `?` sibling in a comma-separated chain lists all tools.

    The `?` sugar lowers to a plain `help`, which lists everything that
    fits the chain - it must NOT turn into docs of the previous operator
    (regression guard for the old 'last_operator' sharing bug).
    """
    # Also load builtins to get help operator
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_test_interp_complex,
    )
    loader = ToolsLoader(cache_dir=None, use_cache=False, kinds=kinds_vocabulary())
    bpmfs = loader.load_from_module(plugins_builtins)
    ctx._register_many_metadatas(bpmfs)

    # Parse and resolve "filter_even, ?" - two separate expressions,
    # through the real parser so the sugar is lowered first
    query_node = ctx.container.get(QueryParserAPI).parse_text_to_tree("filter_even, ?", ctx.create_exec_context())
    forest, at_ds, render = ctx.container.get(QueryProcessorAPI).resolve_query(query_node, ctx.create_exec_context())

    # The first expression resolves to filter_even operator
    items = forest.items

    # Should have 2 items: filter_even operator and the question operator
    # (the ? resolves through its alias, which lists what fits the chain)
    assert len(items) == 2
    assert isinstance(items[0], OperatorDescriptor)
    assert items[0].name == "filter_even"
    assert isinstance(items[1], OperatorDescriptor)
    assert items[1].name == "?"

    # The second item should be the bare question (no pattern filter),
    # which lists all tools, not introspect_tool for
    # filter_even
    args_dict = dict(items[1].args)
    # help (general) has no tool_name filter
    assert "tool_name" not in args_dict


# Test operators for exact match resolution
def test_exact_match_resolution(make_ctx):
    """Test that exact match takes priority over substring match.

    When searching for 'cur', it should find the exact match 'cur'
    even if 'current' and 'cursor' also contain the substring 'cur'.
    """
    # Test exact match - 'cur' should match exactly 'cur', not 'current' or
    # 'cursor'
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_test_interp_complex,
    )
    result = parse_and_interpret(ctx, "cur")
    assert_operator(result, "cur")


def test_substring_match_when_no_exact_match(make_ctx):
    """Test that substring match works when there's no exact match."""

    # 'curs' should match 'cursor' via substring (no exact match for 'curs')
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_test_interp_complex,
    )
    result = parse_and_interpret(ctx, "curs")
    assert_operator(result, "cursor")


def test_ambiguous_shows_full_domain_path(make_ctx):
    """Test that ambiguity error shows full path including domain.

    When there are multiple matches, the error should show the domain-prefixed
    names for disambiguation (e.g., 'fruits.fruits' instead of just 'fruits').
    """

    # Create operators with same base name but different domains
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_test_interp_complex,
    )
    qp = make_qp(ctx)

    @annotated(meta={"tool_type": "inserter", "domain": "test_domain"})
    def op_x() -> list[int]:
        return [1, 2, 3]

    @annotated(meta={"tool_type": "inserter", "domain": "other_domain"})
    def op_y() -> list[int]:
        return [4, 5, 6]

    # Register both operators
    meta_x = _load_tool_metadata(op_x, "test_domain")
    meta_y = _load_tool_metadata(op_y, "other_domain")

    if meta_x:
        ctx._register_metadata(meta_x, op_x)
    if meta_y:
        ctx._register_metadata(meta_y, op_y)

    # Search for 'op' which should match both test_domain.op_x and
    # other_domain.op_y - the listing answers with the full domain paths
    _, _, _, out = qp.execute_query("op")

    assert "test_domain.op_x" in out
    assert "other_domain.op_y" in out


# Tests for attribute parameter validation (TASKS.md item 2)
def test_attribute_item_parameter_not_required(make_ctx):
    """Test that 'item' parameter is not reported as missing for attributes.

    When an attribute requires parameters other than 'item' (which is framework-injected),
    the error message should only show the missing non-framework parameters.
    """
    # attribute_with_param requires 'multiplier' (but 'item' is
    # framework-injected)

    # attribute_with_param requires 'multiplier' (but 'item' is
    # framework-injected)
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_test_interp_complex,
    )
    with pytest.raises(ExceptionWithAdvice) as exc_info:
        parse_and_interpret(ctx, "attribute_with_param")

    error_msg = str(exc_info.value)
    # Should show only 'multiplier' as missing, not 'item'
    assert "Missing required arguments" in error_msg
    assert "multiplier" in error_msg
    assert "'item'" not in error_msg  # 'item' should NOT be in the error


def test_attribute_with_multiple_params_only_shows_missing(make_ctx):
    """Test that when attribute has multiple parameters, only missing ones are shown.

    Even when 'item' is one of the parameters, it should not appear in the
    missing arguments list since it's framework-injected.
    """

    # attribute_with_param requires 'multiplier'
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_test_interp_complex,
    )
    with pytest.raises(ExceptionWithAdvice) as exc_info:
        parse_and_interpret(ctx, "attribute_with_param")

    error_msg = str(exc_info.value)
    assert "multiplier" in error_msg
    assert "'item'" not in error_msg


# Tests for parameterized attribute syntax (TASKS.md item 1)
def test_parameterized_attribute_parentheses_syntax(make_ctx):
    """Test that parameterized attribute syntax (attr_name arg) works correctly."""
    # Register the test attribute
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_test_interp_complex,
    )
    loader = ToolsLoader(cache_dir=None, use_cache=False, kinds=kinds_vocabulary())
    bpmfs = loader.load_from_module(sys.modules[__name__])
    ctx._register_many_metadatas(bpmfs)

    # (attribute_with_param 5) should create an AttributeDescriptor with multiplier=5
    result = parse_and_interpret(ctx, "(attribute_with_param 5)")

    assert result is not None
    assert isinstance(result.item, AttributeDescriptor)
    assert str(result.item.name) == "attribute_with_param"
    # Check that the argument was bound correctly
    args_dict = dict(result.item.args)
    assert args_dict.get("multiplier") == 5


def test_parameterized_attribute_with_string_arg(make_ctx):
    """Test parameterized attribute with string argument."""
    # (attribute_tag_checker python) should create AttributeDescriptor with tag="python"
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_test_interp_complex,
    )
    result = parse_and_interpret(ctx, "(attribute_tag_checker python)")

    assert result is not None
    assert isinstance(result.item, AttributeDescriptor)
    assert str(result.item.name) == "attribute_tag_checker"
    args_dict = dict(result.item.args)
    assert args_dict.get("tag") == "python"


def test_filter_by_attribute_with_parameterized_attribute(make_ctx):
    """Test that filter_by_attribute works with parameterized attribute syntax.

    udan "saved, filter_by_attribute (attribute_tag_checker python)"
    """
    # Load builtins to get filter_by_attribute
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_test_interp_complex,
    )
    loader = ToolsLoader(cache_dir=None, use_cache=False, kinds=kinds_vocabulary())
    bpmfs = loader.load_from_module(plugins_builtins)
    ctx._register_many_metadatas(bpmfs)

    # Parse: filter_by_attribute (attribute_tag_checker python)
    # The (attribute_tag_checker python) should be interpreted as an
    # AttributeDescriptor
    result = parse_and_interpret(ctx, "filter_by_attribute (attribute_tag_checker python)")

    assert result is not None
    assert isinstance(result.item, OperatorDescriptor)
    assert result.item.name == "filter_by_attribute"

    # Check that filter_by_attribute received the AttributeDescriptor as at_d
    # argument
    args_dict = dict(result.item.args)
    at_d_arg = args_dict.get("at_d")
    assert at_d_arg is not None
    assert isinstance(at_d_arg, AttributeDescriptor)
    assert str(at_d_arg.name) == "attribute_tag_checker"
    # Check that the tag parameter was passed correctly
    tag_args = dict(at_d_arg.args)
    assert tag_args.get("tag") == "python"


def test_parameterized_attribute_error_on_missing_params(make_ctx):
    """Test that parameterized attribute syntax shows proper error for missing parameters."""
    # (attribute_with_param) without arguments should show error about missing 'multiplier'
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_test_interp_complex,
    )
    with pytest.raises(ExceptionWithAdvice) as exc_info:
        parse_and_interpret(ctx, "(attribute_with_param)")

    error_msg = str(exc_info.value)
    assert "multiplier" in error_msg
    assert "'item'" not in error_msg


# Tests for attributes with a framework-injected item
def test_external_attribute_item_not_in_required_params(make_ctx):
    """Test that attributes with an injected item don't show 'item' in required parameters.

    Attributes take 'item' as a framework-injected parameter, so it should
    not appear in the missing required arguments error.
    """

    # mcp_attribute_with_external_fn requires 'external_param'
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_test_interp_complex,
    )
    with pytest.raises(ExceptionWithAdvice) as exc_info:
        parse_and_interpret(ctx, "external_attribute_with_param")

    error_msg = str(exc_info.value)
    # Should show only 'external_param' as missing, not 'item'
    assert "external_param" in error_msg
    assert "'item'" not in error_msg


def test_external_attribute_with_parentheses_syntax(make_ctx):
    """Test that attributes with an injected item work with parentheses syntax.

    This runs: (external_attribute_with_param test_value).
    """
    # (external_attribute_with_param test_value) should work
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_test_interp_complex,
    )
    result = parse_and_interpret(ctx, "(external_attribute_with_param test_value)")

    assert result is not None
    assert isinstance(result.item, AttributeDescriptor)
    assert str(result.item.name) == "external_attribute_with_param"
    args_dict = dict(result.item.args)
    assert args_dict.get("external_param") == "test_value"


def test_external_attribute_in_filter_by_attribute(make_ctx):
    """Test the attribute together with filter_by_attribute.

    udan "saved, filter_by_attribute (attribute_tag_checker python)"
    """
    # Load builtins to get filter_by_attribute
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_test_interp_complex,
    )
    loader = ToolsLoader(cache_dir=None, use_cache=False, kinds=kinds_vocabulary())
    bpmfs = loader.load_from_module(plugins_builtins)
    ctx._register_many_metadatas(bpmfs)

    # Parse: filter_by_attribute (external_attribute_with_param python)
    result = parse_and_interpret(ctx, "filter_by_attribute (external_attribute_with_param python)")

    assert result is not None
    assert isinstance(result.item, OperatorDescriptor)
    assert result.item.name == "filter_by_attribute"

    # Verify the at_d argument is an AttributeDescriptor with correct
    # parameters
    args_dict = dict(result.item.args)
    at_d_arg = args_dict.get("at_d")
    assert at_d_arg is not None
    assert isinstance(at_d_arg, AttributeDescriptor)


def test_queries_interpretation_help_comma_render_introspect(make_ctx):
    """Test that '?, :?' shows only renders (last operator wins)."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_test_interp_complex,
    )
    qp = make_qp(ctx)
    loader = ToolsLoader(cache_dir=None, use_cache=False, kinds=kinds_vocabulary())
    bpmfs = loader.load_from_module(plugins_builtins)
    ctx._register_many_metadatas(bpmfs)

    _, attrs, render, out = qp.execute_query("?, :?")
    # Should contain render-specific operators
    assert "render_raw" in out
    # Should NOT contain 'vars' which is a non-render inserter
    assert " - vars ::" not in out


def test_queries_interpretation_render_introspect_comma_help(make_ctx):
    """Test that ':?, ?' shows all tools (last operator wins)."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_test_interp_complex,
    )
    qp = make_qp(ctx)
    loader = ToolsLoader(cache_dir=None, use_cache=False, kinds=kinds_vocabulary())
    bpmfs = loader.load_from_module(plugins_builtins)
    ctx._register_many_metadatas(bpmfs)

    _, attrs, render, out = qp.execute_query(":?, ?")
    # Chain-aware listing grouped by domain: what fits the chain position is shown
    assert "- domain=builtins ::" in out
    assert "attributes_ops.extend_by_attribute" in out
    # the pre-render system attribute lives in the renders package now
    assert "- renders.render ::" in out
    assert "- test_interp_complex.inserter_numbers ::" in out


# Tests for the "Cannot bind arguments of ..." binding error message.
# convert_value failures during argument binding must surface as a clean
# ExceptionWithAdvice naming the tool, not as a raw ValueError/traceback.


def _make_binding_error_ctx(make_ctx):
    """Build a context with builtins registered (limit, double, ...)."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_test_interp_complex,
    )
    loader = ToolsLoader(cache_dir=None, use_cache=False, kinds=kinds_vocabulary())
    bpmfs = loader.load_from_module(plugins_builtins)
    ctx._register_many_metadatas(bpmfs)
    return ctx


def test_binding_error_names_the_tool(make_ctx):
    """Test that a type-conversion failure names the tool in the error.

    `limit abc` binds "abc" to limit's `limit: int` parameter; the conversion
    ValueError must come out as 'Cannot bind arguments of 'limit': ...'.
    """
    ctx = _make_binding_error_ctx(make_ctx)
    qp = make_qp(ctx)

    _, _, _, out = qp.execute_query("range 5, limit abc")
    assert out.startswith("Cannot bind arguments of 'limit':")
    assert "Expected argument with name=limit is integer, found: abc" in out
    assert "Traceback" not in out


def test_binding_error_scalar_into_string_param(make_ctx):
    """Test that a scalar literal bound to a string-typed parameter is forbidden.

    `double(2)` puts the scalar 2 next to `value` which is an attribute name
    (string) - the binding must fail cleanly instead of handing "2" to the
    attribute (which is what let `double 2` do string repetition).
    """
    ctx = _make_binding_error_ctx(make_ctx)
    qp = make_qp(ctx)

    _, _, _, out = qp.execute_query("range 3, double(2)")
    assert out.startswith("Cannot bind arguments of 'double':")
    assert "Expected argument with name=value to be string, found: 2" in out
    assert "Traceback" not in out


def _resolve_single_item(ctx: UdanContext, query: str) -> object:
    """Resolve a one-item query through the public pipeline and return its item.

    The question sugar is a processor extra, so the question-argument rewrites
    only exist on the real flow (resolve_query); parse_and_interpret replays the
    resolver in isolation, without the extras.

    Args:
        ctx: The engine context a make_ctx call returned
        query: The one-item query text

    Returns:
        The resolved chain item (a descriptor or a value)
    """
    forest, _, _ = ctx.container.get(QueryProcessorAPI).resolve_query(parse_tree(query), ctx.create_exec_context())
    return forest.items[0]
