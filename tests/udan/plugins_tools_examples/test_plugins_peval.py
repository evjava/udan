"""Tests for the peval operator provided by the plugins_peval module."""

from tests.conftest import make_qp
from udan.attributes import plugins_operators_attribute
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.plugins_tools_examples import plugins_builtins, plugins_peval


def test_peval_basic_concatenation(make_ctx):
    """Test that peval can concatenate strings using 'it' variable."""
    # Test: range 3, peval "str(it) + '.' + str(it)" should show ["0.0", "1.1",
    # "2.2"]
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_peval)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 3, peval \"str(it) + '.' + str(it)\"")

    lines = out.strip().split("\n")
    assert len(lines) == 3
    assert "- 0.0" in lines
    assert "- 1.1" in lines
    assert "- 2.2" in lines


def test_peval_multiply_numbers(make_ctx):
    """Test that peval can multiply numbers."""
    # Test: range 3, peval "it * 10" should show [0, 10, 20]
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_peval)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query('range 3, peval "it * 10"')

    lines = out.strip().split("\n")
    assert len(lines) == 3
    assert "- 0" in lines
    assert "- 10" in lines
    assert "- 20" in lines


def test_peval_string_length(make_ctx):
    """Test that peval can use len() function."""
    # Test: range 10, peval "len(str(it))" should return string lengths
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_peval)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query('range 10, peval "len(str(it))"')

    lines = out.strip().split("\n")
    assert len(lines) == 10
    assert "- 1" in lines  # len("0") = 1


def test_peval_with_map_field(make_ctx):
    """Test that peval works after map_field to transform extracted values."""
    # Test: fruits, map_field name, peval "it.upper()" should uppercase fruit
    # names
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_peval)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query('fruits, map_field name, peval "it.upper()"')

    lines = out.strip().split("\n")
    assert len(lines) == 10
    assert "- APPLE" in lines
    assert "- ORANGE" in lines
    assert "- BANANA" in lines
    assert "- MANGO" in lines


def test_peval_string_formatting(make_ctx):
    """Test that peval can use string formatting."""
    # Test: range 3, peval "str(it) + '_item'" should add suffix
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_peval)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 3, peval \"str(it) + '_item'\"")

    lines = out.strip().split("\n")
    assert len(lines) == 3
    assert "- 0_item" in lines
    assert "- 1_item" in lines
    assert "- 2_item" in lines


def test_peval_with_fruits_calories(make_ctx):
    """Test that peval can work with numeric fields from fruits."""
    # Test: fruits, map_field calories, peval "it * 2 if it else it" should double
    # calories
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_peval)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query('fruits, map_field calories, peval "it * 2 if it else it"')

    lines = out.strip().split("\n")
    assert len(lines) == 10
    # apple has 52 calories, doubled is 104
    assert "- 104" in lines
    # ambrosia has None calories, should remain None
    assert "- None" in lines


def test_peval_error_handling(make_ctx):
    """Test that peval returns original item when expression fails."""
    # Test: range 3, peval "undefined_function(it)" should fail silently and
    # return original values
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_peval)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query('range 3, peval "undefined_function(it)"')

    lines = out.strip().split("\n")
    assert len(lines) == 3
    # Should return original items when expression fails
    assert "- 0" in lines
    assert "- 1" in lines
    assert "- 2" in lines


def test_peval_with_math_operations(make_ctx):
    """Test that peval can perform math operations."""
    # Test: range 5, peval "it ** 2" should square each number
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_peval)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query('range 5, peval "it ** 2"')

    lines = out.strip().split("\n")
    assert len(lines) == 5
    assert "- 0" in lines  # 0**2 = 0
    assert "- 1" in lines  # 1**2 = 1
    assert "- 4" in lines  # 2**2 = 4
    assert "- 9" in lines  # 3**2 = 9
    assert "- 16" in lines  # 4**2 = 16


def test_peval_preserves_nested_structure(make_ctx):
    """Test that peval preserves nested tree structure."""
    # Test: range 3, multiply 2, peval it should preserve the nested structure
    # multiply 2 creates: [(0, [0]), (1, [2]), (2, [4])]
    # peval it (identity) should preserve the structure
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_peval)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 3, multiply 2, peval it")

    lines = out.strip().split("\n")
    # Should have 6 total lines: 3 top-level items + 3 children
    assert len(lines) == 6

    # Check top-level items (lines without indentation - start with "-")
    top_level = [line for line in lines if line.startswith("-")]
    assert len(top_level) == 3
    assert top_level == ["- 0", "- 1", "- 2"]

    # Check children (lines with indentation - start with space)
    children = [line for line in lines if line.startswith(" ")]
    assert len(children) == 3
    assert children == ["  - 0", "  - 2", "  - 4"]

    # Verify the exact output
    assert out == "- 0\n  - 0\n- 1\n  - 2\n- 2\n  - 4"


def test_peval_modifies_all_items_in_nested_tree(make_ctx):
    """Test that peval modifies all items in nested tree, not just depth 0.

    This is the test for the task: `range 3, multiply 1 2, peval "it*100"`
    should modify all forest items, but only depth=0 was modified before the fix.
    """
    # Test: range 3, multiply 1 2, peval "it*100"
    # multiply 1 2 creates: [(0, [0, 0]), (1, [1, 2]), (2, [2, 4])]
    # All 9 items should be multiplied by 100
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_peval)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query('range 3, multiply 1 2, peval "it*100"')

    expected = "- 0\n  - 0\n  - 0\n- 100\n  - 100\n  - 200\n- 200\n  - 200\n  - 400"
    assert out == expected


def test_peval_on_depth_0(make_ctx):
    """Test that peval with --on-depth=0 only modifies depth 0 items.

    This is the test for the task: `range 3, multiply 7 11, peval "it * 0" --on-depth=0`
    should only modify depth 0 items, preserving children values.
    """
    # Test: range 3, multiply 7 11, peval "it * 0" --on-depth=0
    # multiply 7 11 creates: [(0, [0, 0]), (1, [7, 11]), (2, [14, 22])]
    # With --on-depth=0, only depth 0 items are multiplied by 0
    # Depth 0: 0*0=0, 1*0=0, 2*0=0
    # Depth 1: 0, 0, 7, 11, 14, 22 (unchanged)
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_peval)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query('range 3, multiply 7 11, peval "it * 0" --on-depth=0')

    expected = "- 0\n  - 0\n  - 0\n- 0\n  - 7\n  - 11\n- 0\n  - 14\n  - 22"
    assert out == expected


def test_peval_on_depth_leaf(make_ctx):
    """Test that peval with --on-depth=leaf only modifies the items without children.

    multiply 7 11 creates: [(0, [0, 0]), (1, [7, 11]), (2, [14, 22])], so the depth-1
    items are the leaves, and only they are multiplied by 100.
    """
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_peval)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query('range 3, multiply 7 11, peval "it * 100" --on-depth=leaf')

    expected = "- 0\n  - 0\n  - 0\n- 1\n  - 700\n  - 1100\n- 2\n  - 1400\n  - 2200"
    assert out == expected


def test_peval_on_depth_all(make_ctx):
    """Test that peval with --on-depth=all modifies every item, like no --on-depth at all."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_peval)
    qp = make_qp(ctx)
    forest_all, _, _, out_all = qp.execute_query('range 3, multiply 7 11, peval "it * 100" --on-depth=all')
    forest_plain, _, _, _ = qp.execute_query('range 3, multiply 7 11, peval "it * 100"')

    expected = "- 0\n  - 0\n  - 0\n- 100\n  - 700\n  - 1100\n- 200\n  - 1400\n  - 2200"
    assert out_all == expected
    assert forest_all.items == forest_plain.items
    assert forest_all.depths == forest_plain.depths
