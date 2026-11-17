"""Tests for :table render with column specs and attribute promotion."""

import pytest

import udan.plugins_tools_demo.plugins_demo
import udan.plugins_tools_demo.plugins_fruits
from tests.conftest import make_qp, register_tools_from_module
from udan.plugins_tools_examples import plugins_builtins
from udan.renders import plugins_renders
from udan.renders.plugins_renders import _apply_col_specs, _parse_col_spec, _resolve_dict_path


@pytest.fixture
def ctx_with_renders(make_ctx):
    """Provide an UdanContext with demo plugins and renders registered."""

    ctx = make_ctx()
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)
    register_tools_from_module(ctx, plugins_builtins.__name__)
    register_tools_from_module(ctx, plugins_renders.__name__)
    return ctx


# ---------------------------------------------------------------------------
# Column spec parsing (unit tests)
# ---------------------------------------------------------------------------


def test_parse_col_spec_plain_key():

    assert _parse_col_spec("name") == ("name", "name", "")


def test_parse_col_spec_with_format():

    assert _parse_col_spec("cov:{percent_covered:.0f}") == ("cov", "percent_covered", ".0f")


def test_parse_col_spec_without_format():

    assert _parse_col_spec("fn:{function_name}") == ("fn", "function_name", "")


def test_parse_col_spec_with_dot_path():

    assert _parse_col_spec("proteins:{pfc.proteins:.1f}") == ("proteins", "pfc.proteins", ".1f")


# ---------------------------------------------------------------------------
# Dict path resolution (unit tests)
# ---------------------------------------------------------------------------


def test_resolve_dict_path_simple():

    assert _resolve_dict_path({"name": "apple"}, "name") == "apple"


def test_resolve_dict_path_nested():

    d = {"pfc": {"proteins": 0.3, "fats": 0.2}}
    assert _resolve_dict_path(d, "pfc.proteins") == 0.3


def test_resolve_dict_path_missing():

    assert _resolve_dict_path({"name": "apple"}, "color") is None


def test_resolve_dict_path_missing_nested():

    assert _resolve_dict_path({"pfc": {}}, "pfc.proteins") is None


def test_resolve_dict_path_empty():

    assert _resolve_dict_path({}, "anything") is None


# ---------------------------------------------------------------------------
# Column spec application (unit tests)
# ---------------------------------------------------------------------------


def test_apply_col_specs_plain_key():

    items = [{"name": "apple", "color": "red"}]
    col_specs = [("name", "name", "")]
    result = _apply_col_specs(items, col_specs)
    assert result == [{"name": "apple"}]


def test_apply_col_specs_with_format():

    items = [{"percent_covered": 75.567}]
    col_specs = [("cov", "percent_covered", ".0f")]
    result = _apply_col_specs(items, col_specs)
    assert result == [{"cov": "76"}]


def test_apply_col_specs_with_dot_path():

    items = [{"pfc": {"proteins": 0.3, "fats": 0.2}}]
    col_specs = [("proteins", "pfc.proteins", "")]
    result = _apply_col_specs(items, col_specs)
    assert result == [{"proteins": 0.3}]


def test_apply_col_specs_missing_value():

    items = [{"name": "apple"}]
    col_specs = [("cov", "percent_covered", ".0f")]
    result = _apply_col_specs(items, col_specs)
    assert result == [{"cov": ""}]


def test_apply_col_specs_multiple_columns():

    items = [{"name": "apple", "pfc": {"proteins": 0.3, "fats": 0.2}}]
    col_specs = [
        ("fruit", "name", ""),
        ("proteins", "pfc.proteins", ""),
        ("fats", "pfc.fats", ".1f"),
    ]
    result = _apply_col_specs(items, col_specs)
    assert result == [{"fruit": "apple", "proteins": 0.3, "fats": "0.2"}]


# ---------------------------------------------------------------------------
# Integration tests: :table with column specs on fruit data
# ---------------------------------------------------------------------------


def test_table_column_spec_renames_header(ctx_with_renders):
    qp_with_renders = make_qp(ctx_with_renders)
    """Column spec 'fn:{name}' renames the column header to 'fn'."""
    _, _, _, out = qp_with_renders.execute_query('fruits, limit 3, :table "fn:{name}"')

    lines = out.strip().split("\n")
    header = lines[0]
    assert "| fn" in header
    assert "| apple" in out


def test_table_column_spec_with_format(ctx_with_renders):
    qp_with_renders = make_qp(ctx_with_renders)
    """Column spec 'cost:{fruit_cost:.1f}' formats float values."""
    _, _, _, out = qp_with_renders.execute_query(
        'fruits, fruit_cost, limit 3, :table "name:{name}" "cost:{fruit_cost:.1f}"'
    )

    lines = out.strip().split("\n")
    header = lines[0]
    assert "| name" in header
    assert "| cost" in header
    assert "apple" in out
    assert "1.2" in out


def test_table_column_spec_nested_attr(ctx_with_renders):
    qp_with_renders = make_qp(ctx_with_renders)
    """Column spec with dot path resolves nested dict attribute (pfc)."""
    _, _, _, out = qp_with_renders.execute_query('fruits, pfc, limit 3, :table "name:{name}" "proteins:{pfc.proteins}"')

    lines = out.strip().split("\n")
    header = lines[0]
    assert "| name" in header
    assert "| proteins" in header
    assert "apple" in out
    assert "0.3" in out


def test_table_column_spec_multiple_formatted(ctx_with_renders):
    qp_with_renders = make_qp(ctx_with_renders)
    """Multiple column specs with formatting on pfc data."""
    _, _, _, out = qp_with_renders.execute_query(
        'fruits, pfc, limit 3, :table "name:{name}" "P:{pfc.proteins:.1f}" "F:{pfc.fats:.1f}" "C:{pfc.carbs:.1f}"'
    )

    lines = out.strip().split("\n")
    header = lines[0]
    assert "| name" in header
    assert "| P" in header
    assert "| F" in header
    assert "| C" in header
    # Apple: proteins=0.3, fats=0.2, carbs=14.0
    assert "0.3" in out
    assert "0.2" in out
    assert "14.0" in out


def test_table_plain_columns_still_work(ctx_with_renders):
    qp_with_renders = make_qp(ctx_with_renders)
    """Plain column names without spec syntax still work as before."""
    _, _, _, out = qp_with_renders.execute_query("fruits, limit 3, :table name color")

    lines = out.strip().split("\n")
    header = lines[0]
    assert "| name" in header
    assert "| color" in header
    assert "| calories" not in header
    assert "apple" in out
    assert "red" in out


def test_table_mixed_plain_and_spec_columns(ctx_with_renders):
    qp_with_renders = make_qp(ctx_with_renders)
    """Mix of plain column names and column specs."""
    _, _, _, out = qp_with_renders.execute_query('fruits, fruit_cost, limit 3, :table name "cost:{fruit_cost:.1f}"')

    lines = out.strip().split("\n")
    header = lines[0]
    assert "| name" in header
    assert "| cost" in header
    assert "apple" in out
    assert "1.2" in out
