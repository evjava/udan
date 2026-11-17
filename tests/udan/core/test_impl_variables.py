"""Tests for variable assignment and set operations."""

import pytest

import udan.plugins_tools_demo.plugins_demo
import udan.plugins_tools_demo.plugins_fruits
import udan.plugins_tools_examples.plugins_builtins_set_operations
from tests.conftest import make_qp, register_tools_from_module
from udan.core.api_operators import OperatorDescriptor


@pytest.fixture
def ctx_with_set_operations(make_ctx):
    """Provide an UdanContext with plugins_demo and plugins_builtins_set_operations registered."""
    ctx = make_ctx()
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_examples.plugins_builtins_set_operations.__name__)
    return ctx


# Test output constants
OUTPUT_NUMBERS_0_TO_2 = "- 0\n- 1\n- 2"
OUTPUT_NUMBERS_0_TO_4 = "- 0\n- 1\n- 2\n- 3\n- 4"


def test_assign_and_reference_numbers_3(ctx_with_set_operations):
    qp_with_set_operations = make_qp(ctx_with_set_operations)
    """Test the specific case: a := (range 0 3); a should output [0, 1, 2]"""
    qp_with_set_operations.execute_query("a := (range 0 3)")

    assert ctx_with_set_operations.has_variable("a")
    # Check that variable exists (use $a syntax to access with expansion)
    forest, attrs, render, out = qp_with_set_operations.execute_query("$a")
    lines = out.strip().split("\n")
    assert len(lines) == 3
    assert lines[0] == "- 0"
    assert lines[1] == "- 1"
    assert lines[2] == "- 2"


def test_assign_and_reference_simple(ctx_with_set_operations):
    qp_with_set_operations = make_qp(ctx_with_set_operations)
    """Test assigning a variable and then referencing it."""
    qp_with_set_operations.execute_query("a := (range 0 3)")

    assert ctx_with_set_operations.has_variable("a")
    var_a = ctx_with_set_operations._get_variable("a")
    # Variables store unexpanded operator descriptors (lazy evaluation)
    assert len(var_a.items) == 1
    assert isinstance(var_a.items[0], OperatorDescriptor)
    assert var_a.items[0].name == "range"

    forest2, attrs2, render2, out2 = qp_with_set_operations.execute_query("$a")
    lines = out2.strip().split("\n")
    assert lines[0] == "- 0"
    assert lines[1] == "- 1"
    assert lines[2] == "- 2"


def test_assign_multiple_variables(ctx_with_set_operations):
    qp_with_set_operations = make_qp(ctx_with_set_operations)
    """Test assigning multiple variables."""
    qp_with_set_operations.execute_query("a := (range 0 5)")
    qp_with_set_operations.execute_query("b := (range 10 15)")

    assert ctx_with_set_operations.has_variable("a")
    assert ctx_with_set_operations.has_variable("b")

    var_a = ctx_with_set_operations._get_variable("a")
    var_b = ctx_with_set_operations._get_variable("b")

    # Variables store unexpanded operator descriptors (lazy evaluation)
    assert len(var_a.items) == 1
    assert isinstance(var_a.items[0], OperatorDescriptor)
    assert var_a.items[0].name == "range"
    assert len(var_b.items) == 1
    assert isinstance(var_b.items[0], OperatorDescriptor)
    assert var_b.items[0].name == "range"


def test_reassign_variable(ctx_with_set_operations):
    qp_with_set_operations = make_qp(ctx_with_set_operations)
    """Test that variables can be reassigned."""
    qp_with_set_operations.execute_query("a := (range 0 3)")
    # Check initial value
    forest, attrs, render, out = qp_with_set_operations.execute_query("$a")
    lines = out.strip().split("\n")
    assert len(lines) == 3

    qp_with_set_operations.execute_query("a := (range 10 15)")
    # Check reassigned value
    forest, attrs, render, out = qp_with_set_operations.execute_query("$a")
    lines = out.strip().split("\n")
    assert len(lines) == 5
    assert lines[0] == "- 10"
    assert lines[1] == "- 11"
    assert lines[2] == "- 12"
    assert lines[3] == "- 13"
    assert lines[4] == "- 14"


def test_intersect_basic(ctx_with_set_operations):
    qp_with_set_operations = make_qp(ctx_with_set_operations)
    """Test basic intersection."""
    ctx_with_set_operations._clear_variables()

    qp_with_set_operations.execute_query("a := (range 0 7)")
    qp_with_set_operations.execute_query("b := (range 0 5)")

    forest, attrs, render, out = qp_with_set_operations.execute_query("intersect a b")

    lines = out.strip().split("\n")
    assert len(lines) == 5
    assert lines[0] == "- 0"
    assert lines[1] == "- 1"
    assert lines[2] == "- 2"
    assert lines[3] == "- 3"
    assert lines[4] == "- 4"


def test_intersect_with_parens(ctx_with_set_operations):
    qp_with_set_operations = make_qp(ctx_with_set_operations)
    """Test intersect with parentheses syntax."""
    ctx_with_set_operations._clear_variables()

    qp_with_set_operations.execute_query("x := (range 0 6)")
    qp_with_set_operations.execute_query("y := (range 0 4)")

    forest, attrs, render, out = qp_with_set_operations.execute_query("(intersect x y)")

    lines = out.strip().split("\n")
    assert len(lines) == 4
    for i in range(4):
        assert lines[i] == f"- {i}"


def test_union_basic(ctx_with_set_operations):
    qp_with_set_operations = make_qp(ctx_with_set_operations)
    """Test basic union operation."""
    ctx_with_set_operations._clear_variables()

    qp_with_set_operations.execute_query("a := (range 0 3)")
    qp_with_set_operations.execute_query("b := (range 5 8)")

    forest, attrs, render, out = qp_with_set_operations.execute_query("union a b")

    lines = out.strip().split("\n")
    assert len(lines) == 6
    expected = [0, 1, 2, 5, 6, 7]
    for i, val in enumerate(expected):
        assert lines[i] == f"- {val}"


def test_union_with_overlap(ctx_with_set_operations):
    qp_with_set_operations = make_qp(ctx_with_set_operations)
    """Test union with overlapping sets."""
    ctx_with_set_operations._clear_variables()

    qp_with_set_operations.execute_query("a := (range 0 5)")
    qp_with_set_operations.execute_query("b := (range 3 8)")

    forest, attrs, render, out = qp_with_set_operations.execute_query("union a b")

    lines = out.strip().split("\n")
    assert len(lines) == 8
    for i in range(8):
        assert lines[i] == f"- {i}"


def test_difference_basic(ctx_with_set_operations):
    qp_with_set_operations = make_qp(ctx_with_set_operations)
    """Test basic difference operation."""
    ctx_with_set_operations._clear_variables()

    qp_with_set_operations.execute_query("a := (range 0 10)")
    qp_with_set_operations.execute_query("b := (range 0 5)")

    forest, attrs, render, out = qp_with_set_operations.execute_query("difference a b")

    lines = out.strip().split("\n")
    assert len(lines) == 5
    expected = [5, 6, 7, 8, 9]
    for i, val in enumerate(expected):
        assert lines[i] == f"- {val}"


def test_symmetric_difference(ctx_with_set_operations):
    qp_with_set_operations = make_qp(ctx_with_set_operations)
    """Test symmetric difference operation."""
    ctx_with_set_operations._clear_variables()

    qp_with_set_operations.execute_query("a := (range 0 5)")
    qp_with_set_operations.execute_query("b := (range 3 8)")

    forest, attrs, render, out = qp_with_set_operations.execute_query("symmetric_difference a b")

    lines = out.strip().split("\n")
    assert len(lines) == 6
    expected = [0, 1, 2, 5, 6, 7]
    for i, val in enumerate(expected):
        assert lines[i] == f"- {val}"


def test_undefined_variable_error(ctx_with_set_operations):
    qp_with_set_operations = make_qp(ctx_with_set_operations)
    """Test that referencing an undefined variable raises an error."""
    ctx_with_set_operations._clear_variables()

    forest, attrs, render, out = qp_with_set_operations.execute_query("intersect nonexistent x")

    assert "not defined" in out


def test_clear_variables(ctx_with_set_operations):
    qp_with_set_operations = make_qp(ctx_with_set_operations)
    """Test clearing all variables."""
    qp_with_set_operations.execute_query("a := (range 0 3)")
    qp_with_set_operations.execute_query("b := (range 0 5)")

    assert len(ctx_with_set_operations._list_variables()) == 2

    ctx_with_set_operations._clear_variables()

    assert len(ctx_with_set_operations._list_variables()) == 0
    assert not ctx_with_set_operations.has_variable("a")
    assert not ctx_with_set_operations.has_variable("b")


def test_list_variables(ctx_with_set_operations):
    qp_with_set_operations = make_qp(ctx_with_set_operations)
    """Test listing all variables."""
    # Clear any pre-loaded variables from .udan/vars.env
    ctx_with_set_operations._clear_variables()

    qp_with_set_operations.execute_query("x := (range 0 3)")
    qp_with_set_operations.execute_query("y := (range 0 5)")
    qp_with_set_operations.execute_query("z := (range 0 7)")

    vars = ctx_with_set_operations._list_variables()
    assert set(vars) == {"x", "y", "z"}
