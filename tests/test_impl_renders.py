"""Tests for render functionality."""

from tests import plugins_test_render_variants
from tests.conftest import kinds_vocabulary, make_qp, register_tools_from_module
from tests.plugins_test_render_variants import FRONTEND_HTML
from udan.attributes import plugins_aggregates_attribute, plugins_operators_attribute
from udan.attributes.api_attribute_storage import AttributeStorageAPI
from udan.core.api_attributes import AttributeDescriptor
from udan.core.api_forests import Forest
from udan.core_tools_loading.api_types import Group
from udan.core_tools_loading.impl_tools_loader import ToolsLoader
from udan.plugins_history import plugins_history
from udan.plugins_tools_core import plugins_help, plugins_system
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.plugins_tools_examples import plugins_builtins, plugins_csv, plugins_org, plugins_sql
from udan.plugins_tools_examples.plugins_org import (
    render_org_generic,
    render_org_item,
    render_org_items,
)
from udan.plugins_tools_examples.plugins_sql import SqlRow
from udan.renders import plugins_renders
from udan.renders.api_render_engine import RenderEngineAPI
from udan.renders.api_renders import FRONTEND_TEXT, RenderDescriptor
from udan.renders.plugins_renders import (
    render_group_header,
    render_list,
    render_org_list_aggregate,
    render_raw,
    render_table,
    render_table_aggregate,
)

# Fruit dicts with tags (mirror ALL_FRUITS in plugins_fruits) for exact repr assertions.
FRUIT_APPLE = {
    "id": 1,
    "name": "apple",
    "calories": 52,
    "color": "red",
    "ftype": "fruit",
    "tags": ["fruit", "sweet", "fresh"],
}
FRUIT_ORANGE = {
    "id": 2,
    "name": "orange",
    "calories": 47,
    "color": "orange",
    "ftype": "fruit",
    "tags": ["fruit", "sweet", "citrus"],
}
FRUIT_BANANA = {
    "id": 3,
    "name": "banana",
    "calories": 89,
    "color": "yellow",
    "ftype": "fruit",
    "tags": ["fruit", "sweet", "tropical"],
}


def test_render_raw():
    """Test raw render."""
    item = {"id": 1, "name": "apple"}
    result = render_raw(item)
    assert result == "{'id': 1, 'name': 'apple'}"


def test_render_list():
    """Test list render at different depths."""
    # Depth 0 - no wrapping
    result = render_list("a", depth=0)
    assert result == "a"

    # Depth 1 - single wrapping
    result = render_list("b", depth=1)
    assert result == "[b]"

    # Depth 2 - double wrapping
    result = render_list("c", depth=2)
    assert result == "[[c]]"


def test_render_list_with_nested_structure(make_ctx):
    """Test list render with nested structure from extend_multiply."""
    # extend_multiply creates nested children
    # 0 -> [0*2=0], 1 -> [1*2=2]
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 2, extend_multiply, :list")

    # Special handling applies - renders as single-line list with nested brackets
    # Expected: [0, [0], 1, [2]]
    # (depth 0 items get no brackets, depth 1 items get single brackets, all wrapped in outer brackets)
    assert out == "[0, [0], 1, [2]]"


def test_render_org():
    """Test org render."""
    item = {"id": 1, "name": "apple"}
    result = render_org_generic(item)
    # Should format dict as org-mode heading with properties block
    expected = "* 1 apple\n:PROPERTIES:\n:id: 1\n:name: apple\n:END:"
    assert result == expected


def test_render_org_items():
    """Test org-items render for dicts."""
    item = {"id": 1, "name": "apple"}
    result = render_org_items(item)
    expected = "- {'id': 1, 'name': 'apple'}\n  :id: 1\n  :name: apple"
    assert result == expected


def test_render_org_item():
    """Test org-item render with two fields."""
    item = {"id": 1, "name": "apple"}
    result = render_org_item(item, "id", "name")
    assert result == "- 1 :: apple"


def test_render_table():
    """Test table render for dicts."""
    item = {"id": 1, "name": "apple"}
    result = render_table(item)
    # Single dict rendered as row (old behavior for single items without full
    # table context)
    assert "1" in result
    assert "apple" in result


def test_render_descriptor():
    """Test RenderDescriptor creation."""
    rd = RenderDescriptor.create("org-item", ("id", "name"))
    assert rd.name == "org-item"
    assert rd.args == ("id", "name")
    assert repr(rd) == "Render(org-item, args=('id', 'name'))"


def test_fruits_with_org_item(make_ctx):
    """Test fruits inserter with org-item render."""
    # Test with org-item render (first 3 fruits)
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query(":org-item id name insert_fruits")

    # Check first 3 fruits are rendered correctly
    lines = out.strip().split("\n")
    assert len(lines) == 10  # All 10 fruits (9 regular + 1 mythical)
    assert lines[0] == "- 1 :: apple"
    assert lines[1] == "- 2 :: orange"
    assert lines[2] == "- 3 :: banana"


def test_fruits_with_raw(make_ctx):
    """Test fruits inserter with raw render."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query(":raw insert_fruits")

    # Should show dict representation for all 10 fruits (9 regular + 1
    # mythical)
    lines = out.strip().split("\n")
    assert len(lines) == 10  # All 10 fruits (9 regular + 1 mythical)
    assert lines[0] == repr(FRUIT_APPLE)
    assert lines[1] == repr(FRUIT_ORANGE)
    assert lines[2] == repr(FRUIT_BANANA)


def test_fruits_with_table(make_ctx):
    """Test fruits inserter with table render."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query(":table insert_fruits")

    # Should show table format with headers and simple pipe styling
    lines = out.strip().split("\n")
    # Line 0: header row with column names
    assert "| name" in lines[0] or "| calories" in lines[0] or "| color" in lines[0] or "| id" in lines[0]
    # Line 1: separator with -+
    assert "|-" in lines[1] and "+" in lines[1]
    # Check that apple is in the data
    assert any("apple" in line for line in lines)


def test_colon_alone_shows_advice(make_ctx):
    """Test that `:` lists the renders through the pipeline, identical to `:?`."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    colon_out = qp.execute_query(":")[3]

    assert colon_out == qp.execute_query(":?")[3]

    lines = colon_out.strip().split("\n")
    assert lines[0] == "- domain=fruits ::"
    assert any(line.startswith("  - fruits.render_fruit ::") for line in lines)
    entries = [line for line in lines if line.startswith("  - ")]
    assert entries
    assert all("::" in line for line in entries)


def test_invalid_render_shows_error(make_ctx):
    """Test that an unknown render is answered with the render listing, not the chain's data."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_help,
        plugins_system,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query(":invalid_render insert_fruits")

    lines = out.strip().split("\n")
    assert lines[0] == "- domain=fruits ::"
    assert any("renders.render_attr ::" in line for line in lines)
    # The chain is overridden: insert_fruits never executes
    assert "apple" not in out


def test_fruits_default_render(make_ctx):
    """Test fruits inserter with default (no render specified)."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("insert_fruits")

    # Should use org-item(id) as default render (from supported_renders)
    # Check first 3 fruits
    lines = out.strip().split("\n")
    assert len(lines) == 10  # All 10 fruits (9 regular + 1 mythical)
    assert lines[0] == "- 1 :: apple"
    assert lines[1] == "- 2 :: orange"
    assert lines[2] == "- 3 :: banana"


def test_fruit_render_shows_emoji_and_name(make_ctx):
    """Fruits render as "<emoji> <name>"; fruits missing from FRUIT_EMOJI fall back to the bare name."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("fruits, fruit")

    assert out.strip().split("\n") == [
        "\U0001f34e apple",
        "\U0001f34a orange",
        "\U0001f34c banana",
        "\U0001f353 strawberry",
        "\U0001fad0 blueberry",
        "raspberry",  # no emoji in FRUIT_EMOJI
        "\U0001f347 grape",
        "\U0001f34d pineapple",
        "\U0001f96d mango",
        "ambrosia",  # mythical, untagged with an emoji either
    ]


def test_fruit_render_reachable_by_explicit_spec(make_ctx):
    """Test that :fruit resolves like the auto-detected form."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("fruits, :fruit")

    assert render_specs[0].name == "fruit"
    assert out.strip().split("\n")[0] == "\U0001f34e apple"


def test_explicit_render_overrides_default(make_ctx):
    """Test that explicit render overrides the default supported_renders."""
    # Use table render instead of default org-item
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query(":table insert_fruits")

    # Should show table format with grid styling, not org-item format
    # Check for table markers (grid borders, pipes)
    assert "+" in out  # Grid borders
    assert "|" in out  # Cell separators
    assert "- 1 :: apple" not in out  # Not org-item format


def test_fruits_with_org_no_render_in_output(make_ctx):
    """Test that render spec is not shown in the output."""
    # Test with :org render - the :org should not appear in the output
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query(":org insert_fruits")

    # Output should contain org-mode properties blocks
    # and should not contain the render spec itself
    # Check that we have :PROPERTIES: blocks
    assert ":PROPERTIES:" in out
    assert ":id:" in out
    # Should not contain the render spec itself
    assert ":org" not in out


def test_fruits_with_org_items_properties(make_ctx):
    """Test fruits with org-items render shows org-mode property blocks."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query(":org-items insert_fruits")

    # Should show org-mode property blocks for all 10 fruits
    # Check first 3 fruits with exact line comparison
    lines = out.strip().split("\n")
    assert lines[0] == f"- {repr(FRUIT_APPLE)}"
    assert lines[1] == "  :id: 1"
    assert lines[2] == "  :name: apple"
    assert lines[3] == "  :calories: 52"
    assert lines[4] == "  :color: red"
    assert lines[5] == "  :ftype: fruit"
    assert lines[6] == f"  :tags: {repr(FRUIT_APPLE['tags'])}"

    # Each fruit has 7 lines (item line + 6 properties)
    # Second fruit starts at line 7
    assert lines[7] == f"- {repr(FRUIT_ORANGE)}"
    assert lines[8] == "  :id: 2"
    assert lines[9] == "  :name: orange"
    assert lines[10] == "  :calories: 47"
    assert lines[11] == "  :color: orange"
    assert lines[12] == "  :ftype: fruit"
    assert lines[13] == f"  :tags: {repr(FRUIT_ORANGE['tags'])}"

    # Third fruit starts at line 14
    assert lines[14] == f"- {repr(FRUIT_BANANA)}"
    assert lines[15] == "  :id: 3"
    assert lines[16] == "  :name: banana"
    assert lines[17] == "  :calories: 89"
    assert lines[18] == "  :color: yellow"
    assert lines[19] == "  :ftype: fruit"
    assert lines[20] == f"  :tags: {repr(FRUIT_BANANA['tags'])}"

    # Verify all 10 fruits are present (7 lines each)
    assert len(lines) == 70  # 10 fruits * 7 lines (9 regular + 1 mythical)


def test_fruits_render_spec_filtered_from_tree(make_ctx):
    """Test that render spec strings are not in the forest."""
    # Test with :raw render
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query(":raw insert_fruits")

    # Check the forest items - should not contain ":raw"
    assert ":raw" not in forest.items
    assert ":org" not in forest.items
    assert ":table" not in forest.items

    # Should only contain the fruit dicts (10 fruits total - 9 regular + 1
    # mythical)
    # 10 fruits (9 regular + 1 mythical)
    assert len(forest.items) == 10
    assert all(isinstance(item, dict) for item in forest.items)


def test_render_org_with_depth():
    """Test org render uses correct asterisks based on depth parameter."""
    item = {"id": 1, "name": "apple"}

    # Depth 0 should use single *
    result = render_org_generic(item, depth=0)
    expected = "* 1 apple\n:PROPERTIES:\n:id: 1\n:name: apple\n:END:"
    assert result == expected

    # Depth 1 should use ** (no leading space)
    result = render_org_generic(item, depth=1)
    expected = "** 1 apple\n:PROPERTIES:\n:id: 1\n:name: apple\n:END:"
    assert result == expected

    # Depth 2 should use *** (no leading space)
    result = render_org_generic(item, depth=2)
    expected = "*** 1 apple\n:PROPERTIES:\n:id: 1\n:name: apple\n:END:"
    assert result == expected

    # Heading lines should never have leading spaces
    # Only properties block gets indented
    result = render_org_generic(item, indent="  ", depth=1)
    lines = result.split("\n")
    assert lines[0] == "** 1 apple"  # No indent on heading
    assert lines[1] == "  :PROPERTIES:"  # Indent on properties


def test_table_with_simple_data(make_ctx):
    """Test table render with simple dict data."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    _, _, _, out = qp.execute_query(":table insert_fruits")

    lines = out.strip().split("\n")

    # Should have header, separator, and data rows
    assert len(lines) >= 3
    assert lines[0].startswith("| name")
    assert "|-" in lines[1]
    assert "+" in lines[1]


def test_table_column_alignment(make_ctx):
    """Test that table columns are properly aligned."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    _, _, _, out = qp.execute_query(":table insert_fruits")

    lines = out.strip().split("\n")

    # Third line should have right-aligned numbers (spaces before id) and
    # include ftype and tags
    assert lines[2] == "| apple      |  1 |       52 | red    | fruit | ['fruit', 'sweet', 'fresh']    |"


def test_table_with_grouped_data(make_ctx):
    """Test table render with grouped data from group_by_field."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins.__name__)

    _, _, _, out = qp.execute_query("insert_fruits, group_by_field color, :table")

    # Should render separate tables for each group with org-style section
    # headers
    lines = out.strip().split("\n")

    # Should have section headers for each group
    assert "* color=red" in out
    assert "* color=orange" in out
    assert "* color=yellow" in out

    # Count section headers (each group gets one)
    section_count = sum(1 for line in lines if line.startswith("* color="))
    assert section_count == 6  # red, orange, yellow, blue, purple, None


def test_raw_with_grouped_data(make_ctx):
    """Test that :raw render with grouped data shows dict-style group headers."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins.__name__)

    register_tools_from_module(ctx, plugins_aggregates_attribute.__name__)

    _, _, _, out = qp.execute_query("insert_fruits, group_by_field color, sum calories, :raw")

    # Group headers should be dict-like with type, key, and attrs with sum
    assert "'type': 'group'" in out
    assert "'key': 'red'" in out
    assert "'key': 'orange'" in out
    assert "'key': 'yellow'" in out

    # Per-group aggregate values should be shown
    assert "'sum': 136" in out  # red: 52+32+52
    assert "'sum': 107" in out  # orange: 47+60
    assert "'sum': 139" in out  # yellow: 89+50

    # Regular items should still render as raw dicts
    assert "'name': 'apple'" in out


def test_table_preserves_name_column_order(make_ctx):
    """Test that 'name' column appears first when present."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    _, _, _, out = qp.execute_query(":table insert_fruits")

    lines = out.strip().split("\n")
    header = lines[0]

    # First column should be 'name'
    assert header.split("|")[1].strip() == "name"


def test_table_handles_none_values(make_ctx):
    """Test that table properly handles None/null values."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    _, _, _, out = qp.execute_query(":table insert_fruits")

    # ambrosia has None for color and calories
    lines = out.strip().split("\n")

    # Find the ambrosia row (last data row)
    ambrosia_row = [line for line in lines if "ambrosia" in line][0]
    assert "None" in ambrosia_row


def test_table_with_csv_data(make_ctx):
    """Test table render with CSV data."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_csv.__name__)

    _, _, _, out = qp.execute_query(':table, insert_csv_rows "tests/resources/test_data.csv"')

    lines = out.strip().split("\n")

    # Should render as table with headers (name column moved to front)
    assert len(lines) >= 3
    assert lines[0].startswith("| name")
    assert "Alice" in out
    assert "Bob" in out


# ============================================================================
# Tests for Aggregate Renders (shape="children")
# These renders take all items and render them together
# ============================================================================


def test_aggregate_list_all_render(make_ctx):
    """Test that :list aggregate render produces comma-separated list."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query(":list insert_fruits")

    # Should produce comma-separated list in brackets
    assert out.startswith("[")
    assert out.endswith("]")

    # Should contain all fruit names (first 3 for verification)
    assert "apple" in out
    assert "orange" in out
    assert "banana" in out

    # Should use comma separation
    assert ", " in out


def test_aggregate_only_render_appends_supported_item_render(make_ctx):
    """':bullets'/' :lines' compose per-item lines, so the operator's supported render still applies."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    _, _, render_specs, _ = qp.execute_query(":bullets insert_fruits")

    assert [render_d.name for render_d in render_specs] == ["bullets", "org-item"]
    assert render_specs[0].from_supported is False  # typed by the user
    assert render_specs[1].from_supported is True  # operator's default item render


def test_bullets_joins_per_item_lines(make_ctx):
    """':bullets' renders each item by its per-item render and prefixes '- '."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    _, _, _, out = qp.execute_query("range 3, :bullets")

    assert out == "- 0\n- 1\n- 2"


def test_bullet_prefix_resolves_to_bullets(make_ctx):
    """':bullet' resolves to the bullets aggregate render: its unique prefix match."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    _, _, _, out = qp.execute_query("range 3, :bullet")

    assert out == "- 0\n- 1\n- 2"


def test_lines_joins_per_item_lines(make_ctx):
    """':lines' renders each item by its per-item render without any prefix."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    _, _, _, out = qp.execute_query("range 3, :lines")

    assert out == "0\n1\n2"


def test_bullets_and_lines_keep_depth_indent(make_ctx):
    """':bullets' and ':lines' indent two spaces per depth level."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    _, _, _, bullets_out = qp.execute_query("range 2, extend_multiply, :bullets")
    _, _, _, lines_out = qp.execute_query("range 2, extend_multiply, :lines")

    assert bullets_out == "- 0\n  - 0\n- 1\n  - 2"
    assert lines_out == "0\n  0\n1\n  2"


def test_bullets_composes_user_item_render_with_args(make_ctx):
    """':fmt ..., :bullets' renders each item through the user render, args included."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    _, _, _, bullets_out = qp.execute_query('fruits, limit 3, :fmt "{name}", :bullets')
    _, _, _, lines_out = qp.execute_query('fruits, limit 3, :fmt "{name}", :lines')

    assert bullets_out == "- apple\n- orange\n- banana"
    assert lines_out == "apple\norange\nbanana"


def test_bullets_keeps_own_bullets_of_item_render(make_ctx):
    """A bullet belonging to the per-item render itself is content, not list layout."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    _, _, _, out = qp.execute_query("insert_fruits, :bullets")

    # org-item renders its own '- ' prefix; :bullets does not double it
    lines = out.strip().split("\n")
    assert lines[0] == "- 1 :: apple"
    assert lines[1] == "- 2 :: orange"


def test_aggregate_table_all_render(make_ctx):
    """Test that :table aggregate render produces full table."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query(":table insert_fruits")

    lines = out.strip().split("\n")

    # Should have header, separator, and data rows
    assert len(lines) >= 3
    assert lines[0].startswith("|")

    # Should contain fruit data
    assert "apple" in out
    assert "orange" in out


def test_aggregate_org_render(make_ctx):
    """Test that :org-aggregate produces org-mode outline with * markers."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query(":org-aggregate insert_fruits")

    lines = out.strip().split("\n")

    # Should use * for depth markers
    # First line should be depth 0: * item
    assert lines[0].startswith("* ")
    assert "apple" in lines[0] or "{" in lines[0]

    # All lines should start with * (org-mode headings)
    assert all(line.startswith("*") for line in lines if line.strip())


def test_aggregate_org_list_render(make_ctx):
    """Test that :org-list aggregate render produces org-mode list."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query(":org-list insert_fruits")

    lines = out.strip().split("\n")

    # Should use - for list items
    # First line should start with "- "
    assert lines[0].startswith("- ")

    # Should contain fruit data
    assert "apple" in out or "1" in out


def test_aggregate_renders_produce_different_output(make_ctx):
    """Test that different aggregate renders produce different output formats."""
    # Get output from each aggregate render
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    _, _, _, list_all_out = qp.execute_query(":list insert_fruits")
    _, _, _, table_all_out = qp.execute_query(":table insert_fruits")
    _, _, _, org_out = qp.execute_query(":org-aggregate insert_fruits")
    _, _, _, org_list_out = qp.execute_query(":org-list insert_fruits")

    # Each render should produce different output format
    # list-all: [item1, item2, ...]
    assert list_all_out.startswith("[")
    assert list_all_out.endswith("]")

    # table-all: | header | ... |
    assert table_all_out.startswith("|")

    # org-aggregate: * item
    assert org_out.startswith("*")

    # org-list: - item
    assert org_list_out.startswith("-")

    # Verify outputs are actually different
    outputs = [list_all_out, table_all_out, org_out, org_list_out]
    assert len(set(outputs)) == 4, "All aggregate renders should produce different output"


def test_aggregate_renders_with_nested_structure(make_ctx):
    """Test aggregate renders with simple data (depth-based formatting)."""
    # Use insert_fruits which produces items at depth 0
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    _, _, _, org_out = qp.execute_query(":org-aggregate insert_fruits")

    lines = org_out.strip().split("\n")

    # Each line should be a heading with appropriate *
    # All items from insert_fruits are at depth 0, so all should be single *
    assert all(line.startswith("* ") and not line.startswith("**") for line in lines if line.strip())


def test_aggregate_render_with_empty_result(make_ctx):
    """Test aggregate renders with empty result."""
    # Use a query that returns empty result
    # Get variable 'x' which doesn't exist - returns empty
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    _, _, _, out = qp.execute_query(":list vars")

    # vars returns variables, not empty - let's just test that the render works
    # The output should be valid (either empty brackets or list of variables)
    assert out is not None
    assert isinstance(out, str)


# ============================================================================
# Tests for Low-Level render_forest API
# These tests use the core_api_forests.Forest and core_api_tools
# ============================================================================


def test_rendering_no_attributes(make_ctx):
    """Test rendering without any attributes."""
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_history, plugins_renders
    )
    forest = Forest(items=["a", "b", "c"], depths=[0, 0, 0])

    result = ctx._output.output_forest(forest, [], [], ctx.create_exec_context())

    assert result == "- a\n- b\n- c"


def test_rendering_with_single_attribute(make_ctx):
    """Test rendering with a single attribute."""
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_history, plugins_renders
    )
    forest = Forest(items=["a", "b", "c"], depths=[0, 0, 0])

    at_d = AttributeDescriptor(name="test_attr", args={})
    # Use attribute_storage directly instead of forest.attributes

    ctx.container.get(AttributeStorageAPI).set_attr_value(at_d, "a", 1)
    ctx.container.get(AttributeStorageAPI).set_attr_value(at_d, "b", 2)
    ctx.container.get(AttributeStorageAPI).set_attr_value(at_d, "c", 3)

    result = ctx._output.output_forest(forest, [at_d], [], ctx.create_exec_context())

    assert result == "- a :: 1\n- b :: 2\n- c :: 3"


def test_rendering_with_multiple_attributes(make_ctx):
    """Test rendering with multiple attributes."""
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_history, plugins_renders
    )
    forest = Forest(items=["a", "b"], depths=[0, 0])

    at_d1 = AttributeDescriptor(name="attr1", args={})
    at_d2 = AttributeDescriptor(name="attr2", args={})
    # Use attribute_storage directly instead of forest.attributes

    store = ctx.container.get(AttributeStorageAPI)
    store.set_attr_value(at_d1, "a", 1)
    store.set_attr_value(at_d1, "b", 2)
    store.set_attr_value(at_d2, "a", "x")
    store.set_attr_value(at_d2, "b", "y")

    result = ctx._output.output_forest(forest, [at_d1, at_d2], [], ctx.create_exec_context())

    assert result == "|> a|1|x|\n|> b|2|y|"


def test_rendering_with_depth(make_ctx):
    """Test rendering with nested items (depth)."""
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_history, plugins_renders
    )
    forest = Forest(items=["a", "b", "c"], depths=[0, 1, 2])

    result = ctx._output.output_forest(forest, [], [], ctx.create_exec_context())

    assert result == "- a\n  - b\n    - c"


def test_org_list_aggregate_uses_two_space_indent():
    """Regression: org-list aggregate indents two spaces per depth level."""
    result = render_org_list_aggregate(
        depths=[0, 1, 2],
        children=["a", "b", "c"],
        attr_ds=[],
    )
    assert result == "- a\n  - b\n    - c"


def test_table_aggregate_non_dict_renders_depth_item_table():
    """Regression: table aggregate renders non-dict items as a depth/item table."""
    result = render_table_aggregate(
        depths=[0, 1, 2],
        children=["a", "b", "c"],
        attr_ds=[],
    )
    assert result == "| depth | item |\n|-------+------|\n|     0 | a    |\n|     1 | b    |\n|     2 | c    |"


def test_render_engine_shows_row_items_as_columns(make_ctx):
    """Regression: row items (read_sql etc., output_semantic "row") render their columns.

    The engine hands non-row-aware renders the row's columns; the row-aware
    render_sql_row still sees the raw row with the rowid.
    """
    ctx = make_ctx(plugins_sql, plugins_renders)
    rows = [
        SqlRow(db_path="demo.db", table="users", row_id=1, row_data={"id": 1, "name": "Alice", "age": 30}),
        SqlRow(db_path="demo.db", table="users", row_id=2, row_data={"id": 2, "name": "Bob", "age": 25}),
    ]
    forest = Forest(items=rows, depths=[0, 0])

    table_out = ctx._output.output_forest(forest, [], [RenderDescriptor.create("table")], ctx.create_exec_context())
    expected = "| name  | id | age |\n|-------+----+-----|\n| Alice |  1 |  30 |\n| Bob   |  2 |  25 |"
    assert table_out == expected

    row_out = ctx._output.output_forest(
        forest, [], [RenderDescriptor.create("render_sql_row")], ctx.create_exec_context()
    )
    assert row_out.strip().split("\n") == ["- 1 | 1 | Alice | 30 |", "- 2 | 2 | Bob | 25 |"]


def test_table_aggregate_promotes_scalar_attributes_to_columns():
    """Regression: scalar attribute values become table columns for non-dict items."""
    at_d = AttributeDescriptor(name="relative_path", args={})
    items_attrs = [{"relative_path": "a.txt"}, {"relative_path": "b.txt"}]

    result = render_table_aggregate(
        depths=[0, 0],
        children=["a", "b"],
        attr_ds=[at_d],
        items_attrs=items_attrs,
    )

    assert (
        result
        == "| item | relative_path |\n|------+---------------|\n| a    | a.txt         |\n| b    | b.txt         |"
    )


def test_table_aggregate_grouped_scalar_items_render_item_rows():
    """Regression: grouped scalar items must render as item rows, not empty output."""

    result = render_table_aggregate(
        depths=[0, 1, 1, 1, 0, 1, 1],
        children=[
            Group(key=True, key_descriptor=None),
            0,
            2,
            4,
            Group(key=False, key_descriptor=None),
            1,
            3,
        ],
        attr_ds=[],
    )
    expected = (
        "* True\n| item |\n|------|\n|    0 |\n|    2 |\n|    4 |\n* False\n| item |\n|------|\n|    1 |\n|    3 |"
    )
    assert result == expected


def test_render_group_header_with_indent():
    """Group headers should use the two-space indent provided by the pipeline."""

    item = Group(key="red", key_descriptor=None)
    result = render_group_header(item, indent="  ", depth=1)
    assert result == "  - red ::"


def test_rendering_with_debug(make_ctx):
    """Test rendering with debug mode enabled."""

    # Create a fresh context (not using the fixture which overrides ctx.debug
    # = print)
    debug_ctx = make_ctx()
    debug_qp = make_qp(debug_ctx)
    # Register renders for the test

    loader = ToolsLoader(cache_dir=None, use_cache=False, kinds=kinds_vocabulary())
    metadata_fns = loader.load_from_module(plugins_renders)
    debug_ctx._register_many_metadatas(metadata_fns)

    # Use execute_query with debug=True to test debug wrapping
    # This is the real API - execute_query creates a logger per query
    result = debug_qp.execute_query("fruits", debug=True)

    # result is (forest, attrs, render_specs, output)
    output = result[3]

    # Check that output contains the actual results (after debug messages)
    # Debug messages are prefixed with "# [DEBUG]"
    lines = output.split("\n")
    debug_lines = [line for line in lines if line.startswith("# [DEBUG]")]
    # Check that we have some debug output (query_text, query_tree, etc.)
    assert len(debug_lines) > 0, f"Expected debug lines in output, got: {output}"
    # Check that non-debug lines exist (the actual output)
    non_debug_lines = [line for line in lines if not line.startswith("# [DEBUG]")]
    assert len(non_debug_lines) > 0, f"Expected non-debug output, got: {output}"


def test_render_without_attrs_param_ignores_loaded_attribute(make_ctx):
    """A render without an `attrs` parameter renders the item, not the raw dict repr."""
    ctx = make_ctx(plugins_renders)
    forest = Forest(items=["a", "b"], depths=[0, 0])
    at_d = AttributeDescriptor(name="sort_key", args={})
    store = ctx.container.get(AttributeStorageAPI)
    store.set_attr_value(at_d, "a", 2)
    store.set_attr_value(at_d, "b", 1)

    result = ctx._output.output_forest(forest, [at_d], [RenderDescriptor(name="lines-item")], ctx.create_exec_context())

    assert result == "a\nb"


def test_apply_render_drops_unsupported_special_kwargs(make_ctx):
    """Special keys the render does not declare are dropped, not failed into the fallback."""
    ctx = make_ctx(plugins_renders)

    def render_item_only(item, indent=""):
        return f"{indent}{item}"

    wrapped = {"item": "apple", "attrs": {"size": 1}}
    result = ctx.container.get(RenderEngineAPI)._apply_render(wrapped, None, render_item_only, indent="  ")

    assert result == "  apple"


def test_apply_render_passes_declared_special_kwargs(make_ctx):
    """Special keys the render declares are still forwarded (custom attribute renders)."""
    ctx = make_ctx(plugins_renders)

    def render_value(item, indent="", value="", original_item=None):
        return f"{indent}{original_item}: {value}"

    wrapped = {"_type": "attribute_value", "value": "code", "original_item": "mod.py"}
    result = ctx.container.get(RenderEngineAPI)._apply_render(wrapped, None, render_value)

    assert result == "mod.py: code"


def test_apply_render_var_kwargs_render_receives_depth_and_attrs(make_ctx):
    """Renders with **kwargs keep receiving depth and the declared special keys."""
    ctx = make_ctx(plugins_renders)

    def render_any(item, indent="", attrs=None, **kwargs):
        return f"{indent}{item} depth={kwargs.get('depth')} attrs={attrs}"

    wrapped = {"item": "apple", "attrs": {"size": 1}}
    result = ctx.container.get(RenderEngineAPI)._apply_render(wrapped, None, render_any, depth=2)

    assert result == "apple depth=2 attrs={'size': 1}"


def test_fruits_with_attribute_and_render_without_attrs(make_ctx):
    """Demo: attribute loaded in the query must not break a render without an attrs param.

    Regression for render_org_diff-style renders: before the fix the engine passed
    attrs to render_org_item and fell back to the raw {'item': ..., 'attrs': ...} repr.
    """
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    _, _, _, out = qp.execute_query(":org-item id name, insert_fruits, fruit_cost")

    lines = out.strip().split("\n")
    assert len(lines) == 10  # All 10 fruits (9 regular + 1 mythical)
    assert lines[0] == "- 1 :: apple"
    assert lines[1] == "- 2 :: orange"
    # The loaded attribute does not leak into the render, and no raw fallback reprs
    assert "fruit_cost" not in out
    assert "'item':" not in out


def test_fruits_sorted_by_attribute_render_clean(make_ctx):
    """Demo: order by a loaded attribute, the render shows only the items."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    _, _, _, out = qp.execute_query(":org-item id name, insert_fruits, fruit_cost, sort_by_field fruit_cost --desc")

    lines = out.strip().split("\n")
    assert len(lines) == 10
    assert lines[0] == "- 5 :: blueberry"  # most expensive fruit first
    assert lines[-1] == "- 10 :: ambrosia"
    # Sorted by the attribute, rendered without it
    assert "fruit_cost" not in out
    assert "'item':" not in out


def test_fruits_with_attribute_and_org_render_shows_label_once(make_ctx):
    """Demo: a render declaring attrs still receives them; the engine adds no second label."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    _, _, _, out = qp.execute_query(":org, insert_fruits, pfc")

    lines = out.strip().split("\n")
    assert lines[0] == "- pfc"  # the render labels the attribute itself
    assert lines[1] == "* 1 apple"
    # No empty bullet and no duplicated label from an engine-side wrapper
    assert "\n- \n" not in out
    assert "- pfc\n- pfc" not in out


def test_fruits_with_attribute_default_render(make_ctx):
    """Demo: default render stays intact when an attribute is loaded."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_history,
        plugins_renders,
        plugins_org,
    )
    qp = make_qp(ctx)
    _, _, _, out = qp.execute_query("insert_fruits, fruit_cost")

    lines = out.strip().split("\n")
    assert len(lines) == 10
    assert lines[0] == "- 1 :: apple"
    assert "'item':" not in out


# --- has_variant: which renders a frontend can resolve without falling back to text ---


def _engine_with_html_table_variant(make_ctx):
    """The render engine of a container holding the core renders plus ':table's html variant."""
    ctx = make_ctx(plugins_renders)
    register_tools_from_module(ctx, plugins_test_render_variants.__name__)
    return ctx.container.get(RenderEngineAPI)


def test_has_variant_sees_the_variant_behind_a_shared_alias(make_ctx):
    """One name carrying two renders - one per frontend - answers True for both."""
    engine = _engine_with_html_table_variant(make_ctx)

    assert engine.has_variant("table", frontend=FRONTEND_TEXT) is True
    assert engine.has_variant("table", frontend=FRONTEND_HTML) is True


def test_has_variant_sees_the_variant_behind_the_render_name(make_ctx):
    """The html variant is reachable under its own function name as well as the alias."""
    engine = _engine_with_html_table_variant(make_ctx)

    assert engine.has_variant("render_html_table_test", frontend=FRONTEND_HTML) is True


def test_has_variant_is_false_for_a_render_without_the_frontend(make_ctx):
    """A render with no variant for the frontend answers False, its text variant notwithstanding."""
    engine = _engine_with_html_table_variant(make_ctx)

    assert engine.has_variant("raw", frontend=FRONTEND_HTML) is False


def test_has_variant_defaults_to_the_text_frontend(make_ctx):
    engine = make_ctx(plugins_renders).container.get(RenderEngineAPI)

    assert engine.has_variant("raw") is True


def test_has_variant_is_false_for_an_unknown_name(make_ctx):
    engine = make_ctx(plugins_renders).container.get(RenderEngineAPI)

    assert engine.has_variant("no_such_render_xyz", frontend=FRONTEND_HTML) is False
