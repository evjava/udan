"""Tests for org-mode plugins."""

from tests.conftest import make_qp, register_tools_from_module
from udan.plugins_tools_examples import plugins_org
from udan.plugins_tools_examples.api_types import ASTChunk
from udan.plugins_tools_examples.plugins_org import (
    date_after,
    date_before,
    insert_cur_items,
    org_image,
    org_table_from_section_with_properties,
    render_org_astchunk,
    render_org_generic,
    render_org_source_block,
    render_org_text,
)
from udan.plugins_tools_examples.plugins_org_parser import OrgItem
from udan.renders import plugins_renders, plugins_tables

# Expected output for first org item from cur-python.org
EXPECTED_FIRST_ORG_ITEM = "** INFO tqdm"


def test_org_parser():
    """Test parsing org items from file."""
    items = insert_cur_items("tests/resources/cur-python.org")

    # Should have parsed items
    assert len(items) > 0

    # Check first item
    first = items[0]
    assert isinstance(first, OrgItem)
    assert first.title == "INFO tqdm"
    assert first.date == "21.07.23-01:20:09"


def test_org_insert_cur(make_ctx):
    """Test inserting cur items via exec."""
    ctx = make_ctx(plugins_org)
    qp = make_qp(ctx)

    forest, attrs, render_specs, out = qp.execute_query("insert_cur_items tests/resources/cur-python.org")

    # Should output org items with proper format
    lines = out.strip().split("\n")
    # First line should be the headline
    assert lines[0] == EXPECTED_FIRST_ORG_ITEM
    assert len(out) > 0


def test_org_date_filter():
    """Test filtering by date."""
    items = insert_cur_items("tests/resources/cur-python.org")

    # Filter items after a certain date
    filtered = [item for item in items if date_after(item, "01.01.21-00:00:00")]
    assert len(filtered) > 0

    # Filter items before a certain date
    filtered = [item for item in items if date_before(item, "01.01.24-00:00:00")]
    assert len(filtered) > 0


def test_org_query_with_date_filter(make_ctx):
    """Test querying with date filter."""
    ctx = make_ctx(plugins_org)
    qp = make_qp(ctx)

    # Query with date filter (dates with ':' must be quoted - bare ATOM tokens exclude ':')
    forest, attrs, render_specs, out = qp.execute_query(
        'insert_cur_items tests/resources/cur-python.org, date_after "01.01.23-00:00:00"'
    )

    # Should show items after 2023
    assert len(out) > 0


def test_org_with_attributes(make_ctx):
    """Test org item attributes."""
    ctx = make_ctx(plugins_org)
    qp = make_qp(ctx)

    register_tools_from_module(ctx, plugins_renders.__name__)

    # Query with title attribute and org render
    forest, attrs, render_specs, out = qp.execute_query(
        "insert_cur_items tests/resources/cur-python.org, org_title, :org"
    )

    # Output shows attribute name first, then org format content
    lines = [
        line for line in out.strip().split("\n") if line.strip() and line.strip() != "-"
    ]  # Filter empty lines and lone bullets
    # First line should be the attribute name
    assert lines[0] == "- org_title"
    # Second line should be the first org item headline
    assert lines[1] == EXPECTED_FIRST_ORG_ITEM
    # Third line should have the date property
    assert lines[2] == "date: 21.07.23-01:20:09"


def test_org_rendering_format(make_ctx):
    """Test that org items are rendered in org-mode format."""
    ctx = make_ctx(plugins_org)
    qp = make_qp(ctx)

    # Query without attributes - should render in org format
    forest, attrs, render_specs, out = qp.execute_query("insert_cur_items tests/resources/cur-python.org")

    # Should render with ** headlines and properties
    lines = out.strip().split("\n")
    # First line should be the headline
    assert lines[0] == EXPECTED_FIRST_ORG_ITEM
    # Should have a date property
    date_lines = [line for line in lines if line.startswith("date:")]
    assert len(date_lines) > 0
    # Should have proper org format with asterisks, not bullets
    assert not out.startswith("- ")  # Not bullet format


def test_org_astchunk_no_extra_indentation():
    """Test that ASTChunk org-mode rendering has no extra indentation on markers.

    This validates the fix for nested ASTChunks (depth > 0) where org-mode markers
    (like **, :PROPERTIES:, #+begin_src, #+end_src) should not be indented
    even when the ASTChunk is nested.
    """

    # Create a nested ASTChunk (depth=1) to test the fix
    # Using type="duplication" which was the case that revealed the bug
    chunk = ASTChunk(
        name="test_function",
        type="duplication",
        docstring="Test function for indentation test",
        source_file="src/udan/test_file.py",
        line_start_number=42,
        line_end_number=50,
        full_code='def test_function() -> None:\n    """Test function."""\n    return None',
    )

    # Render as org - the output should be org-mode format
    result = render_org_astchunk(chunk, depth=1)

    lines = result.strip().split("\n")

    # For a nested chunk (depth=1), markers should have NO leading space
    # (org-mode markers like **, :PROPERTIES:, #+begin_src, #+end_src should start at column 0)
    # This was the bug: before the fix, they had leading space from parent indent

    # Check heading line (should be "** src/udan/test_file.py:42-50" with no leading space)
    assert lines[0] == "** src/udan/test_file.py:42-50"

    # Check properties (should be ":PROPERTIES:" with no leading space)
    assert lines[1] == ":PROPERTIES:"

    # Check source_file property (should be ":source_file: ..." with no leading space)
    assert lines[2] == ":source_file: src/udan/test_file.py:42-50"

    # Check docstring property (should be ":docstring: ..." with no leading space)
    assert lines[3] == ":docstring: Test function for indentation test"

    # Check END marker (should be ":END:" with no leading space)
    assert lines[4] == ":END:"

    # Check begin_src marker (should be "#+begin_src python" with no leading space)
    assert lines[5] == "#+begin_src python"

    # Check code has proper indent
    assert lines[6] == "  def test_function() -> None:"
    assert lines[7] == '      """Test function."""'
    assert lines[8] == "      return None"

    # Check end_src marker (should be "#+end_src" with no leading space)
    assert lines[9] == "#+end_src"


def test_date_filters_with_non_orgitem():
    """Test date_after and date_before return False for non-OrgItem objects."""

    # Test with dict
    dict_item = {"title": "Test", "date": "01.01.23-00:00:00"}
    assert date_after(dict_item, "01.01.22-00:00:00") is False
    assert date_before(dict_item, "01.01.24-00:00:00") is False

    # Test with string
    string_item = "test string"
    assert date_after(string_item, "01.01.22-00:00:00") is False
    assert date_before(string_item, "01.01.24-00:00:00") is False

    # Test with None
    assert date_after(None, "01.01.22-00:00:00") is False
    assert date_before(None, "01.01.24-00:00:00") is False


def test_render_org_generic_with_dict_format():
    """Test render_org_generic with dict format containing item and attrs."""

    # Create an OrgItem
    org_item = OrgItem(
        title="Test item",
        level=2,
        tags=["python"],
        date="01.01.23-00:00:00",
        content="Test content",
    )

    # Test with dict format (as used in rendering pipeline)
    item_dict = {"item": org_item, "attrs": {"test_attr": "test_value"}}
    result = render_org_generic(item_dict, indent="", depth=0)

    # Should show attribute identity first
    assert "- test_attr" in result
    # Should show org item content
    assert "** Test item" in result
    assert "date: 01.01.23-00:00:00" in result


def test_render_org_source_block_with_dict():
    """Test render_org_source_block with dict format."""

    # Test with dict format (direct call)
    item_dict = {
        "_type": "attribute_value",
        "value": "def hello():\n    print('world')",
        "item": "test.py",
        "original_item": "test.py",
    }

    result = render_org_source_block(item_dict)

    # Should render as org-mode source block
    assert "* test.py" in result
    assert "#+begin_src python" in result
    assert "def hello():" in result
    assert "    print('world')" in result
    assert "#+end_src" in result


def test_render_org_source_block_with_kwargs():
    """Test render_org_source_block with kwargs format (called from rendering pipeline)."""

    # Test with kwargs (as used in rendering pipeline)
    code = "def test():\n    return 42"
    original_item = "module.py"

    result = render_org_source_block(item="test", indent="  ", depth=1, value=code, original_item=original_item)

    # Should render with proper indentation and source block
    assert "  * module.py" in result
    assert "  #+begin_src python" in result
    assert "  def test():" in result
    assert "      return 42" in result
    assert "  #+end_src" in result


def test_render_org_text_with_dict():
    """Test render_org_text with dict format."""

    # Test with dict format
    item_dict = {
        "_type": "attribute_value",
        "value": "Line 1\nLine 2\nLine 3",
        "item": "test.txt",
        "original_item": "test.txt",
    }

    result = render_org_text(item_dict)

    # Should render as org-mode text block
    assert "* test.txt" in result
    assert "Line 1" in result
    assert "Line 2" in result
    assert "Line 3" in result


def test_render_org_text_with_kwargs():
    """Test render_org_text with kwargs format."""

    # Test with kwargs
    text = "First line\nSecond line"
    original_item = "document.txt"

    result = render_org_text(item="test", indent="  ", depth=1, value=text, original_item=original_item)

    # Should render with proper indentation
    assert "  * document.txt" in result
    assert "  First line" in result
    assert "  Second line" in result


# --- org_image attribute ---


def test_org_image_png(tmp_path):
    image_file = tmp_path / "photo.png"
    image_file.write_bytes(b"pixels")
    assert org_image(image_file) == f"[[{image_file}]]"


def test_org_image_jpeg(tmp_path):
    image_file = tmp_path / "photo.jpeg"
    image_file.write_bytes(b"pixels")
    assert org_image(str(image_file)) == f"[[{image_file}]]"


def test_org_image_non_image_returns_empty(tmp_path):
    text_file = tmp_path / "notes.txt"
    text_file.write_text("hello")
    assert org_image(text_file) == ""


def test_org_image_non_path_returns_empty():
    assert org_image({"_path": "/tmp/photo.png"}) == ""


def test_org_image_with_width(tmp_path):
    image_file = tmp_path / "photo.png"
    image_file.write_bytes(b"pixels")
    assert org_image(image_file, width=300) == f"#+ATTR_ORG: :width 300\n[[{image_file}]]"


def test_org_image_width_none_keeps_bare_link(tmp_path):
    image_file = tmp_path / "photo.png"
    image_file.write_bytes(b"pixels")
    assert org_image(image_file, width=None) == f"[[{image_file}]]"


def test_org_image_width_non_image_returns_empty(tmp_path):
    text_file = tmp_path / "notes.txt"
    text_file.write_text("hello")
    assert org_image(text_file, width=300) == ""


# --- org_table_from_section_with_properties inserter ---

ORG_TABLE_DOC = """* section 1
* section 2
** alice
- city :: London
- age :: 20
** bob
- city :: NY
- age :: 22
** john
- age :: 30
"""

ORG_TABLE_WITH_INTRO_DOC = """* section 1
* section 2
People known to the section.
** alice
- city :: London
** bob
- age :: 22
"""

ORG_TABLE_DEEP_DOC = """* root
** alice
- city :: London
*** diary
- mood :: good
** bob
- age :: 22
"""

ORG_TABLE_FIRST_SECTION_DOC = """* people
** alice
- city :: London
- age :: 20
** bob
- city :: NY
- age :: 22
"""


def write_org_table_file(tmp_path, doc):
    org_file = tmp_path / "people.org"
    org_file.write_text(doc)
    return org_file


def test_org_table_from_section_with_properties(tmp_path):
    org_file = write_org_table_file(tmp_path, ORG_TABLE_DOC)

    results = list(org_table_from_section_with_properties(f"{org_file}:2"))
    expected = [
        {"name": "alice", "city": "London", "age": "20"},
        {"name": "bob", "city": "NY", "age": "22"},
        {"name": "john", "city": "", "age": "30"},
    ]
    assert results == expected


def test_org_table_from_section_line_argument(tmp_path):
    org_file = write_org_table_file(tmp_path, ORG_TABLE_DOC)

    expected = [
        {"name": "alice", "city": "London", "age": "20"},
        {"name": "bob", "city": "NY", "age": "22"},
        {"name": "john", "city": "", "age": "30"},
    ]
    assert list(org_table_from_section_with_properties(str(org_file), 2)) == expected
    assert list(org_table_from_section_with_properties(str(org_file), "2")) == expected


def test_org_table_from_section_location_in_body(tmp_path):
    org_file = write_org_table_file(tmp_path, ORG_TABLE_WITH_INTRO_DOC)

    results = list(org_table_from_section_with_properties(f"{org_file}:3"))
    expected = [
        {"name": "alice", "city": "London", "age": ""},
        {"name": "bob", "city": "", "age": "22"},
    ]
    assert results == expected


def test_org_table_from_section_bare_path_defaults_to_first_line(tmp_path):
    org_file = write_org_table_file(tmp_path, ORG_TABLE_FIRST_SECTION_DOC)

    results = list(org_table_from_section_with_properties(str(org_file)))
    expected = [
        {"name": "alice", "city": "London", "age": "20"},
        {"name": "bob", "city": "NY", "age": "22"},
    ]
    assert results == expected


def test_org_table_from_section_grandchild_properties_join_the_row(tmp_path):
    org_file = write_org_table_file(tmp_path, ORG_TABLE_DEEP_DOC)

    results = list(org_table_from_section_with_properties(f"{org_file}:1"))
    expected = [
        {"name": "alice", "city": "London", "mood": "good", "age": ""},
        {"name": "bob", "city": "", "mood": "", "age": "22"},
    ]
    assert results == expected


def test_org_table_from_section_without_child_sections(tmp_path):
    org_file = write_org_table_file(tmp_path, ORG_TABLE_DOC)

    assert list(org_table_from_section_with_properties(f"{org_file}:1")) == []
    assert list(org_table_from_section_with_properties(str(org_file))) == []
    assert list(org_table_from_section_with_properties(f"{org_file}:3")) == []


def test_org_table_from_section_invalid_location(tmp_path):
    org_file = write_org_table_file(tmp_path, ORG_TABLE_DOC)

    assert list(org_table_from_section_with_properties(str(org_file), 99)) == []
    assert list(org_table_from_section_with_properties(f"{org_file}:99")) == []
    assert list(org_table_from_section_with_properties(f"{org_file}:abc")) == []
    assert list(org_table_from_section_with_properties("/nonexistent/file.org:1")) == []
    assert list(org_table_from_section_with_properties("/nonexistent/file.org")) == []


def test_org_table_from_section_with_query(tmp_path, make_ctx):
    ctx = make_ctx(plugins_org, plugins_tables)
    qp = make_qp(ctx)
    org_file = write_org_table_file(tmp_path, ORG_TABLE_DOC)
    forest, attrs, render_specs, out = qp.execute_query(
        f'org_table_from_section_with_properties "{org_file}:2", :entries'
    )

    expected = "\n".join(
        [
            "** entry-1",
            "- name :: alice",
            "- city :: London",
            "- age  :: 20",
            "** entry-2",
            "- name :: bob",
            "- city :: NY",
            "- age  :: 22",
            "** entry-3",
            "- name :: john",
            "- city :: ",
            "- age  :: 30",
        ]
    )
    assert out == expected
