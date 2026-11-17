"""Tests for builtins plugin operators and renders."""

from tests.conftest import make_qp, register_tools_from_module
from udan.attributes import plugins_operators_attribute
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.plugins_tools_examples import plugins_builtins
from udan.plugins_tools_examples.plugins_builtins import raiser
from udan.renders import plugins_renders


def test_attr_render_with_field_name(make_ctx):
    """Test that :attr render extracts a specific field from dict items."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)

    # Test extracting name field from fruits
    forest, attrs, render_specs, out = qp.execute_query("fruits, :attr name")

    # Should return only fruit names, one per line
    lines = out.strip().split("\n")
    assert len(lines) == 10  # All 10 fruits

    # Check specific fruits are present
    assert "apple" in lines
    assert "orange" in lines
    assert "banana" in lines
    assert "mango" in lines
    assert "ambrosia" in lines

    # No dict formatting should be present
    assert "{" not in out
    assert "}" not in out
    assert "=" not in out


def test_attr_render_with_color_field(make_ctx):
    """Test that :attr render works with different fields."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)

    # Test extracting color field
    forest, attrs, render_specs, out = qp.execute_query("fruits, :attr color")

    lines = out.strip().split("\n")

    # Check colors are present
    assert "red" in lines
    assert "orange" in lines
    assert "yellow" in lines
    assert "blue" in lines
    assert "purple" in lines

    # ambrosia has None color, should be "None"
    assert "None" in lines


def test_attr_render_with_named_argument(make_ctx):
    """Test that :attr render works with --field=value format."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)

    # Test using --field=value format
    forest, attrs, render_specs, out = qp.execute_query("fruits, :attr --field=name")

    lines = out.strip().split("\n")

    # Should work the same as positional argument
    assert len(lines) == 10
    assert "apple" in lines
    assert "orange" in lines


def test_attr_render_with_attribute_field(make_ctx):
    """Test that :attr render can extract attribute field values."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)

    # Test extracting translate_ru attribute field after applying translate extender
    # Expected: Russian translations of fruit names
    forest, attrs, render_specs, out = qp.execute_query("fruits, translate, :attr translate_ru")

    lines = out.strip().split("\n")

    # Should have translations for fruits that have the attribute (not all 10
    # have translate_ru)
    assert len(lines) == 9  # ambrosia doesn't have a translation

    # Check some Russian translations are present
    # apple -> яблоко, orange -> апельсин, banana -> банан
    assert "яблоко" in lines
    assert "апельсин" in lines
    assert "банан" in lines

    # No dict formatting should be present
    assert "{" not in out
    assert "}" not in out


def test_map_field_basic(make_ctx):
    """Test that map_field extracts a field from each dict item."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)

    # Test extracting name field from fruits using map_field
    forest, attrs, render_specs, out = qp.execute_query("fruits, map_field name")

    # Should return only fruit names
    lines = out.strip().split("\n")
    assert len(lines) == 10  # All 10 fruits

    # Check specific fruits are present (output format is "- value")
    assert "- apple" in lines
    assert "- orange" in lines
    assert "- banana" in lines
    assert "- mango" in lines
    assert "- ambrosia" in lines


def test_map_field_with_color_field(make_ctx):
    """Test that map_field works with different fields."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)

    # Test extracting color field
    forest, attrs, render_specs, out = qp.execute_query("fruits, map_field color")

    lines = out.strip().split("\n")

    # Check colors are present
    assert "- red" in lines
    assert "- orange" in lines
    assert "- yellow" in lines
    assert "- blue" in lines
    assert "- purple" in lines

    # ambrosia has None color, should be "- None"
    assert "- None" in lines


def test_map_field_none_field(make_ctx):
    """Test that map_field returns None for missing fields."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)

    # Test extracting a non-existent field
    forest, attrs, render_specs, out = qp.execute_query("fruits, map_field nonexistent_field")

    lines = out.strip().split("\n")

    # Should have None for all 10 fruits
    assert len(lines) == 10
    # All lines should be "- None"
    for line in lines:
        assert line == "- None"


def test_map_field_preserves_order(make_ctx):
    """Test that map_field preserves the order of items."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)

    forest, attrs, render_specs, out = qp.execute_query("fruits, map_field name")

    lines = out.strip().split("\n")

    # First fruit should be apple (from demo data)
    assert lines[0] == "- apple"
    # Last fruit should be ambrosia (from demo data)
    assert lines[-1] == "- ambrosia"


def test_map_field_name_on_path_objects(make_ctx):
    """Test that map_field name works with Path objects from ls_files."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, "udan.plugins_tools_examples.plugins_fs")

    # Test that map_field name extracts the .name attribute from Path objects
    forest, attrs, render_specs, out = qp.execute_query(
        "ls_files tests/udan/plugins_tools_examples test_plugins_builtins*.py, map_field name"
    )

    lines = out.strip().split("\n")

    # Should return just the filenames, not full paths
    # (directory content varies, so names are checked for membership, not counted)
    assert "- test_plugins_builtins.py" in lines
    assert "- test_plugins_builtins_set_operations.py" in lines

    # Full paths should not be present
    assert "tests/" not in out


def test_as_str_converts_numbers_to_str_items(make_ctx):
    """Test that as_str makes the forest items themselves str, not just the rendering."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)

    forest, attrs, render_specs, out = qp.execute_query("range 3, as_str")

    assert out == "- 0\n- 1\n- 2"
    assert forest.items == ["0", "1", "2"]


def test_as_str_converts_dict_items(make_ctx):
    """Test that as_str turns fruit dicts into their string representation."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)

    forest, attrs, render_specs, out = qp.execute_query("fruits, limit 2, as_str")

    assert out == (
        "- {'id': 1, 'name': 'apple', 'calories': 52, 'color': 'red', 'ftype': 'fruit',"
        " 'tags': ['fruit', 'sweet', 'fresh']}\n"
        "- {'id': 2, 'name': 'orange', 'calories': 47, 'color': 'orange', 'ftype': 'fruit',"
        " 'tags': ['fruit', 'sweet', 'citrus']}"
    )
    assert all(isinstance(item, str) for item in forest.items)


def test_as_str_converts_nested_structure(make_ctx):
    """Test that as_str stringifies every element of a tree and keeps the shape."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)

    forest, attrs, render_specs, out = qp.execute_query("menu, extend_menu_fruits, as_str")

    assert out == (
        "- day-1\n"
        "  - {'name': 'apple', 'quantity': 1}\n"
        "- day-2\n"
        "  - {'name': 'orange', 'quantity': 1}\n"
        "- day-3\n"
        "  - {'name': 'apple', 'quantity': 2}\n"
        "  - {'name': 'orange', 'quantity': 1}\n"
        "- day-4\n"
        "  - {'name': 'apple', 'quantity': 1}\n"
        "  - {'name': 'grape', 'quantity': 1}\n"
        "  - {'name': 'mango', 'quantity': 1}"
    )
    assert forest.depths == [0, 1, 0, 1, 0, 1, 1, 0, 1, 1, 1]
    assert all(isinstance(item, str) for item in forest.items)


def test_as_str_on_depth_0_maps_only_top_level(make_ctx):
    """Test that as_str --on-depth=0 stringifies the parents and leaves the children."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)

    forest, attrs, render_specs, out = qp.execute_query("range 3, multiply 2, as_str --on-depth=0")

    assert out == "- 0\n  - 0\n- 1\n  - 2\n- 2\n  - 4"
    assert forest.items == ["0", 0, "1", 2, "2", 4]
    assert forest.depths == [0, 1, 0, 1, 0, 1]


def test_map_attr_basic(make_ctx):
    """Test that map_attr works with dict keys (similar to map_field)."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)

    # map_attr should work the same as map_field for dict keys
    forest, attrs, render_specs, out = qp.execute_query("fruits, map_attr name")

    lines = out.strip().split("\n")
    assert len(lines) == 10
    assert "- apple" in lines


def test_map_attr_nested_structures(make_ctx):
    """Test that map_attr works on nested structures, extracting dict keys at all depths."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)

    # Create nested structure with fruits, then extract name field
    # extend_menu_fruits creates nested dict items with 'name' key
    # Parent items are strings (day-1, etc.), children are dicts with 'name'
    # key
    forest, attrs, render_specs, out = qp.execute_query("menu, extend_menu_fruits, map_attr name")

    lines = out.strip().split("\n")

    # Parent items are strings, so getattr("day-1", "name", None) returns None
    # Child items are dicts with 'name' key, so dict.get("name") returns fruit names
    # Output should show None for parents and fruit names for children
    assert "apple" in out
    assert "orange" in out
    assert "grape" in out
    assert "mango" in out

    # Verify we have None values for parent items (strings don't have 'name'
    # attribute)
    depth_0_lines = [line for line in lines if not line.startswith(" ")]
    # Parent items at depth 0 should be None
    assert any("None" in line for line in depth_0_lines)


def test_map_attr_with_none_values(make_ctx):
    """Test that map_attr handles None values correctly."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)

    # Extract calories field - ambrosia has None calories
    forest, attrs, render_specs, out = qp.execute_query("fruits, map_attr calories")

    # Should include None value for ambrosia
    assert "- None" in out or "None" in out


def test_map_attr_nonexistent_key(make_ctx):
    """Test that map_attr returns None for nonexistent keys."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)

    # Extract nonexistent field
    forest, attrs, render_specs, out = qp.execute_query("fruits, map_attr nonexistent_field")

    lines = out.strip().split("\n")

    # All values should be None
    for line in lines:
        assert "None" in line or line.strip() == "- None"


def test_map_attr_preserves_nesting(make_ctx):
    """Test that map_attr preserves nested structure depth information."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)

    # Create nested structure and verify depth is preserved
    forest, attrs, render_specs, out = qp.execute_query("menu, extend_menu_fruits, map_attr name")

    lines = out.strip().split("\n")

    # Check that we have both depth 0 (parents) and depth 1 (children) items
    depth_0_lines = [line for line in lines if not line.startswith(" ")]
    depth_1_lines = [line for line in lines if line.startswith(" ")]

    # Should have both parents and children
    assert len(depth_0_lines) > 0
    assert len(depth_1_lines) > 0


def test_map_attr_udan_attribute_translate_ru(make_ctx):
    """Test that map_attr works with udan attributes like translate_ru."""
    # Extract translate_ru attribute from fruits
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("fruits, map_attr translate_ru")

    lines = out.strip().split("\n")

    # Should have 10 fruits with Russian translations
    assert len(lines) == 10

    # Check specific Russian translations
    assert "яблоко" in out  # apple
    assert "апельсин" in out  # orange
    assert "банан" in out  # banana
    assert "клубника" in out  # strawberry
    assert "манго" in out  # mango

    # ambrosia has no translation, should be None
    assert "- None" in out


def test_group_by_intervals_with_fruits_calories(make_ctx):
    """Test group_by_intervals with fruits by calories field."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)

    # Test grouping fruits by calories into intervals: (..40), [40..60), [60..)
    forest, attrs, render_specs, out = qp.execute_query("fruits, group_by_intervals calories 40 60")

    # Should have 3 groups plus None group for ambrosia
    assert "- (..40) ::" in out
    assert "- [40..60) ::" in out
    assert "- [60..) ::" in out
    assert "- None ::" in out

    lines = out.split("\n")

    # Group (..40) should contain strawberry (32 calories)
    group_start = next(i for i, line in enumerate(lines) if "(..40)" in line)
    group_section = "\n".join(lines[group_start : group_start + 10])
    assert "strawberry" in group_section

    # Group [40..60) should contain apple (52), orange (47), blueberry (57),
    # etc.
    group_start = next(i for i, line in enumerate(lines) if "[40..60)" in line)
    group_section = "\n".join(lines[group_start : group_start + 20])
    assert "apple" in group_section
    assert "orange" in group_section
    assert "blueberry" in group_section

    # Group [60..) should contain banana (89), grape (62), mango (60)
    group_start = next(i for i, line in enumerate(lines) if "[60..)" in line)
    group_section = "\n".join(lines[group_start : group_start + 20])
    assert "banana" in group_section
    assert "grape" in group_section
    assert "mango" in group_section

    # Group None should contain ambrosia (None calories)
    group_start = next(i for i, line in enumerate(lines) if "- None ::" in line)
    group_section = "\n".join(lines[group_start : group_start + 10])
    assert "ambrosia" in group_section


def test_group_by_intervals_with_fruits_calories_three_intervals(make_ctx):
    """Test group_by_intervals with fruits using three calorie intervals."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)

    # Test with intervals 10, 60: (..10), [10..60), [60..)
    forest, attrs, render_specs, out = qp.execute_query("fruits, group_by_intervals calories 10 60")

    # No fruits have calories < 10, so (..10) group should be empty or not shown
    # All fruits have calories >= 32, except ambrosia which has None
    assert "- [10..60) ::" in out
    assert "- [60..) ::" in out
    assert "- None ::" in out

    lines = out.split("\n")

    # Group [10..60) should have 6 fruits: apple, orange, strawberry,
    # blueberry, raspberry, pineapple
    group_start = next(i for i, line in enumerate(lines) if "[10..60)" in line)
    group_section = "\n".join(lines[group_start : group_start + 30])
    assert "apple" in group_section
    assert "orange" in group_section
    assert "strawberry" in group_section
    assert "blueberry" in group_section
    assert "raspberry" in group_section
    assert "pineapple" in group_section

    # Group [60..) should have 3 fruits: banana, grape, mango
    group_start = next(i for i, line in enumerate(lines) if "[60..)" in line)
    group_section = "\n".join(lines[group_start : group_start + 20])
    assert "banana" in group_section
    assert "grape" in group_section
    assert "mango" in group_section


def test_group_by_intervals_with_fruits_calories_single_boundary(make_ctx):
    """Test group_by_intervals with fruits using a single calorie boundary."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)

    # Test with single boundary 50: (..50), [50..)
    forest, attrs, render_specs, out = qp.execute_query("fruits, group_by_intervals calories 50")

    # Should have 2 groups plus None group
    assert "- (..50) ::" in out
    assert "- [50..) ::" in out
    assert "- None ::" in out

    lines = out.split("\n")

    # Group (..50) should have fruits with calories < 50
    group_start = next(i for i, line in enumerate(lines) if "- (..50) ::" in line)
    group_section = "\n".join(lines[group_start : group_start + 20])
    # strawberry (32), orange (47), pineapple (50 is not < 50)
    assert "strawberry" in group_section
    assert "orange" in group_section

    # Group [50..) should have fruits with calories >= 50
    group_start = next(i for i, line in enumerate(lines) if "- [50..) ::" in line)
    group_section = "\n".join(lines[group_start : group_start + 30])
    # pineapple (50), apple (52), raspberry (52), blueberry (57), grape (62), mango (60), banana (89)
    assert "pineapple" in group_section
    assert "apple" in group_section
    assert "grape" in group_section
    assert "banana" in group_section


def test_flat_children_basic(make_ctx):
    """Test basic flat_children functionality."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 1 3, multiply 2 3, flat_children, :list")

    expected = "[(1, 2), (1, 3), (2, 4), (2, 6)]"
    assert out == expected


def test_flat_children_single_child(make_ctx):
    """Test flat_children with single child per parent."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 3, multiply 2, flat_children, :list")

    expected = "[(0, 0), (1, 2), (2, 4)]"
    assert out == expected


def test_flat_children_alias_chains(make_ctx):
    """Test that chains alias works (from TASKS.md)."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 1 3, multiply 2 3, chains, :list")

    expected = "[(1, 2), (1, 3), (2, 4), (2, 6)]"
    assert out == expected


def test_flat_children_alias_zip_children(make_ctx):
    """Test that zip_children alias works."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 1 3, multiply 2 3, zip_children, :list")

    expected = "[(1, 2), (1, 3), (2, 4), (2, 6)]"
    assert out == expected


def test_grep_keeps_matching_items(make_ctx):
    """Test that grep (has_pattern) keeps items matching pattern."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("fruits, grep berry, :list")

    # Should contain fruits with "berry" in name
    assert "strawberry" in out
    assert "blueberry" in out
    # Should NOT contain "apple" or "orange"
    assert "apple" not in out
    assert "orange" not in out


def test_grepv_removes_matching_items(make_ctx):
    """Test that grepv (has_not_pattern) removes items matching pattern."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("fruits, grepv berry, :list")

    # Should contain fruits without "berry" in name
    assert "apple" in out
    assert "orange" in out
    # Should NOT contain berry items
    assert "strawberry" not in out
    assert "blueberry" not in out


def test_greps_and_logic_with_positive_patterns(make_ctx):
    """Test that greps keeps items matching ALL positive patterns."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    # Find fruits that have BOTH 'berry' AND 'blue' -> should only match
    # blueberry
    forest, attrs, render_specs, out = qp.execute_query("fruits, greps berry blue, :list")

    # Should contain only blueberry (has both 'berry' and 'blue')
    assert "blueberry" in out
    # Should NOT contain strawberry (has 'berry' but not 'blue')
    assert "strawberry" not in out
    # Should NOT contain raspberry (has 'berry' but not 'blue')
    assert "raspberry" not in out
    # Should NOT contain apple or orange (don't have 'berry')
    assert "apple" not in out
    assert "orange" not in out


def test_greps_with_negative_pattern(make_ctx):
    """Test that greps with negative pattern removes items matching that pattern."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    # Find fruits that have 'berry' but NOT 'blue' -> should match strawberry,
    # raspberry
    forest, attrs, render_specs, out = qp.execute_query("fruits, greps berry -blue, :list")

    # Should contain strawberry and raspberry (have 'berry' but not 'blue')
    assert "strawberry" in out
    assert "raspberry" in out
    # Should NOT contain blueberry (has 'blue')
    assert "blueberry" not in out


def test_greps_only_negative_patterns(make_ctx):
    """Test that greps with only negative patterns removes all matching items."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    # Remove all fruits with 'berry' or 'apple'
    forest, attrs, render_specs, out = qp.execute_query("fruits, greps -berry -apple, :list")

    # Should contain orange, banana, mango, grape, pineapple, ambrosia
    assert "orange" in out
    assert "banana" in out
    assert "mango" in out
    # Should NOT contain berry items or apple
    assert "strawberry" not in out
    assert "blueberry" not in out
    assert "raspberry" not in out
    assert "apple" not in out


def test_greps_complex_condition(make_ctx):
    """Test that greps handles complex AND conditions."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    # Find fruits with 'an' but NOT 'le' -> should match banana, mango, orange
    forest, attrs, render_specs, out = qp.execute_query("fruits, greps an -le, :list")

    # Should contain banana, mango, orange (have 'an' but not 'le')
    assert "banana" in out
    assert "mango" in out
    assert "orange" in out
    # Should NOT contain apple (has 'le')
    assert "apple" not in out
    # Should NOT contain pineapple (has 'le')
    assert "pineapple" not in out


def test_raiser():
    """Test that raiser inserter raises an exception."""
    # Should raise RuntimeError
    try:
        raiser()
        assert False, "raiser should have raised RuntimeError"
    except RuntimeError as e:
        assert "Test exception from raiser inserter" in str(e)


_FRUIT_NAMES = {
    "apple",
    "orange",
    "banana",
    "strawberry",
    "blueberry",
    "raspberry",
    "grape",
    "pineapple",
    "mango",
    "ambrosia",
}

_BERRY_NAMES = {"strawberry", "blueberry", "raspberry"}


def test_extend_by_inserter_uses_inserter_defaults(make_ctx):
    """With no passthrough args the root gets the inserter's full default output."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    forest, _attrs, _render_specs, _out = qp.execute_query("self_insert one-root, extend_by_inserter fruits")

    pairs = list(forest.as_pairs())
    top_items = [item for depth, item in pairs if depth == 0]
    children = [item for depth, item in pairs if depth == 1]

    assert top_items == ["one-root"]  # single root: the defaults test has nothing to repeat over
    assert {child["name"] for child in children} == _FRUIT_NAMES


def test_extend_by_inserter_gives_each_item_its_own_children(make_ctx):
    """$field binding derives each root's children from that root, not the same set for all."""
    ctx = make_ctx(plugins_demo, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    _forest, _attrs, _render_specs, out = qp.execute_query(
        "range 4, extend_by_inserter 'demo.range' 'a=0' 'b=$item', :list"
    )

    # item k is extended with range(0, k): item 0 gets nothing, item 3 gets [0, 1, 2]
    assert out == "[0, 1, [0], 2, [0], [1], 3, [0], [1], [2]]"


def test_extend_by_inserter_binds_named_passthrough_arg(make_ctx):
    """'key=value' entries bind the inner inserter's named parameter."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    forest, _attrs, _render_specs, _out = qp.execute_query(
        "self_insert one-root, extend_by_inserter 'fruits' 'pattern=berry'"
    )

    children = [item for depth, item in forest.as_pairs() if depth == 1]
    names = {child["name"] for child in children}

    assert names == _BERRY_NAMES


def test_extend_by_inserter_binds_positional_passthrough_arg(make_ctx):
    """An entry without '=' feeds the first unbound parameter, $item substituted like named values."""
    ctx = make_ctx(plugins_demo, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    _forest, _attrs, _render_specs, out = qp.execute_query("range 3, extend_by_inserter 'demo.range' '$item', :list")

    # item 0 -> range(0) is empty, item 1 -> [0], item 2 -> [0, 1]
    assert out == "[0, 1, [0], 2, [0], [1]]"


def test_extend_by_inserter_substitutes_item_fields(make_ctx):
    """$field tokens in a passthrough value are replaced by the item's field."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    forest, _attrs, _render_specs, _out = qp.execute_query("fruits, extend_by_inserter 'self_insert' 'arg=$name'")

    children = [item for depth, item in forest.as_pairs() if depth == 1]

    assert sorted(children) == sorted(_FRUIT_NAMES)  # one string child per fruit, its own name


def test_extend_by_inserter_resolves_domain_qualified_name(make_ctx):
    """A 'domain.name' inserter name resolves to the registered bare name."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    forest, _attrs, _render_specs, _out = qp.execute_query(
        "self_insert one-root, extend_by_inserter 'fruits.insert_fruits' 'pattern=berry'"
    )

    children = [item for depth, item in forest.as_pairs() if depth == 1]
    names = {child["name"] for child in children}

    assert names == _BERRY_NAMES


def test_extend_by_inserter_rejects_unknown_parameter(make_ctx):
    """A 'key=value' entry naming no parameter of the inserter fails with advice."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    _forest, _attrs, _render_specs, out = qp.execute_query("menu, extend_by_inserter 'fruits' 'nope=1'")

    assert "has no parameter 'nope'" in out


def test_extend_by_inserter_rejects_missing_item_field(make_ctx):
    """A $field naming no field of the item fails with advice."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    _forest, _attrs, _render_specs, out = qp.execute_query("menu, extend_by_inserter 'fruits' 'pattern=$nonexistent'")

    assert "names no field of the item" in out


def test_extend_by_inserter_rejects_non_inserter(make_ctx):
    """A non-inserter tool name fails with advice."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    _forest, _attrs, _render_specs, out = qp.execute_query("menu, extend_by_inserter 'is_even'")

    assert "is a attribute, not an inserter" in out


def test_extend_by_inserter_rejects_missing_name(make_ctx):
    """An inserter name is required."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    # An empty string entry reports the missing name
    _forest, _attrs, _render_specs, out = qp.execute_query("menu, extend_by_inserter ''")

    assert "inserter name must be a non-empty string" in out
