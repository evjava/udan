"""Tests for extend_multiply extender."""

import pytest

import udan.plugins_tools_demo.plugins_demo
import udan.plugins_tools_demo.plugins_fruits
from tests.conftest import make_qp, register_tools_from_module
from udan.attributes.api_attribute_runtime import AttributeRuntimeAPI
from udan.attributes.impl_attribute_runtime import AttributesContext
from udan.attributes.impl_attribute_storage import AttributeStorage
from udan.core.api_forests import Forest
from udan.core.api_operators import OperatorDescriptor
from udan.core.impl_debug_logger import DebugLogger
from udan.core.impl_exec_context import ExecContext
from udan.operator.api_operator_engine import OperatorsEngineAPI
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.plugins_tools_examples import plugins_builtins

opd = OperatorDescriptor.create


def apply_operators(ctx, items: list[OperatorDescriptor]) -> Forest:
    """Apply operators and return the resulting forest."""
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)
    forest = Forest.from_items(items)
    exec_ctx = ExecContext(logger=DebugLogger(log_time=False))

    # Create attribute storage and context for operator application
    attribute_storage = AttributeStorage(attributes={})
    attr_context = AttributesContext(
        attribute_runtime=ctx.container.get(AttributeRuntimeAPI),
        attribute_storage=attribute_storage,
        requested_attributes=forest.types.flattened_requested(),
        ctx=exec_ctx,
    )

    forest_ext = _engine(ctx)._apply_operators_in_forest(forest, exec_ctx, attr_context)
    return forest_ext


def check_forest(forest_actual, forest_expected):
    """Check that two forests are equal."""
    assert forest_actual.items == forest_expected.items
    assert forest_actual.depths == forest_expected.depths


@pytest.fixture
def ctx(make_ctx):
    """Provide an UdanContext for testing."""
    ctx = make_ctx()
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)

    register_tools_from_module(ctx, plugins_builtins.__name__)
    return ctx


def test_extend_multiply_default(make_ctx):
    """Test extend_multiply with default parameter (mults=[2])."""
    # Insert numbers 1, 2, 3 and extend with default (multiply by 2)
    ctx = make_ctx(plugins_demo, plugins_fruits)
    items = [opd("range", [("a", 1), ("b", 4)]), opd("extend_multiply")]
    forest = apply_operators(ctx, items)

    # Expected: 1 -> [2], 2 -> [4], 3 -> [6]
    assert forest.items == [1, 2, 2, 4, 3, 6]
    assert forest.depths == [0, 1, 0, 1, 0, 1]


def test_extend_multiply_single_multiplier(make_ctx):
    """Test extend_multiply with a single multiplier."""
    # Insert numbers 1, 2, 3 and extend with mults=[3]
    ctx = make_ctx(plugins_demo, plugins_fruits)
    items = [opd("range", [("a", 1), ("b", 4)]), opd("extend_multiply", [("mults", [3])])]
    forest = apply_operators(ctx, items)

    # Expected: 1 -> [3], 2 -> [6], 3 -> [9]
    assert forest.items == [1, 3, 2, 6, 3, 9]
    assert forest.depths == [0, 1, 0, 1, 0, 1]


def test_extend_multiply_multiple_multipliers(make_ctx):
    """Test extend_multiply with multiple multipliers."""
    # Insert number 5 and extend with mults=[2, 3, 4]
    ctx = make_ctx(plugins_demo, plugins_fruits)
    items = [opd("range", [("a", 5), ("b", 6)]), opd("extend_multiply", [("mults", [2, 3, 4])])]
    forest = apply_operators(ctx, items)

    # Expected: 5 -> [10, 15, 20]
    assert forest.items == [5, 10, 15, 20]
    assert forest.depths == [0, 1, 1, 1]


def test_extend_multiply_via_query(make_ctx):
    """Test extend_multiply through query execution with single multiplier."""
    # Note: ctx fixture already has demo and builtins plugins registered
    # Execute query: range 1 4, then extend with multiplier 3
    ctx = make_ctx(plugins_demo, plugins_fruits)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 1 4, extend_multiply 3")

    # Should show:
    # - 1
    #   - 3
    # - 2
    #   - 6
    # - 3
    #   - 9
    lines = out.strip().split("\n")
    assert len(lines) >= 6
    assert lines[0] == "- 1"
    assert lines[1] == "  - 3"


def test_extend_multiply_via_query_multiple_multipliers(make_ctx):
    """Test extend_multiply through query execution with multiple multipliers."""
    # Note: ctx fixture already has demo and builtins plugins registered
    # Execute query: range 5 6, then extend with multipliers 2, 3, 4
    ctx = make_ctx(plugins_demo, plugins_fruits)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 5 6, extend_multiply 2 3 4")

    # Should show:
    # - 5
    #   - 10
    #   - 15
    #   - 20
    lines = out.strip().split("\n")
    assert len(lines) >= 4
    assert lines[0] == "- 5"
    assert "10" in lines[1]
    assert "15" in lines[2]
    assert "20" in lines[3]


def test_extend_multiply_max_depth_via_query(make_ctx):
    """Test extend_multiply with --max-depth producing a nested chain of extensions."""
    ctx = make_ctx(plugins_demo, plugins_fruits)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 2 3, extend_multiply 2 --max-depth=3")

    assert forest.items == [2, 4, 8, 16, 32]
    assert forest.depths == [0, 1, 2, 3, 4]


def test_extend_multiply_max_depth_branching_via_query(make_ctx):
    """Test extend_multiply with --max-depth and multiple multipliers at each level."""
    ctx = make_ctx(plugins_demo, plugins_fruits)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 1 2, extend_multiply 2 3 --max-depth=1")

    assert forest.items == [1, 2, 4, 6, 3, 6, 9]
    assert forest.depths == [0, 1, 2, 2, 1, 2, 2]


def test_extend_multiply_max_depth_zero_via_query(make_ctx):
    """Test extend_multiply with --max-depth=0 keeps the default single extension."""
    ctx = make_ctx(plugins_demo, plugins_fruits)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 2 3, extend_multiply 2 --max-depth=0")

    assert forest.items == [2, 4]
    assert forest.depths == [0, 1]


def test_extend_multiply_rejects_non_integer_multipliers_at_binding(make_ctx):
    """A word among the multipliers is a binding error, even when --on-depth hides the run.

    UDAN-489: a missing comma (`extend_multiply 2 3 filter_by_attribute is_even`)
    binds the two tool names as multipliers; the failure must surface at binding
    time. Before, it waited for the extender to run - and `--on-depth=1` never ran
    it on depth-0 items, so the query silently degraded to `range 2`.
    """
    ctx = make_ctx(plugins_demo, plugins_fruits)
    qp = make_qp(ctx)

    _, _, _, out = qp.execute_query("range 2, extend_multiply 2 3 filter_by_attribute is_even --on-depth=1")

    assert out.startswith("Cannot bind arguments of 'extend_multiply':")
    assert "Expected argument with name=mults is integer, found: filter_by_attribute" in out


def _engine(ctx):
    """The operators engine, resolved from the container the fixture built."""
    return ctx.container.get(OperatorsEngineAPI)
