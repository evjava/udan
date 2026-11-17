"""Tests for SQL database plugin.

This test file demonstrates the sql plugin functionality for reading
sqlite database tables.
"""

import json
import sqlite3
from contextlib import closing

from tests.conftest import make_qp, register_tools_from_module
from udan.attributes.api_attribute_storage import AttributeStorageAPI
from udan.core.api_attributes import AttributeDescriptor
from udan.plugins_tools_examples import plugins_builtins, plugins_json, plugins_org, plugins_sql
from udan.renders import plugins_renders


def _create_test_db(db_path) -> str:
    """Create a test sqlite database with a users table."""
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("create table users (id integer primary key, name text, age integer, city text)")
        conn.execute("insert into users (name, age, city) values ('Alice', 30, 'NYC')")
        conn.execute("insert into users (name, age, city) values ('Bob', 25, 'LA')")
        conn.commit()
    return str(db_path)


def _fetch_all(db_path: str, sql: str) -> list[tuple]:
    with closing(sqlite3.connect(db_path)) as conn:
        return list(conn.execute(sql))


def test_sql_inserters_available(make_ctx):
    """Test that sql inserters are registered."""
    ctx = make_ctx(plugins_renders)
    register_tools_from_module(ctx, plugins_sql.__name__)

    tools = ctx.registry.get_tools()
    assert "read_sql" in tools
    assert "show_sql_tables" in tools


def test_sql_show_tables(make_ctx, tmp_path):
    """Test show_sql_tables lists tables in alphabetical order."""
    ctx = make_ctx(plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins.__name__)
    register_tools_from_module(ctx, plugins_sql.__name__)

    db_path = str(tmp_path / "test.db")
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("create table users (id integer primary key, name text)")
        conn.execute("create table orders (id integer primary key, total integer)")
        conn.commit()

    result = qp.execute_query(f'show_sql_tables "{db_path}", :list')

    assert result[3] == "[orders, users]"


def test_sql_where_and_limit(make_ctx, tmp_path):
    """Test read_sql with where condition and limit."""
    ctx = make_ctx(plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins.__name__)
    register_tools_from_module(ctx, plugins_sql.__name__)

    db_path = _create_test_db(tmp_path / "test.db")
    query = f'read_sql "{db_path}" --table=users --where=age>20 --limit=1, render_sql_row'
    result = qp.execute_query(query)

    lines = result[3].strip().split("\n")
    assert lines == ["- 1 | 1 | Alice | 30 | NYC |"]


def test_sql_db_not_found(make_ctx, tmp_path):
    """Test error handling for non-existent database file."""
    ctx = make_ctx(plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_sql.__name__)

    db_path = str(tmp_path / "nonexistent.db")
    result = qp.execute_query(f'read_sql "{db_path}" --table=users, render_sql_row')

    assert "not found" in result[3].lower() or "error" in result[3].lower()


def test_sql_rows_with_render(make_ctx, tmp_path):
    """Test reading SQL rows together with their render."""
    ctx = make_ctx(plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins.__name__)
    register_tools_from_module(ctx, plugins_sql.__name__)

    db_path = _create_test_db(tmp_path / "test.db")
    result = qp.execute_query(f'read_sql "{db_path}" --table=users, render_sql_row')

    lines = result[3].strip().split("\n")
    assert lines == [
        "- 1 | 1 | Alice | 30 | NYC |",
        "- 2 | 2 | Bob | 25 | LA |",
    ]


def test_sql_rows_with_table_render(make_ctx, tmp_path):
    """Test read_sql :table renders row columns like read_csv does.

    Regression: SqlRow items rendered as a depth/item table with the pipe row
    string in the item column instead of their columns.
    """
    ctx = make_ctx(plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins.__name__)
    register_tools_from_module(ctx, plugins_sql.__name__)

    db_path = _create_test_db(tmp_path / "test.db")
    result = qp.execute_query(f'read_sql "{db_path}" --table=users, :table')

    # 'name' is moved to the front like for read_csv dict rows
    assert result[3].strip().split("\n") == [
        "| name  | id | age | city |",
        "|-------+----+-----+------|",
        "| Alice |  1 |  30 | NYC  |",
        "| Bob   |  2 |  25 | LA   |",
    ]


def test_sql_rows_with_table_render_columns(make_ctx, tmp_path):
    """Test read_sql :table with explicit columns shows only those columns."""
    ctx = make_ctx(plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins.__name__)
    register_tools_from_module(ctx, plugins_sql.__name__)

    db_path = _create_test_db(tmp_path / "test.db")
    result = qp.execute_query(f'read_sql "{db_path}" --table=users, :table name city')

    assert result[3].strip().split("\n") == [
        "| name  | city |",
        "|-------+------|",
        "| Alice | NYC  |",
        "| Bob   | LA   |",
    ]


def test_sql_rows_with_json_render(make_ctx, tmp_path):
    """Test read_sql :json renders the row columns as JSON objects.

    Regression: SqlRow items serialized as the pipe row string instead of
    their columns.
    """
    ctx = make_ctx(plugins_renders, plugins_json)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins.__name__)
    register_tools_from_module(ctx, plugins_sql.__name__)

    db_path = _create_test_db(tmp_path / "test.db")
    result = qp.execute_query(f'read_sql "{db_path}" --table=users, :json')

    lines = result[3].strip().split("\n")
    assert json.loads("\n".join(lines[:6])) == {"id": 1, "name": "Alice", "age": 30, "city": "NYC"}
    assert json.loads("\n".join(lines[6:])) == {"id": 2, "name": "Bob", "age": 25, "city": "LA"}


def test_sql_rows_field_renders(make_ctx, tmp_path):
    """Test field-oriented renders (:fmt, :attr, :org-item) read row columns."""
    ctx = make_ctx(plugins_renders, plugins_org)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins.__name__)
    register_tools_from_module(ctx, plugins_sql.__name__)
    db_path = _create_test_db(tmp_path / "test.db")
    queries = [
        (f'read_sql "{db_path}" --table=users, :fmt {{name}}', ["Alice", "Bob"]),
        (f'read_sql "{db_path}" --table=users, :attr name', ["Alice", "Bob"]),
        (f'read_sql "{db_path}" --table=users, :org-item id name', ["- 1 :: Alice", "- 2 :: Bob"]),
    ]
    for query, expected in queries:
        _forest, _attrs, _render_specs, out = qp.execute_query(query)
        assert out.strip().split("\n") == expected, query


def test_sql_row_content_attribute(make_ctx, tmp_path):
    """Test sql_row_content attribute extracts formatted row."""
    ctx = make_ctx(plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_builtins.__name__)
    register_tools_from_module(ctx, plugins_sql.__name__)

    db_path = _create_test_db(tmp_path / "test.db")
    forest, _attrs, _render_specs, _out = qp.execute_query(f'read_sql "{db_path}" --table=users, sql_row_content')

    storage = ctx.container.get(AttributeStorageAPI)
    at_d = AttributeDescriptor.create("sql_row_content")
    values = [storage.get_attr_value(at_d, item) for _depth, item in forest.as_pairs()]
    assert values == [
        "| 1 | Alice | 30 | NYC |",
        "| 2 | Bob | 25 | LA |",
    ]
