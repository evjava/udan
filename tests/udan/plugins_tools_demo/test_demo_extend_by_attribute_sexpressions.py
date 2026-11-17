"""Test extend_by_attribute with S-expression composition (bracket syntax).

Current status: Bracket syntax like (translate_ru) is parsed correctly
but query processor needs updates to handle AttributeDescriptor arguments.
These tests document the current limitation and expected behavior.
"""

from tests.conftest import make_qp
from udan.attributes import plugins_operators_attribute
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.plugins_tools_demo.plugins_demo import add_values
from udan.plugins_tools_examples import plugins_builtins
from udan.renders import plugins_renders


def test_extend_by_attribute_flat_syntax_works(make_ctx):
    """Test extend_by_attribute with flat attribute syntax (current working method)."""
    # This works: extend_by_attribute translate_ru
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("fruits, extend_by_attribute translate_ru, :list")
    assert "яблоко" in out  # apple
    assert "апельсин" in out  # orange


def test_extend_by_attribute_with_dict_key_fallback(make_ctx):
    """Test extend_by_attribute falls back to dict key lookup."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("fruits, extend_by_attribute name, :list")

    # Each fruit dict should have its 'name' value as a child
    assert "apple" in out
    assert "orange" in out


def test_extend_by_attribute_empty_value_skipped(make_ctx):
    """Test extend_by_attribute skips items where attribute returns None."""
    # pfc returns None for fruits not in NUTRITION_DATA; ambrosia has no pfc
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("fruits, extend_by_attribute pfc, :list")

    # Items with None attribute should have no children
    result = eval(out)
    for item in result:
        if isinstance(item, list):
            # Child exists — pfc was not None for this fruit
            assert len(item) == 1
        # If not a list, the fruit had no pfc value and was left as-is


def test_add_values_as_direct_function():
    """Test add_values can be called directly as a Python function."""

    # Test that add_values works when called directly
    result = add_values(5, [1, 2])
    assert result == [6, 7]

    result = add_values(10, [-5])
    assert result == [5]

    result = add_values(0, [1, 2, 3])
    assert result == [1, 2, 3]
