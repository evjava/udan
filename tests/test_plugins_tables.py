"""Tests for table render plugins."""

from tests.conftest import make_qp
from udan.plugins_tools_examples import plugins_csv
from udan.renders import plugins_tables
from udan.renders.plugins_tables import render_entries


def test_render_entries_dicts():
    """Test render_entries with dict items."""
    result = render_entries([0, 0], [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}], [])
    expected = "** entry-1\n- a :: 1\n- b :: 2\n** entry-2\n- a :: 3\n- b :: 4"
    assert result == expected


def test_render_entries_scalar_items():
    """Test render_entries with non-dict items."""
    result = render_entries([0, 0, 0], ["apple", "orange", 42], [])
    expected = "** entry-1\n- item :: apple\n** entry-2\n- item :: orange\n** entry-3\n- item :: 42"
    assert result == expected


def test_render_entries_empty():
    """Test render_entries with no items."""
    assert render_entries([], [], []) == ""


def test_render_entries_align():
    """Test render_entries pads keys so values start on the same level."""
    result = render_entries([0, 0], [{"a": "1", "ab": "2"}, {"a": "3", "ab": "4"}], [])
    expected = "** entry-1\n- a  :: 1\n- ab :: 2\n** entry-2\n- a  :: 3\n- ab :: 4"
    assert result == expected


def test_render_entries_align_false():
    """Test render_entries with align disabled."""
    result = render_entries([0, 0], [{"a": "1", "ab": "2"}, {"a": "3", "ab": "4"}], [], align=False)
    expected = "** entry-1\n- a :: 1\n- ab :: 2\n** entry-2\n- a :: 3\n- ab :: 4"
    assert result == expected


def test_render_entries_align_string_false():
    """Test render_entries with align passed as string from a named arg."""
    result = render_entries([0], [{"a": "1", "ab": "2"}], [], align="False")
    expected = "** entry-1\n- a :: 1\n- ab :: 2"
    assert result == expected


def test_render_entries_fields():
    """Test render_entries with field args renders only those fields."""
    result = render_entries([0, 0], [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}], [], "b")
    expected = "** entry-1\n- b :: 2\n** entry-2\n- b :: 4"
    assert result == expected


def test_render_entries_fields_order():
    """Test field args set the order of the rendered lines."""
    result = render_entries([0], [{"a": "1", "b": "2"}], [], "b", "a")
    expected = "** entry-1\n- b :: 2\n- a :: 1"
    assert result == expected


def test_render_entries_fields_missing_value():
    """Test a field an item lacks renders with an empty value."""
    result = render_entries([0, 0], [{"a": "1"}, {"b": "2"}], [], "a", "b")
    expected = "** entry-1\n- a :: 1\n- b :: \n** entry-2\n- a :: \n- b :: 2"
    assert result == expected


def test_render_entries_fields_scalar_items():
    """Test field args on non-dict items keep the single item field."""
    result = render_entries([0, 0], ["apple", 42], [], "item")
    expected = "** entry-1\n- item :: apple\n** entry-2\n- item :: 42"
    assert result == expected


def test_render_entries_fields_col_spec_rename():
    """Test a field spec renames the key, like :table column specs."""
    result = render_entries([0], [{"name": "apple"}], [], "fruit:{name}")
    expected = "** entry-1\n- fruit :: apple"
    assert result == expected


def test_render_entries_fields_col_spec_format():
    """Test a field spec formats the value, like :table column specs."""
    result = render_entries([0], [{"price": 1.26}], [], "cost:{price:.1f}")
    expected = "** entry-1\n- cost :: 1.3"
    assert result == expected


def test_render_entries_fields_col_spec_dot_path():
    """Test a field spec resolves a nested dict field, like :table column specs."""
    result = render_entries([0], [{"pfc": {"proteins": 0.3}}], [], "proteins:{pfc.proteins}")
    expected = "** entry-1\n- proteins :: 0.3"
    assert result == expected


def test_render_entries_with_query(tmp_path, make_ctx):
    """Test :entries render with read_csv through query execution."""
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("id,name\n1,Alice\n2,Bob\n")

    ctx = make_ctx(plugins_csv, plugins_tables)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query(f'read_csv "{csv_file}", :entries')

    expected = "** entry-1\n- id   :: 1\n- name :: Alice\n** entry-2\n- id   :: 2\n- name :: Bob"
    assert out == expected


def test_render_entries_align_named_arg_with_query(tmp_path, make_ctx):
    """Test :entries --align=False through query execution."""
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("id,name\n1,Alice\n")

    ctx = make_ctx(plugins_csv, plugins_tables)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query(f'read_csv "{csv_file}", :entries --align=False')

    assert out == "** entry-1\n- id :: 1\n- name :: Alice"


def test_render_entries_fields_with_query(tmp_path, make_ctx):
    """Test :entries field args through query execution."""
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("id,name,city\n1,Alice,Prague\n2,Bob,Berlin\n")

    ctx = make_ctx(plugins_csv, plugins_tables)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query(f'read_csv "{csv_file}", :entries city name')

    expected = "** entry-1\n- city :: Prague\n- name :: Alice\n** entry-2\n- city :: Berlin\n- name :: Bob"
    assert out == expected


def test_render_entries_row_items_per_column(tmp_path, make_ctx):
    """Test :entries renders row items one line per column with aligned keys."""
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("id,name,city\n1,Alice,Prague\n2,Bob,Berlin\n")

    ctx = make_ctx(plugins_csv, plugins_tables)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query(f'read_csv_rows "{csv_file}", :entries')

    expected = (
        "** entry-1\n- id   :: 1\n- name :: Alice\n- city :: Prague\n"
        "** entry-2\n- id   :: 2\n- name :: Bob\n- city :: Berlin"
    )
    assert out == expected


def test_render_entries_row_items_untruncated(tmp_path, make_ctx):
    """Test :entries renders row values in full, unlike the 30-char table truncation."""
    csv_file = tmp_path / "data.csv"
    long_name = "A" * 40
    csv_file.write_text(f"name\n{long_name}\n")

    ctx = make_ctx(plugins_csv, plugins_tables)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query(f'read_csv_rows "{csv_file}", :entries')

    assert out == f"** entry-1\n- name :: {long_name}"


def test_render_entries_row_items_fields_with_query(tmp_path, make_ctx):
    """Test :entries field args on row items pick the columns of the row_data dict."""
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("id,name,city\n1,Alice,Prague\n")

    ctx = make_ctx(plugins_csv, plugins_tables)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query(f'read_csv_rows "{csv_file}", :entries city')

    assert out == "** entry-1\n- city :: Prague"
