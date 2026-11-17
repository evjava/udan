"""Tests for set operations: intersect, union, difference, symmetric_difference."""

from tests.conftest import make_qp, register_tools_from_module
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.plugins_tools_examples import plugins_builtins_set_operations
from udan.renders import plugins_renders


# Intersect tests
def test_intersect_basic(make_ctx) -> None:
    """Test basic intersection of two ranges."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins_set_operations.__name__)
    forest, attrs, render_specs, out = qp.execute_query("a := (range 3); b := (range 1 4); intersect $a $b, :list")
    assert out == "[1, 2]"


def test_intersect_no_overlap(make_ctx) -> None:
    """Test intersection with non-overlapping ranges."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins_set_operations.__name__)
    forest, attrs, render_specs, out = qp.execute_query("a := (range 3); b := (range 5 8); intersect $a $b, :list")
    # Empty result renders as [] with :list aggregate render
    assert out == "[]"


def test_intersect_full_overlap(make_ctx) -> None:
    """Test intersection with identical ranges."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins_set_operations.__name__)
    forest, attrs, render_specs, out = qp.execute_query("a := (range 3); b := (range 3); intersect $a $b, :list")
    assert out == "[0, 1, 2]"


def test_intersect_subset(make_ctx) -> None:
    """Test intersection where one range is subset of another."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins_set_operations.__name__)
    forest, attrs, render_specs, out = qp.execute_query("a := (range 10); b := (range 3 7); intersect $a $b, :list")
    assert out == "[3, 4, 5, 6]"


def test_intersect_large_numbers(make_ctx) -> None:
    """Test intersection with large number ranges."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins_set_operations.__name__)
    forest, attrs, render_specs, out = qp.execute_query(
        "a := (range 0 100 5); b := (range 0 100 7); intersect $a $b, :list"
    )
    # Intersection of multiples of 5 and 7 up to 100
    assert out == "[0, 35, 70]"


# Union tests
def test_union_basic(make_ctx) -> None:
    """Test basic union of two ranges."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins_set_operations.__name__)
    forest, attrs, render_specs, out = qp.execute_query("a := (range 3); b := (range 3 6); union $a $b, :list")
    assert out == "[0, 1, 2, 3, 4, 5]"


def test_union_with_overlap(make_ctx) -> None:
    """Test union with overlapping ranges."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins_set_operations.__name__)
    forest, attrs, render_specs, out = qp.execute_query("a := (range 5); b := (range 3 8); union $a $b, :list")
    assert out == "[0, 1, 2, 3, 4, 5, 6, 7]"


def test_union_no_overlap(make_ctx) -> None:
    """Test union with non-overlapping ranges."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins_set_operations.__name__)
    forest, attrs, render_specs, out = qp.execute_query("a := (range 3); b := (range 5 8); union $a $b, :list")
    assert out == "[0, 1, 2, 5, 6, 7]"


def test_union_identical(make_ctx) -> None:
    """Test union with identical ranges."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins_set_operations.__name__)
    forest, attrs, render_specs, out = qp.execute_query("a := (range 3); b := (range 3); union $a $b, :list")
    assert out == "[0, 1, 2]"


def test_union_large_ranges(make_ctx) -> None:
    """Test union with larger number ranges."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins_set_operations.__name__)
    forest, attrs, render_specs, out = qp.execute_query(
        "a := (range 0 100 5); b := (range 0 100 7); union $a $b, :list, :nolimit"
    )
    # Union of multiples of 5 and 7 up to 100
    expected = (
        "[0, 5, 7, 10, 14, 15, 20, 21, 25, 28, 30, 35, 40, 42, 45, 49, "
        "50, 55, 56, 60, 63, 65, 70, 75, 77, 80, 84, 85, 90, 91, 95, 98]"
    )
    assert out == expected


# Difference tests
def test_difference_basic(make_ctx) -> None:
    """Test basic difference (a \\ b)."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins_set_operations.__name__)
    forest, attrs, render_specs, out = qp.execute_query("a := (range 10); b := (range 3); difference $a $b, :list")
    assert out == "[3, 4, 5, 6, 7, 8, 9]"


def test_difference_no_overlap(make_ctx) -> None:
    """Test difference with non-overlapping ranges returns first set."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins_set_operations.__name__)
    forest, attrs, render_specs, out = qp.execute_query("a := (range 3); b := (range 5 8); difference $a $b, :list")
    assert out == "[0, 1, 2]"


def test_difference_subset(make_ctx) -> None:
    """Test difference where second set is subset of first."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins_set_operations.__name__)
    forest, attrs, render_specs, out = qp.execute_query("a := (range 10); b := (range 3 7); difference $a $b, :list")
    assert out == "[0, 1, 2, 7, 8, 9]"


def test_difference_empty_result(make_ctx) -> None:
    """Test difference where sets are identical returns empty."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins_set_operations.__name__)
    forest, attrs, render_specs, out = qp.execute_query("a := (range 3); b := (range 3); difference $a $b, :list")
    # Empty result renders as [] with :list aggregate render
    assert out == "[]"


def test_difference_large_ranges(make_ctx) -> None:
    """Test difference with larger ranges."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins_set_operations.__name__)
    forest, attrs, render_specs, out = qp.execute_query(
        "a := (range 0 50 3); b := (range 0 50 5); difference $a $b, :list"
    )
    # Multiples of 3 that are not multiples of 5
    assert out == "[3, 6, 9, 12, 18, 21, 24, 27, 33, 36, 39, 42, 48]"


# Symmetric difference tests
def test_symmetric_difference_basic(make_ctx) -> None:
    """Test basic symmetric difference."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins_set_operations.__name__)
    forest, attrs, render_specs, out = qp.execute_query(
        "a := (range 5); b := (range 3 8); symmetric_difference $a $b, :list"
    )
    assert out == "[0, 1, 2, 5, 6, 7]"


def test_symmetric_difference_no_overlap(make_ctx) -> None:
    """Test symmetric difference with non-overlapping ranges is union."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins_set_operations.__name__)
    forest, attrs, render_specs, out = qp.execute_query(
        "a := (range 3); b := (range 5 8); symmetric_difference $a $b, :list"
    )
    assert out == "[0, 1, 2, 5, 6, 7]"


def test_symmetric_difference_identical(make_ctx) -> None:
    """Test symmetric difference with identical ranges returns empty."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins_set_operations.__name__)
    forest, attrs, render_specs, out = qp.execute_query(
        "a := (range 3); b := (range 3); symmetric_difference $a $b, :list"
    )
    # Empty result renders as [] with :list aggregate render
    assert out == "[]"


def test_symmetric_difference_partial_overlap(make_ctx) -> None:
    """Test symmetric difference with partial overlap."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins_set_operations.__name__)
    forest, attrs, render_specs, out = qp.execute_query(
        "a := (range 6); b := (range 4 10); symmetric_difference $a $b, :list"
    )
    assert out == "[0, 1, 2, 3, 6, 7, 8, 9]"


def test_symmetric_difference_large_ranges(make_ctx) -> None:
    """Test symmetric difference with larger ranges."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins_set_operations.__name__)
    forest, attrs, render_specs, out = qp.execute_query(
        "a := (range 0 30 3); b := (range 0 30 5); symmetric_difference $a $b, :list"
    )
    # Items in multiples of 3 or 5, but not both (15 is in both, so excluded)
    assert out == "[3, 5, 6, 9, 10, 12, 18, 20, 21, 24, 25, 27]"


# Chaining tests
def test_chain_intersect_union(make_ctx) -> None:
    """Test chaining intersect and union."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins_set_operations.__name__)
    forest, attrs, render_specs, out = qp.execute_query(
        "a := (range 5); b := (range 3 8); c := (range 6 10); i := (intersect $a $b); union $i $c, :list"
    )
    assert out == "[3, 4, 6, 7, 8, 9]"


def test_chain_difference_symmetric_difference(make_ctx) -> None:
    """Test chaining difference and symmetric_difference."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins_set_operations.__name__)
    forest, attrs, render_specs, out = qp.execute_query(
        "a := (range 10); b := (range 3 7); c := (range 5 8); "
        "d := (difference $a $b); symmetric_difference $d $c, :list"
    )
    # d = [0, 1, 2, 7, 8, 9], c = [5, 6, 7]
    # symmetric diff = [0, 1, 2, 5, 6, 8, 9]
    assert out == "[0, 1, 2, 5, 6, 8, 9]"


def test_triple_union(make_ctx) -> None:
    """Test union of three sets."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins_set_operations.__name__)
    forest, attrs, render_specs, out = qp.execute_query(
        "a := (range 3); b := (range 2 5); c := (range 4 7); ab := (union $a $b); union $ab $c, :list"
    )
    assert out == "[0, 1, 2, 3, 4, 5, 6]"
