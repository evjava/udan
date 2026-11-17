"""Tests for varargs argument handling."""

import pytest

import udan.plugins_tools_demo.plugins_demo
import udan.plugins_tools_demo.plugins_fruits
from tests.conftest import make_qp, register_tools_from_module
from udan.attributes import plugins_operators_attribute
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.plugins_tools_examples import plugins_builtins
from udan.renders import plugins_renders


@pytest.fixture
def ctx(make_ctx):
    """Provide an UdanContext with demo plugin for testing."""
    ctx = make_ctx()
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)
    return ctx


@pytest.fixture
def ctx_with_renders(make_ctx):
    """Provide an UdanContext with demo plugins and renders registered."""

    ctx = make_ctx()
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)
    register_tools_from_module(ctx, plugins_builtins.__name__)
    register_tools_from_module(ctx, plugins_renders.__name__)
    return ctx


@pytest.fixture
def ctx_with_builtins(make_ctx):
    """Provide an UdanContext with demo plugins, builtins, and renders registered."""

    ctx = make_ctx()
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)
    register_tools_from_module(ctx, plugins_builtins.__name__)
    register_tools_from_module(ctx, plugins_renders.__name__)
    return ctx


def test_varargs_no_arguments(make_ctx):
    """Test varargs with no arguments returns empty list."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("varargs")

    assert forest.items == []
    assert forest.depths == []


def test_varargs_single_argument(make_ctx):
    """Test varargs with a single argument."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("varargs 1")

    # Arguments from query are strings
    assert forest.items == ["1"]
    assert forest.depths == [0]


def test_varargs_multiple_arguments(make_ctx):
    """Test varargs with multiple arguments."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("varargs 1 2 3")

    # Arguments from query are strings
    assert forest.items == ["1", "2", "3"]
    assert forest.depths == [0, 0, 0]


def test_varargs_string_arguments(make_ctx):
    """Test varargs with string arguments."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("varargs a b c")

    assert forest.items == ["a", "b", "c"]
    assert forest.depths == [0, 0, 0]


def test_varargs_mixed_arguments(make_ctx):
    """Test varargs with mixed string and numeric arguments."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("varargs hello 42 world")

    # Arguments from query are strings
    assert forest.items == ["hello", "42", "world"]
    assert forest.depths == [0, 0, 0]


def test_varargs_via_query_no_args(ctx_with_renders):
    qp_with_renders = make_qp(ctx_with_renders)
    """Test varargs through query execution with no arguments."""
    forest, attrs, render_specs, out = qp_with_renders.execute_query("varargs, :list")
    # Empty list renders as [] with :list aggregate render
    assert out == "[]"


def test_varargs_via_query_with_args(ctx_with_renders):
    qp_with_renders = make_qp(ctx_with_renders)
    """Test varargs through query with arguments."""
    forest, attrs, render_specs, out = qp_with_renders.execute_query("varargs 1 2 3, :list")
    assert out == "[1, 2, 3]"


def test_varargs_via_query_string_args(ctx_with_renders):
    qp_with_renders = make_qp(ctx_with_renders)
    """Test varargs through query with string arguments."""
    forest, attrs, render_specs, out = qp_with_renders.execute_query("varargs foo bar baz, :list")
    assert out == "[foo, bar, baz]"


def test_varargs_many_arguments(make_ctx):
    """Test varargs with many arguments."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("varargs 1 2 3 4 5 6 7 8 9 10")

    # Arguments from query are strings
    assert forest.items == ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"]
    assert forest.depths == [0] * 10


def test_varargs_chained_with_operators(ctx_with_builtins):
    qp_with_builtins = make_qp(ctx_with_builtins)
    """Test varargs result can be chained with other operators."""
    forest, attrs, render_specs, out = qp_with_builtins.execute_query("varargs a b c, limit 2, :list")
    assert out == "[a, b]"


def test_varargs_extra_default(make_ctx):
    """Test varargs inserter with an extra named parameter uses its default."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("varargs_extra 1 2")

    assert forest.items == ["1", "2", "extra"]
    assert forest.depths == [0, 0, 0]


def test_varargs_extra_no_positional_args(make_ctx):
    """Test varargs inserter with extra parameter and no positional arguments."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("varargs_extra")

    assert forest.items == ["extra"]
    assert forest.depths == [0]


def test_varargs_extra_named_arg_binds_to_extra_not_vararg(make_ctx):
    """Test --extra=tail binds to the `extra` parameter, not to the vararg."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("varargs_extra 1 2 --extra=tail")

    assert forest.items == ["1", "2", "tail"]
    assert forest.depths == [0, 0, 0]
