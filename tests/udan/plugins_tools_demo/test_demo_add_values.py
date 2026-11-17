"""Tests for add_values attribute with extend_by_attribute."""

from tests.conftest import make_qp
from udan.attributes import plugins_operators_attribute
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.plugins_tools_examples import plugins_builtins
from udan.renders import plugins_renders


def test_add_values_via_query(make_ctx):
    """Test add_values through query execution with extend_by_attribute."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 2, extend_by_attribute (add_values 1 2), :list")
    assert out == "[0, [1, 2], 1, [2, 3]]"
