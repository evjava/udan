"""Tests for implicit variables and new syntax."""

import pytest

import udan.plugins_tools_demo.plugins_demo
import udan.plugins_tools_demo.plugins_fruits
import udan.plugins_tools_examples.plugins_builtins_set_operations
from tests.conftest import make_qp, register_tools_from_module


@pytest.fixture
def ctx_with_plugins(make_ctx):
    """Provide an UdanContext with plugins registered."""
    ctx = make_ctx()
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_examples.plugins_builtins_set_operations.__name__)
    return ctx


def test_numbers_3_shorthand(ctx_with_plugins):
    qp_with_plugins = make_qp(ctx_with_plugins)
    """Test that 'range 3' works and outputs [0, 1, 2]"""
    forest, attrs, render, out = qp_with_plugins.execute_query("range 3")

    lines = out.strip().split("\n")
    assert len(lines) == 3
    assert lines[0] == "- 0"
    assert lines[1] == "- 1"
    assert lines[2] == "- 2"


def test_numbers_shorthand_with_assignment(ctx_with_plugins):
    qp_with_plugins = make_qp(ctx_with_plugins)
    """Test 'a := (range 3); $a' with shorthand"""
    ctx_with_plugins._clear_variables()

    forest, attrs, render, out = qp_with_plugins.execute_query("a := (range 3); $a")

    lines = out.strip().split("\n")
    assert len(lines) == 3
    assert lines[0] == "- 0"
    assert lines[1] == "- 1"
    assert lines[2] == "- 2"


def test_variable_assignment_with_dollar_reference(ctx_with_plugins):
    qp_with_plugins = make_qp(ctx_with_plugins)
    """Test 'a := (range 0 3); $a' syntax"""
    ctx_with_plugins._clear_variables()

    # This should work with semicolon and $ prefix
    forest, attrs, render, out = qp_with_plugins.execute_query("a := (range 0 3); $a")

    lines = out.strip().split("\n")
    assert len(lines) == 3
    assert lines[0] == "- 0"
    assert lines[1] == "- 1"
    assert lines[2] == "- 2"


def test_variable_dollar_reference_works(ctx_with_plugins):
    qp_with_plugins = make_qp(ctx_with_plugins)
    """Test that $a reference works"""
    ctx_with_plugins._clear_variables()

    qp_with_plugins.execute_query("a := (range 0 3)")
    assert ctx_with_plugins.has_variable("a")

    # Reference with $ prefix
    forest, attrs, render, out = qp_with_plugins.execute_query("$a")

    lines = out.strip().split("\n")
    assert len(lines) == 3
    assert lines[0] == "- 0"
    assert lines[1] == "- 1"
    assert lines[2] == "- 2"


def test_set_operations_with_dollar_syntax(ctx_with_plugins):
    qp_with_plugins = make_qp(ctx_with_plugins)
    """Test set operations with new $ syntax"""
    ctx_with_plugins._clear_variables()

    qp_with_plugins.execute_query("a := (range 0 7)")
    qp_with_plugins.execute_query("b := (range 0 5)")

    # intersect a b should still work with positional args
    forest, attrs, render, out = qp_with_plugins.execute_query("intersect a b")

    lines = out.strip().split("\n")
    assert len(lines) == 5
    assert lines[0] == "- 0"
    assert lines[4] == "- 4"


def test_multiple_statements_with_semicolon(ctx_with_plugins):
    qp_with_plugins = make_qp(ctx_with_plugins)
    """Test multiple statements separated by semicolon"""
    ctx_with_plugins._clear_variables()

    # Assign two variables and reference both
    forest, attrs, render, out = qp_with_plugins.execute_query("a := (range 0 3); b := (range 5 8); $a")

    lines = out.strip().split("\n")
    assert len(lines) == 3
    assert lines[0] == "- 0"
