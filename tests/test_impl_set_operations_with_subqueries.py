"""Tests for set operations with subqueries (inline forests as arguments)."""

from tests.conftest import make_qp, register_tools_from_module
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.plugins_tools_examples import plugins_builtins, plugins_builtins_set_operations
from udan.renders import plugins_renders


def test_subqueries(make_ctx):
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins.__name__)
    register_tools_from_module(ctx, plugins_builtins_set_operations.__name__)

    forest, attrs, render_specs, out = qp.execute_query("intersect (range 3) (range 1 4), :list")
    assert out == "[1, 2]"


def test_difference_with_mixed_args(make_ctx):
    """Test difference with one subquery and one variable reference.

    Test that we can mix subqueries and variable references.
    """
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins.__name__)
    register_tools_from_module(ctx, plugins_builtins_set_operations.__name__)

    # First create a variable, then use it in a set operation
    # Semicolon separates the assignment from the chain
    q = "a := (range 5); difference a (range 2 5), :list"
    forest, attrs, render_specs, out = qp.execute_query(q)
    assert out == "[0, 1]"


def test_union_with_mixed_args(make_ctx):
    """Test union with one subquery and one variable reference."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins.__name__)
    register_tools_from_module(ctx, plugins_builtins_set_operations.__name__)

    # First create a variable
    forest, attrs, render_specs, out = qp.execute_query("a := (range 3)")

    # Then use it in a set operation with a subquery
    forest, attrs, render_specs, out = qp.execute_query("union (range 3 5) a, :list")
    # a = [0, 1, 2], (range 3 5) = [3, 4]
    # union should return [0, 1, 2, 3, 4]
    assert out == "[0, 1, 2, 3, 4]"


def test_chained_set_operations_with_subqueries(make_ctx):
    """Test chaining multiple set operations with subqueries.

    Test: difference (range 5) (union (range 2) (range 3 5))
    (range 5) = [0, 1, 2, 3, 4]
    union (range 2) (range 3 5) = union [0, 1] [3, 4] = [0, 1, 3, 4]
    difference = [2]
    """
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins.__name__)
    register_tools_from_module(ctx, plugins_builtins_set_operations.__name__)

    forest, attrs, render_specs, out = qp.execute_query("difference (range 5) (union (range 2) (range 3 5)), :list")
    assert out == "[2]"


def test_empty_result_from_subquery_difference(make_ctx):
    """Test difference where subquery results in empty set."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins.__name__)
    register_tools_from_module(ctx, plugins_builtins_set_operations.__name__)

    # (range 2) - (range 2) = []
    # Note: Empty results render as "[]"
    # This is a rendering behavior, not specific to subqueries
    forest, attrs, render_specs, out = qp.execute_query("difference (range 2) (range 2), :list")
    # The operation works correctly (produces 0 items), renders as []
    assert out == "[]"


def test_identical_subqueries(make_ctx):
    """Test union with identical subqueries."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins.__name__)
    register_tools_from_module(ctx, plugins_builtins_set_operations.__name__)

    # (range 3) union (range 3) = [0, 1, 2]
    forest, attrs, render_specs, out = qp.execute_query("union (range 3) (range 3), :list")
    assert out == "[0, 1, 2]"
