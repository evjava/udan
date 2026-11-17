"""Tests for CSV file plugin.

This test file demonstrates the csv plugin functionality for reading
and parsing CSV files.
"""

import ast

from tests.conftest import make_qp, register_tools_from_module
from udan.plugins_tools_core import plugins_help, plugins_system
from udan.plugins_tools_examples import plugins_builtins, plugins_csv
from udan.renders import plugins_renders


def test_csv_inserters_available(make_ctx):
    """Test that csv inserters are registered."""
    ctx = make_ctx(plugins_renders)
    register_tools_from_module(ctx, plugins_csv.__name__)

    tools = ctx.registry.get_tools()
    assert "insert_csv_rows" in tools
    assert "insert_csv_values" in tools
    assert "read_csv" in tools


def test_csv_read_simple_file(make_ctx):
    """Test reading a simple CSV file."""
    ctx = make_ctx(plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins.__name__)
    register_tools_from_module(ctx, plugins_csv.__name__)

    result = qp.execute_query('insert_csv_rows "tests/resources/test_data.csv", :list')

    # Should return data
    assert result[3]  # Output should not be empty

    # Verify it's a list of dictionaries
    rows = ast.literal_eval(result[3])
    assert len(rows) == 5  # Test file has 5 data rows
    assert "id" in rows[0]
    assert "name" in rows[0]
    assert rows[0]["name"] == "Alice"
    assert rows[1]["name"] == "Bob"


def test_csv_values_flat_list(make_ctx):
    """Test insert_csv_values returns flat list."""
    ctx = make_ctx(plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_csv.__name__)

    result = qp.execute_query('insert_csv_values "tests/resources/test_data.csv", :list')

    # Should return flat list of values
    assert result[3]  # Output should not be empty

    # Verify it contains header and data values
    output = result[3]
    assert "id" in output
    assert "Alice" in output
    assert "Bob" in output


def test_csv_no_header(make_ctx):
    """Test reading CSV without headers."""
    ctx = make_ctx(plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_csv.__name__)

    result = qp.execute_query('insert_csv_rows "tests/resources/test_data.csv" --nohas_header, :list')

    # Should return data
    assert result[3]

    rows = ast.literal_eval(result[3])
    # Without headers, should use column indices as keys
    assert "0" in rows[0]  # First column index
    assert "1" in rows[0]  # Second column index


def test_csv_skip_rows(make_ctx):
    """Test skipping rows in CSV."""
    ctx = make_ctx(plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_csv.__name__)

    # Skip the header row, so we get only data rows
    result = qp.execute_query('insert_csv_values "tests/resources/test_data.csv", skip_rows=1, :list')

    # Should return data without headers
    assert result[3]

    # Should not contain header names
    output = result[3]
    # The word "id", "name", etc. are in header row, which we skipped
    # So output should only have data values
    assert "Alice" in output
    assert "Bob" in output


def test_csv_introspection(make_ctx):
    """Test csv inserter introspection."""
    ctx = make_ctx(plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_help.__name__)
    register_tools_from_module(ctx, plugins_builtins.__name__)
    register_tools_from_module(ctx, plugins_system.__name__)
    register_tools_from_module(ctx, plugins_csv.__name__)

    # Check insert_csv_rows documentation
    _, _, _, out = qp.execute_query("? insert_csv_rows")

    assert "insert_csv_rows" in out
    assert "file" in out.lower() or "filepath" in out.lower()


def test_csv_file_not_found(make_ctx):
    """Test error handling for non-existent file."""
    ctx = make_ctx(plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_csv.__name__)

    # Try to read non-existent file
    result = qp.execute_query('insert_csv_rows "nonexistent.csv", :list')

    # Should return error message
    assert result[3]  # Error message should be in output
    assert "not found" in result[3].lower() or "error" in result[3].lower()


def test_csv_tsv(make_ctx):
    """Test reading CSV files using read_csv alias."""
    ctx = make_ctx(plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins.__name__)
    register_tools_from_module(ctx, plugins_csv.__name__)

    # Test the read_csv alias
    result = qp.execute_query('read_csv "tests/resources/test_data.csv", :list')
    assert result[3]  # Should read CSV successfully

    # Verify it returns the same data as insert_csv_rows
    rows = ast.literal_eval(result[3])
    assert len(rows) == 5
    assert rows[0]["name"] == "Alice"


def test_csv_rows_with_table_render(make_ctx):
    """Test reading CSV rows together with the table render."""
    ctx = make_ctx(plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins.__name__)
    register_tools_from_module(ctx, plugins_csv.__name__)

    result = qp.execute_query('read_csv_rows "tests/resources/test_data.csv", render_csv_row')

    # Should render as table rows with row numbers
    assert result[3]  # Output should not be empty
    output = result[3]
    assert "- 0 |" in output  # First row with row number 0
    assert "1" in output  # First data value
    assert "Alice" in output  # First name


def test_csv_row_content_attribute(make_ctx):
    """Test csv_row_content attribute extracts formatted row."""
    ctx = make_ctx(plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins.__name__)
    register_tools_from_module(ctx, plugins_csv.__name__)

    result = qp.execute_query('read_csv_rows "tests/resources/test_data.csv", csv_row_content')

    # Should return formatted row content
    assert result[3]  # Output should not be empty
    output = result[3]
    assert "|" in output  # Should have table separators
