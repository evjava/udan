"""Demo test for UdanContext._with_plugins() sugar method.

This test verifies that the convenience method for registering plugins
on an existing UdanContext works correctly.
"""

from tests.conftest import make_qp
from udan.attributes import plugins_operators_attribute
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.plugins_tools_examples import plugins_builtins


def test_exec_context_create_with_plugins_basic(make_ctx):
    """Test that the UdanContext._with_plugins sugar method registers specified plugins."""
    # Create UdanContext and register plugins using sugar method
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)

    # Verify tools are registered
    specs = ctx.registry.get_tools()

    # Check that key tools from both plugins are present
    assert "insert_fruits" in specs, "insert_fruits from udan.plugins_tools_demo.plugins_demo should be registered"
    assert "sort_by_field" in specs, "sort_by_field from plugins_builtins should be registered"
    assert "group_by_field" in specs, "group_by_field from plugins_builtins should be registered"


def test_exec_context_create_with_plugins_executes_query(make_ctx):
    """Test that the UdanContext._with_plugins sugar method works for actual query execution."""
    # Create UdanContext and register plugins
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)

    # Execute a query using operators from both plugins
    query = "insert_fruits, sort_by_field --field=name"
    forest, attrs, render_specs, out = qp.execute_query(query)

    # Verify sorting worked (fruits should be sorted by name)
    assert "apple" in out, "Result should contain 'apple'"
    assert "banana" in out, "Result should contain 'banana'"
