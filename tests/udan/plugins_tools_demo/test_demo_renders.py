"""Tests for render tools with demo data."""

import pytest

import udan.plugins_tools_demo.plugins_demo
import udan.plugins_tools_demo.plugins_fruits
from tests.conftest import make_qp, register_tools_from_module
from udan.plugins_tools_core import plugins_system
from udan.plugins_tools_examples import plugins_builtins
from udan.renders import plugins_renders


@pytest.fixture
def ctx_with_renders(make_ctx):
    """Provide an UdanContext with demo plugins and renders registered."""

    ctx = make_ctx()
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)
    register_tools_from_module(ctx, plugins_builtins.__name__)
    register_tools_from_module(ctx, plugins_system.__name__)
    register_tools_from_module(ctx, plugins_renders.__name__)
    return ctx


def test_table_with_all_columns(ctx_with_renders):
    qp_with_renders = make_qp(ctx_with_renders)
    """Test table render shows all columns by default."""
    _, _, _, out = qp_with_renders.execute_query(":table insert_fruits")

    lines = out.strip().split("\n")

    # Should have header row with all columns
    header = lines[0]
    assert "| name" in header
    assert "| id" in header
    assert "| calories" in header
    assert "| color" in header
    assert "| ftype" in header

    # Should contain all fruit data
    assert "apple" in out
    assert "orange" in out
    assert "banana" in out


def test_table_with_selected_columns(ctx_with_renders):
    qp_with_renders = make_qp(ctx_with_renders)
    """Test table render with specific columns selected."""
    _, _, _, out = qp_with_renders.execute_query("insert_fruits, (:table id name)")

    lines = out.strip().split("\n")
    header = lines[0]

    # Should only have id and name columns
    assert "| id" in header
    assert "| name" in header
    assert "| calories" not in header
    assert "| color" not in header
    assert "| ftype" not in header

    # Check data row has only id and name
    data_lines = [line for line in lines if "| apple" in line or "| 1 |" in line]
    assert len(data_lines) == 1
    apple_line = data_lines[0]

    # Should have id and name, no other columns
    assert "apple" in apple_line
    assert "1" in apple_line
    assert "fruit" not in apple_line
    assert "red" not in apple_line


def test_table_with_single_column(ctx_with_renders):
    qp_with_renders = make_qp(ctx_with_renders)
    """Test table render with single column selected."""
    _, _, _, out = qp_with_renders.execute_query("insert_fruits, (:table name)")

    lines = out.strip().split("\n")
    header = lines[0]

    # Should only have name column
    assert header.count("|") == 2  # Only name column (2 border characters)
    assert "| name" in header

    # Data should only contain names
    assert "| apple" in out
    assert "| orange" in out
    assert "| 1" not in out  # No id column
    assert "| fruit" not in out  # No ftype column


def test_table_with_three_columns(ctx_with_renders):
    qp_with_renders = make_qp(ctx_with_renders)
    """Test table render with three specific columns."""
    _, _, _, out = qp_with_renders.execute_query("insert_fruits, (:table id name ftype)")

    lines = out.strip().split("\n")
    header = lines[0]

    # Should have id, name, and ftype columns
    assert "| id" in header
    assert "| name" in header
    assert "| ftype" in header
    assert "| calories" not in header
    assert "| color" not in header

    # Check data row
    apple_line = [line for line in lines if "apple" in line][0]
    assert "apple" in apple_line
    assert "1" in apple_line
    assert "fruit" in apple_line
    assert "red" not in apple_line
    assert "52" not in apple_line


def test_table_with_nonexistent_column(ctx_with_renders):
    qp_with_renders = make_qp(ctx_with_renders)
    """Test table render with nonexistent column shows requested columns."""
    _, _, _, out = qp_with_renders.execute_query("insert_fruits, (:table id nonexistent)")

    # Should render with both columns (id exists, nonexistent is empty)
    assert "| id" in out
    assert "| nonexistent" in out

    # All fruits should be shown with empty values for nonexistent column
    assert "|  1 |" in out
    assert "|  2 |" in out
    assert "| 10 |" in out


def test_table_introspection(ctx_with_renders):
    qp_with_renders = make_qp(ctx_with_renders)
    """Test table render introspection shows documentation and available columns."""
    _, _, _, out = qp_with_renders.execute_query("insert_fruits, :table ?")

    lines = out.strip().split("\n")

    expected_lines = [
        "- renders.table (render) [src/udan/renders/plugins_renders.py:735]",
        "  - Aggregate render: creates table from all dict items.",
        "",
        "Collects all dict items and formats them as a table with headers.",
        "Handles grouped data (Group markers) by rendering separate tables with headers.",
        "Scalar items without attributes are rendered as a depth/item table.",
        "",
        "Uses custom formatting to match legacy table output (right-aligned numbers).",
        "",
        "Args:",
        "    depths: List of depth values for each item",
        "    children: List of items to render",
        "    attr_ds: Attribute descriptors (not used, kept for signature)",
        "    *columns: Optional column names to display (e.g., :table id entry)",
        "              If not specified, shows all columns from all items",
        "",
        "Returns:",
        "    Formatted table string",
        "",
        "Examples:",
        "    :table              # Show all columns",
        "    :table id entry     # Show only id and entry columns",
        "    :table name language  # Show only name and language columns",
        "",
        # depths, children, attr_ds and columns are documented by the Args section
        # above - only the one it says nothing about gets a line of its own
        "  - items_attrs: any",
        "- ",
        "- Available columns (6):",
        "  - calories",
        "  - color",
        "  - ftype",
        "  - id",
        "  - name",
        "  - tags",
    ]

    assert lines == expected_lines
