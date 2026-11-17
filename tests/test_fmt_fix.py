"""Test format string with spaces and colons."""

import pytest

import udan.plugins_tools_examples.plugins_builtins
import udan.plugins_tools_examples.plugins_fs
import udan.renders.plugins_renders
from tests.conftest import make_qp, register_tools_from_module


@pytest.fixture
def ctx_with_renders(make_ctx):
    """Provide an UdanContext with fs, renders and builtins plugins registered.

    The format strings are exercised over ls_files items (Path objects with a
    name field) - a producer the core ships itself, so this file does not need
    the python plugin that used to feed it the `functions` tool.
    """
    ctx = make_ctx()
    register_tools_from_module(ctx, udan.plugins_tools_examples.plugins_builtins.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_examples.plugins_fs.__name__)
    register_tools_from_module(ctx, udan.renders.plugins_renders.__name__)
    return ctx


def test_fmt_with_spaces_and_colons(ctx_with_renders):
    qp_with_renders = make_qp(ctx_with_renders)
    """Test that format strings with spaces and colons work correctly."""
    forest, attrs, render_specs, out = qp_with_renders.execute_query(
        "ls_files tests/udan/plugins_tools_examples test_plugins_*.py, limit 1, "
        ':fmt("- {name}:{name} {name} :: {name}")'
    )
    print("Render specs:", render_specs)
    print("Output:")
    print(out)
    # The format string should contain the formatted output, not dict repr
    assert "::" in out  # Should contain our format separator


def test_fmt_simple(ctx_with_renders):
    qp_with_renders = make_qp(ctx_with_renders)
    """Test simple format string."""
    forest, attrs, render_specs, out = qp_with_renders.execute_query(
        'ls_files tests/udan/plugins_tools_examples test_plugins_*.py, limit 1, :fmt("{name}")'
    )
    print("Render specs:", render_specs)
    print("Output:")
    print(out)
    # The one item limit picks up is whichever file the glob returns first, so
    # assert the shape: a bare file name, not a path and not a dict repr
    assert out.strip().startswith("test_plugins_")
    assert out.strip().endswith(".py")
    assert "/" not in out
