"""Tests for boolean flag argument handling (--flag, --noflag)."""

import pytest

import udan.plugins_tools_demo.plugins_demo
import udan.plugins_tools_demo.plugins_fruits
from tests.conftest import make_qp, register_tools_from_module
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
    """Provide an UdanContext with demo plugins, renders, and org renders registered."""

    ctx = make_ctx()
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)
    register_tools_from_module(ctx, plugins_builtins.__name__)
    register_tools_from_module(ctx, plugins_renders.__name__)
    return ctx


def test_bool_demo_default(make_ctx):
    """Test bool_demo with default parameters (no flags)."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("bool_demo")

    assert forest.items == ["a", "b", "c"]
    assert forest.depths == [0, 0, 0]


def test_bool_demo_reverse_true_via_flag(make_ctx):
    """Test bool_demo with --reverse flag (sets reverse=true)."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("bool_demo --reverse")

    assert forest.items == ["c", "b", "a"]
    assert forest.depths == [0, 0, 0]


def test_bool_demo_uppercase_true_via_flag(make_ctx):
    """Test bool_demo with --uppercase flag (sets uppercase=true)."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("bool_demo --uppercase")

    assert forest.items == ["A", "B", "C"]
    assert forest.depths == [0, 0, 0]


def test_bool_demo_both_flags_true(make_ctx):
    """Test bool_demo with both --reverse and --uppercase flags."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("bool_demo --reverse --uppercase")

    assert forest.items == ["C", "B", "A"]
    assert forest.depths == [0, 0, 0]


def test_bool_demo_via_query_default(ctx_with_renders):
    qp_with_renders = make_qp(ctx_with_renders)
    """Test bool_demo through query execution with no flags."""
    forest, attrs, render_specs, out = qp_with_renders.execute_query("bool_demo, :list")
    assert out == "[a, b, c]"


def test_bool_demo_via_query_with_reverse(ctx_with_renders):
    qp_with_renders = make_qp(ctx_with_renders)
    """Test bool_demo through query with --reverse flag."""
    forest, attrs, render_specs, out = qp_with_renders.execute_query("bool_demo --reverse, :list")
    assert out == "[c, b, a]"


def test_bool_demo_via_query_with_uppercase(ctx_with_renders):
    qp_with_renders = make_qp(ctx_with_renders)
    """Test bool_demo through query with --uppercase flag."""
    forest, attrs, render_specs, out = qp_with_renders.execute_query("bool_demo --uppercase, :list")
    assert out == "[A, B, C]"


def test_bool_demo_via_query_with_both_flags(ctx_with_renders):
    qp_with_renders = make_qp(ctx_with_renders)
    """Test bool_demo through query with both --reverse and --uppercase."""
    forest, attrs, render_specs, out = qp_with_renders.execute_query("bool_demo --reverse --uppercase, :list")
    assert out == "[C, B, A]"


def test_bool_demo_via_query_with_noflag(ctx_with_renders):
    qp_with_renders = make_qp(ctx_with_renders)
    """Test bool_demo through query with --noreverse flag (explicit false)."""
    forest, attrs, render_specs, out = qp_with_renders.execute_query("bool_demo --noreverse, :list")
    # Should not reverse since reverse is explicitly False
    assert out == "[a, b, c]"


def test_bool_demo_via_query_uppercase_with_noreverse(ctx_with_renders):
    qp_with_renders = make_qp(ctx_with_renders)
    """Test bool_demo with --uppercase --noreverse (uppercase true, reverse false)."""
    forest, attrs, render_specs, out = qp_with_renders.execute_query("bool_demo --uppercase --noreverse, :list")
    assert out == "[A, B, C]"


def test_bool_demo_with_positional_and_flags(ctx_with_renders):
    qp_with_renders = make_qp(ctx_with_renders)
    """Test that positional args work with flags (if we add positional support)."""
    # For now, just test that flags are parsed correctly
    forest, attrs, render_specs, out = qp_with_renders.execute_query("bool_demo --reverse, :list")
    assert out == "[c, b, a]"
