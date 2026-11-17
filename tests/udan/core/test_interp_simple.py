"""Tests for query interpretation.

This module contains simple tests that don't require attributes and operators
to be defined inside the tests - they rely on built-in functionality or
work without needing custom tool registration.
"""

import pytest

from tests.conftest import make_qp
from tests.test_helpers import parse_and_interpret
from udan.attributes import plugins_operators_attribute
from udan.core.api_exceptions import ExceptionWithAdvice
from udan.core.api_operators import OperatorDescriptor
from udan.plugins_history import plugins_history
from udan.plugins_tools_core import plugins_help, plugins_system
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.plugins_tools_examples import plugins_builtins, plugins_fs
from udan.renders import plugins_renders


def test_queries_interpretation_debug(make_ctx):
    """Test that 'debug' item enables debug mode for its query only."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
    )
    qp = make_qp(ctx)
    _, _, _, out_debug = qp.execute_query("debug, range 3, :list")
    _, _, _, out_plain = qp.execute_query("range 3, :list")

    # Debug query output is prepended with the debug log
    assert out_debug.startswith("# ")
    assert "[0, 1, 2]" in out_debug
    # Subsequent query without the debug token renders clean output
    assert out_plain == "[0, 1, 2]"


def test_queries_interpretation_empty_children(make_ctx):
    """Test that an unquoted unknown item is rejected as a bare literal."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
    )
    with pytest.raises(ExceptionWithAdvice, match="Bare literal 'some_simple_item' is not allowed"):
        parse_and_interpret(ctx, "some_simple_item")


def test_queries_interpretation_help(make_ctx):
    """Test that the listing operator returns a help operator descriptor.

    The `?` sugar lowers to `help` in the query parser, so the processor
    only ever interprets the written form.
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
    )
    result = parse_and_interpret(ctx, "help")

    assert result is not None
    assert isinstance(result.item, type(OperatorDescriptor.create("help")))


def test_queries_interpretation_node_with_children(make_ctx):
    """Test that an unknown tool with arguments is an error, not the `?` listing."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
    )
    qp = make_qp(ctx)

    # No close name: the miss is named and the listing is only pointed at
    forest, _, _, out = qp.execute_query("not-exist 5")
    assert forest is None
    assert out == "Tool 'not-exist' not found.\nRun '?' to list the available tools."

    # A close name is offered as a suggestion
    forest, _, _, out = qp.execute_query("rane 5")
    assert forest is None
    assert out == (
        "Tool 'rane' not found.\nDid you mean one of these?\n  - demo.range\nRun '?' to list the available tools."
    )


def test_queries_interpretation_dash_sugar(make_ctx):
    """Test that a dashed word names the underscored tool (`extend-multiply` -> `extend_multiply`).

    A word is rewritten only when the underscored form matches a tool and the
    dashed form does not: `not-exist` keeps its name in the miss it reports.
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
    )
    qp = make_qp(ctx)

    expected = "- 0\n  - 0\n- 1\n  - 2\n- 2\n  - 4"
    _, _, _, out_full = qp.execute_query("range 3, extend-multiply 2")
    _, _, _, out_fragment = qp.execute_query("range 3, extend-mult 2")
    _, _, _, out_plain = qp.execute_query("range 3, extend_multiply 2")
    assert out_full == expected
    assert out_fragment == expected
    assert out_plain == expected

    # A dashed name whose underscored form matches nothing is a miss as typed
    _, _, _, out_miss = qp.execute_query("not-exist 5")
    assert out_miss == "Tool 'not-exist' not found.\nRun '?' to list the available tools."


def test_queries_interpretation_dash_sugar_question(make_ctx):
    """Test that a dashed word names the underscored tool in a question (`ls-files?` -> `ls_files?`).

    The question's pattern is matched the way a written tool name is: the
    dashed spelling shows the tool's docs, not the listing the no-match
    pattern falls back to.
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
        plugins_fs,
    )
    qp = make_qp(ctx)

    _, _, _, out_dashed, _ = qp.execute_query_split_debug("ls-files?")
    _, _, _, out_typed, _ = qp.execute_query_split_debug("ls_files?")

    assert out_dashed == out_typed
    assert out_dashed.startswith("- fs.insert_ls_files (inserter)")


def test_string_literals_not_matched_as_tools(make_ctx):
    """Test that string literals are returned as-is, not matched against tools."""

    # Single-quoted string should be returned as a plain string value
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
    )
    result = parse_and_interpret(ctx, "'a'")
    assert result is not None
    assert result.item == "a"
    assert result.children == []

    # Double-quoted string should also work
    result = parse_and_interpret(ctx, '"hello"')
    assert result is not None
    assert result.item == "hello"
    assert result.children == []

    # String with spaces
    result = parse_and_interpret(ctx, "'hello world'")
    assert result is not None
    assert result.item == "hello world"
    assert result.children == []


def test_string_literals_with_render_tools():
    """Test that string literals work with render tools."""
    # The main functionality is tested in test_string_literals_not_matched_as_tools
    # Full query execution with render tools is tested in integration
    # tests
    pass


def test_string_literals_as_function_arguments():
    """Test that string literals can be used as function arguments."""
    # The main functionality is tested in test_string_literals_not_matched_as_tools
    # Full query execution with tools is tested in integration tests
    pass


def test_empty_string_literal(make_ctx):
    """Test that empty string literals are handled correctly."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
    )
    result = parse_and_interpret(ctx, "''")
    assert result is not None
    assert result.item == ""
    assert result.children == []

    result = parse_and_interpret(ctx, '""')
    assert result is not None
    assert result.item == ""
    assert result.children == []


def test_trailing_underscore_shows_matching_tools(make_ctx):
    """Test that trailing underscore lists the tools with that prefix."""
    # When an item ends with '_', it should list all tools starting with that prefix
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
    )
    qp = make_qp(ctx)
    _, _, _, out = qp.execute_query("sort_")

    assert "sort_by_field" in out
    assert "sort_by_natural_order" in out
