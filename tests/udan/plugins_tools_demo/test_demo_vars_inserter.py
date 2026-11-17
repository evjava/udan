"""Demo test for vars system inserter.

This test verifies that the vars inserter shows all defined variables.
"""

from tests.conftest import make_qp
from udan.plugins_tools_core import plugins_system
from udan.plugins_tools_demo import plugins_demo, plugins_fruits


def test_vars_inserter_shows_variables(make_ctx):
    """Test that vars inserter shows all defined variables."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_system)
    qp = make_qp(ctx)

    # Assign a variable
    forest, attrs, render_specs, out = qp.execute_query("a := (fruits)")

    # Use vars inserter to show all variables
    forest2, attrs2, render_specs2, out2 = qp.execute_query("vars")

    # Should show variable 'a' with more context (not just letter 'a' in 'vars')
    assert "a:" in out2 or ("a" in out2 and "variable" in out2.lower()), f"vars should show variable 'a', got: {out2}"


def test_vars_shows_multiple_variables(make_ctx):
    """Test that vars shows multiple variables."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_system)
    qp = make_qp(ctx)

    # Assign multiple variables
    qp.execute_query("a := (range 0 3)")
    qp.execute_query("b := (range 5 8)")

    # Show all variables
    forest, attrs, render_specs, out = qp.execute_query("vars")

    # Should show both 'a' and 'b'
    assert "a:" in out or ("a" in out and "variable" in out.lower()), f"vars should show variable 'a', got: {out}"
    assert "b:" in out or ("b" in out and "variable" in out.lower()), f"vars should show variable 'b', got: {out}"
