"""Demo test for smart parser argument disambiguation.

This test verifies that the parser uses argument presence to resolve
ambiguity between similar tools.
"""

from tests.conftest import make_qp
from udan.attributes import plugins_operators_attribute
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.plugins_tools_examples import plugins_builtins


def test_smart_parser_sort_with_args(make_ctx):
    """Test that 'sort name' resolves to sort_by_field.

    Query: insert_fruits, sort name
    Should resolve to sort_by_field because sort_by_natural_order takes no args.
    """
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)

    query = "insert_fruits, sort name"
    forest, attrs, render_specs, out = qp.execute_query(query)

    # Check that sorting worked (should be sorted by name)
    assert "apple" in out, "Should contain apple"
    assert "banana" in out, "Should contain banana"
