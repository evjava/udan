"""Tests for parameter binding through query interpretation.

This module tests parameter binding (positional, named, defaults) through the
interpretation system, using a simple test tool.
"""

import pytest

import tests.plugins_test_interp_binding
from tests.conftest import kinds_vocabulary, make_qp
from tests.test_helpers import parse_and_interpret
from udan.attributes import plugins_operators_attribute
from udan.core.impl_udan_context import UdanContext
from udan.core_tools_loading.impl_tools_loader import ToolsLoader
from udan.plugins_history import plugins_history
from udan.plugins_tools_core import plugins_system
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.plugins_tools_examples import plugins_builtins
from udan.renders import plugins_renders


@pytest.fixture
def ctx_with_insert_range(make_ctx):
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_system,
        plugins_history,
        plugins_renders,
    )
    loader = ToolsLoader(cache_dir=None, use_cache=False, kinds=kinds_vocabulary())
    metadata_fns = loader.load_from_module(tests.plugins_test_interp_binding)
    ctx._register_many_metadatas(metadata_fns)
    return ctx


def test_bind_ext_named_only(ctx_with_insert_range: UdanContext):
    """Test binding with named arguments only (--min_value=5)."""
    result = parse_and_interpret(ctx_with_insert_range, "insert_range --min_value=5")

    assert result.item.name == "insert_range"
    args_dict = dict(result.item.args)
    assert args_dict == {"min_value": 5, "max_value": 10, "step": 1}


def test_bind_ext_named_override(ctx_with_insert_range: UdanContext):
    """Test binding with named arguments overriding defaults (--min_value=0 --max_value=5 --step=2)."""
    result = parse_and_interpret(ctx_with_insert_range, "insert_range --min_value=0 --max_value=5 --step=2")

    assert result.item.name == "insert_range"
    args_dict = dict(result.item.args)
    assert args_dict == {"min_value": 0, "max_value": 5, "step": 2}


def test_bind_ext_positional_only(ctx_with_insert_range: UdanContext):
    """Test binding with positional argument only (5)."""
    result = parse_and_interpret(ctx_with_insert_range, "insert_range 5")

    assert result.item.name == "insert_range"
    args_dict = dict(result.item.args)
    assert args_dict == {"min_value": 5, "max_value": 10, "step": 1}


def test_bind_ext_positional_full(ctx_with_insert_range: UdanContext):
    """Test binding with all positional arguments (0 10 2)."""
    result = parse_and_interpret(ctx_with_insert_range, "insert_range 0 10 2")

    assert result.item.name == "insert_range"
    args_dict = dict(result.item.args)
    assert args_dict == {"min_value": 0, "max_value": 10, "step": 2}


def test_bind_ext_mixed_positional_and_named(ctx_with_insert_range: UdanContext):
    """Test binding with positional and named arguments (5 --step=2)."""
    result = parse_and_interpret(ctx_with_insert_range, "insert_range 5 --step=2")

    assert result.item.name == "insert_range"
    args_dict = dict(result.item.args)
    assert args_dict == {"min_value": 5, "max_value": 10, "step": 2}


def test_bind_ext_named_only_reverse_order(ctx_with_insert_range: UdanContext):
    """Test binding with named arguments in reverse order (--step=2 --max_value=20 --min_value=0)."""
    result = parse_and_interpret(ctx_with_insert_range, "insert_range --step=2 --max_value=20 --min_value=0")

    assert result.item.name == "insert_range"
    args_dict = dict(result.item.args)
    assert args_dict == {"min_value": 0, "max_value": 20, "step": 2}


def test_bind_ext_default_args(ctx_with_insert_range: UdanContext):
    """Test binding with default arguments - in style of test_bind_arg."""

    def bind(arg: str) -> dict:
        return dict(parse_and_interpret(ctx_with_insert_range, f"insert_range {arg}".strip()).item.args)

    # All defaults (empty string - no args)
    assert bind("") == {"min_value": 0, "max_value": 10, "step": 1}
    # One positional
    assert bind("5") == {"min_value": 5, "max_value": 10, "step": 1}
    # Two positional
    assert bind("5 20") == {"min_value": 5, "max_value": 20, "step": 1}
    # Three positional
    assert bind("5 20 2") == {"min_value": 5, "max_value": 20, "step": 2}
    # Mixed positional and named
    assert bind("5 --step=2") == {"min_value": 5, "max_value": 10, "step": 2}
    # All named
    assert bind("--min_value=5 --step=2") == {"min_value": 5, "max_value": 10, "step": 2}
    # Only named (some with defaults)
    assert bind("--step=2") == {"min_value": 0, "max_value": 10, "step": 2}
    # Named in reverse order
    assert bind("--step=2 --max_value=20") == {"min_value": 0, "max_value": 20, "step": 2}


def test_bind_ext_dash_to_underscore_conversion(ctx_with_insert_range: UdanContext):
    """Test that dashes in argument names are converted to underscores.

    For example, --min-value should work the same as --min_value.
    This allows users to use more CLI-friendly argument names with dashes
    instead of underscores.
    """
    result = parse_and_interpret(ctx_with_insert_range, "insert_range --min-value=5 --max-value=20 --step=2")

    assert result.item.name == "insert_range"
    args_dict = dict(result.item.args)
    assert args_dict == {"min_value": 5, "max_value": 20, "step": 2}


def test_bind_ext_unknown_named_arg_is_advice(ctx_with_insert_range: UdanContext):
    """An unknown --flag names the available parameters instead of showing a traceback."""
    qp = make_qp(ctx_with_insert_range)
    forest, _attrs, _render_specs, out = qp.execute_query("insert_range --nope=1")

    assert forest is None
    assert "there is no parameter `--nope`" in out
    assert "to show help write `insert_range?`" in out
    assert (
        "Available parameters:\n  - min_value: integer(=0)\n  - max_value: integer(=10)\n  - step: integer(=1)"
    ) in out
    assert "Traceback" not in out


@pytest.fixture
def ctx_with_framework_params(make_ctx):
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_system,
        plugins_history,
        plugins_renders,
    )
    loader = ToolsLoader(cache_dir=None, use_cache=False, kinds=kinds_vocabulary())
    metadata_fns = loader.load_from_module(tests.plugins_test_interp_binding)
    ctx._register_many_metadatas(metadata_fns)
    return ctx


def test_bind_positional_excludes_framework_params(ctx_with_framework_params: UdanContext):
    """Test that positional binding excludes framework parameters (ctx, item, items, nodes).

    Framework parameters are automatically injected by the framework and should
    not be bound by positional arguments. Positional arguments should bind to
    user-defined parameters in order.
    """
    # Test with insert_with_framework_params(ctx, value)
    # Positional argument '5' should bind to 'value', not 'ctx'
    result = parse_and_interpret(ctx_with_framework_params, "insert_with_framework_params 5")

    assert result.item.name == "insert_with_framework_params"
    args_dict = dict(result.item.args)
    # 'ctx' is framework-injected, 'value' gets the positional arg
    assert args_dict == {"value": 5}


def test_bind_positional_item_param_excluded(ctx_with_framework_params: UdanContext):
    qp_with_framework_params = make_qp(ctx_with_framework_params)
    """Test that 'item' framework parameter is excluded from positional binding.

    When an operator has 'item' as a framework parameter, positional arguments
    should bind to user-defined parameters, not 'item'.
    """
    # We need to test through a query that uses the filter
    # The filter_with_item_and_param has 'item' (framework) and 'threshold' (user)
    # When used as "filter_with_item_and_param 10", the '10' should bind to
    # 'threshold'

    # Use insert_range to get some numbers, then filter them
    # The positional arg '5' should bind to 'threshold', not 'item'
    result = qp_with_framework_params.execute_query("insert_range 0 10, filter_with_item_and_param 5")

    # Should filter out numbers > 5, leaving 6, 7, 8, 9
    forest, attrs, render_specs, out = result
    assert forest.items == [6, 7, 8, 9]
