"""Tests for JSON query plugins."""

import json
from datetime import datetime

import udan.plugins_tools_examples.plugins_json
from tests.conftest import make_qp, register_tools_from_module
from udan.plugins_tools_examples.plugins_json import (
    as_json,
    read_json,
    read_json_chunks,
    render_json,
    resolve_json_path,
)

# ── resolve_json_path tests ──


def test_resolve_root():
    """Path '.' returns the data wrapped in a list."""
    data = {"a": 1}
    assert resolve_json_path(data, ".") == [data]


def test_resolve_dict_key():
    """Path '.key' extracts a dict value."""
    assert resolve_json_path({"x": 42}, ".x") == [42]


def test_resolve_nested_keys():
    """Path '.a.b' navigates nested dicts."""
    data = {"a": {"b": 99}}
    assert resolve_json_path(data, ".a.b") == [99]


def test_resolve_missing_key():
    """Missing key returns empty list."""
    assert resolve_json_path({"x": 1}, ".y") == []


def test_resolve_list_iteration():
    """Path '[]' iterates over a list."""
    data = [1, 2, 3]
    assert resolve_json_path(data, "[]") == [1, 2, 3]


def test_resolve_dict_then_iterate():
    """Path '.items[]' extracts dict value then iterates."""
    data = {"items": [10, 20]}
    assert resolve_json_path(data, ".items[]") == [10, 20]


def test_resolve_iterate_then_key():
    """Path '.repos[].id' iterates list then extracts key from each."""
    data = {"repos": [{"id": "a"}, {"id": "b"}]}
    assert resolve_json_path(data, ".repos[].id") == ["a", "b"]


def test_resolve_deep_chain():
    """Path '.a[].b[].c' navigates multiple levels of lists and dicts."""
    data = {"a": [{"b": [{"c": 1}, {"c": 2}]}, {"b": [{"c": 3}]}]}
    assert resolve_json_path(data, ".a[].b[].c") == [1, 2, 3]


def test_resolve_iterate_non_list():
    """Iterating over a non-list produces empty."""
    data = {"x": "not a list"}
    assert resolve_json_path(data, ".x[]") == []


def test_resolve_empty_data():
    """Empty dict returns empty for any key."""
    assert resolve_json_path({}, ".foo") == []


def test_resolve_key_from_list():
    """Extracting a key from a list element (not a dict) is skipped."""
    data = [{"id": "a"}, "not_a_dict", {"id": "c"}]
    assert resolve_json_path(data, "[].id") == ["a", "c"]


# ── read_json tests ──

READ_JSON_ARRAY_ITEMS = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
READ_JSON_DOCUMENT = {
    "result": {"collections": [{"name": "econ_cyberleninka"}, {"name": "finance_cyberleninka"}]},
    "status": "ok",
}


def test_insert_json_array(tmp_path):
    """read_json inserts one item per array entry."""
    filepath = tmp_path / "test_array.json"
    filepath.write_text(json.dumps(READ_JSON_ARRAY_ITEMS))

    result = read_json(filepath)
    assert result == READ_JSON_ARRAY_ITEMS


def test_insert_json_object_single_item(tmp_path):
    """read_json inserts an object file as one item holding the whole JSON element."""
    filepath = tmp_path / "test_object.json"
    filepath.write_text(json.dumps(READ_JSON_DOCUMENT))

    result = read_json(filepath)
    assert result == [READ_JSON_DOCUMENT]


def test_insert_json_scalar(tmp_path):
    """read_json inserts a scalar file as one item."""
    filepath = tmp_path / "test_scalar.json"
    filepath.write_text(json.dumps(42))

    result = read_json(filepath)
    assert result == [42]


def test_insert_json_array_list_false(tmp_path):
    """read_json with list=False inserts an array file as one item."""
    filepath = tmp_path / "test_array_no_expand.json"
    filepath.write_text(json.dumps(READ_JSON_ARRAY_ITEMS))

    result = read_json(filepath, list=False)
    assert result == [READ_JSON_ARRAY_ITEMS]


def test_insert_json_object_list_false(tmp_path):
    """read_json with list=False inserts an object file as one item."""
    filepath = tmp_path / "test_object_no_expand.json"
    filepath.write_text(json.dumps(READ_JSON_DOCUMENT))

    result = read_json(filepath, list=False)
    assert result == [READ_JSON_DOCUMENT]


def test_insert_jsonl_lines(tmp_path):
    """read_json inserts one item per non-empty jsonl line."""
    filepath = tmp_path / "test_lines.jsonl"
    filepath.write_text('{"id": 1}\n\n{"id": 2}\n')

    result = read_json(filepath)
    assert result == [{"id": 1}, {"id": 2}]


def test_insert_jsonl_scalar_lines(tmp_path):
    """read_json inserts one item per jsonl line holding a scalar."""
    filepath = tmp_path / "test_lines_scalar.jsonl"
    filepath.write_text("1\n2\n3\n")

    result = read_json(filepath)
    assert result == [1, 2, 3]


def test_insert_jsonl_array_lines_expand(tmp_path):
    """read_json expands a jsonl line holding a JSON array into items."""
    filepath = tmp_path / "test_lines_array.jsonl"
    filepath.write_text("[1, 2]\n[3]\n")

    result = read_json(filepath)
    assert result == [1, 2, 3]


def test_insert_jsonl_array_lines_list_false(tmp_path):
    """read_json with list=False keeps a jsonl array line as one item."""
    filepath = tmp_path / "test_lines_array_no_expand.jsonl"
    filepath.write_text("[1, 2]\n[3]\n")

    result = read_json(filepath, list=False)
    assert result == [[1, 2], [3]]


def test_insert_json_string_path(tmp_path):
    """read_json accepts string path."""
    filepath = tmp_path / "test_str.json"
    filepath.write_text(json.dumps([1, 2, 3]))

    result = read_json(str(filepath))
    assert result == [1, 2, 3]


def test_insert_json_path_object(tmp_path):
    """read_json accepts Path object."""
    filepath = tmp_path / "test_path.json"
    filepath.write_text(json.dumps([1, 2, 3]))

    result = read_json(filepath)
    assert result == [1, 2, 3]


def test_insert_json_missing_file(tmp_path):
    """read_json raises FileNotFoundError for missing file."""
    filepath = tmp_path / "nonexistent.json"
    try:
        read_json(filepath)
        assert False, "Should have raised FileNotFoundError"
    except FileNotFoundError:
        pass


def test_insert_json_missing_jsonl_file(tmp_path):
    """read_json raises FileNotFoundError for a missing jsonl file."""
    filepath = tmp_path / "nonexistent.jsonl"
    try:
        read_json(filepath)
        assert False, "Should have raised FileNotFoundError"
    except FileNotFoundError:
        pass


def test_insert_json_invalid_json(tmp_path):
    """read_json raises ValueError for invalid JSON."""
    filepath = tmp_path / "test_invalid.json"
    filepath.write_text("{invalid json}")

    try:
        read_json(filepath)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Error parsing JSON" in str(e)


def test_insert_json_invalid_jsonl(tmp_path):
    """read_json raises ValueError for an invalid jsonl line."""
    filepath = tmp_path / "test_invalid.jsonl"
    filepath.write_text('{"id": 1}\n{invalid json}\n')

    try:
        read_json(filepath)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Error parsing JSON" in str(e)


# ── as_json tests ──


def test_as_json_array_expands():
    """as_json yields one item per entry of a parsed array."""
    assert as_json(["[1, 2, 3]"]) == [1, 2, 3]


def test_as_json_object_is_single_item():
    """as_json inserts a parsed object as one item."""
    assert as_json(['{"id": 1, "name": "Alice"}']) == [{"id": 1, "name": "Alice"}]


def test_as_json_scalar_is_single_item():
    """as_json inserts a parsed scalar as one item."""
    assert as_json(["42"]) == [42]


def test_as_json_empty_array_yields_none():
    """as_json yields no items for an empty array."""
    assert as_json(["[]"]) == []


def test_as_json_nested_array_stays_one_item():
    """as_json keeps a nested array inside an array as one item."""
    assert as_json(["[[1, 2], 3]"]) == [[1, 2], 3]


def test_as_json_several_items():
    """as_json parses every item and concatenates the results."""
    assert as_json(["[1, 2]", '{"id": 3}', "4"]) == [1, 2, {"id": 3}, 4]


def test_as_json_array_list_false():
    """as_json with list=False inserts a parsed array as one item."""
    assert as_json(["[1, 2, 3]"], list=False) == [[1, 2, 3]]


def test_as_json_object_list_false():
    """as_json with list=False keeps an object a single item."""
    assert as_json(['{"id": 1}'], list=False) == [{"id": 1}]


def test_as_json_invalid_json():
    """as_json raises ValueError for invalid JSON."""
    try:
        as_json(["{invalid json}"])
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Error parsing JSON" in str(e)


def test_as_json_non_string_item():
    """as_json raises ValueError for an item that is not a string."""
    try:
        as_json([42])
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Error parsing JSON" in str(e)


# ── read_json_chunks tests ──


def test_read_json_chunks_default_path(tmp_path):
    """read_json_chunks with default path '.' returns entire document."""
    filepath = tmp_path / "test_rows_default.json"
    filepath.write_text(json.dumps([{"id": 1}, {"id": 2}]))

    result = read_json_chunks(filepath)
    assert isinstance(result, list)
    assert len(result) == 2


def test_read_json_chunks_dict_default_path(tmp_path):
    """read_json_chunks wraps dict in list when using default path."""
    filepath = tmp_path / "test_rows_dict.json"
    filepath.write_text(json.dumps({"name": "test"}))

    result = read_json_chunks(filepath)
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["name"] == "test"


def test_read_json_chunks_extract_array(tmp_path):
    """read_json_chunks with .users[] extracts array elements."""
    filepath = tmp_path / "test_rows_array.json"
    filepath.write_text(json.dumps({"users": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]}))

    result = read_json_chunks(filepath, jq_filter=".users[]")
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["name"] == "Alice"
    assert result[1]["name"] == "Bob"


def test_read_json_chunks_extract_field(tmp_path):
    """read_json_chunks with .users[].name extracts specific field."""
    filepath = tmp_path / "test_rows_field.json"
    filepath.write_text(json.dumps({"users": [{"name": "Alice"}, {"name": "Bob"}]}))

    result = read_json_chunks(filepath, jq_filter=".users[].name")
    assert result == ["Alice", "Bob"]


def test_read_json_chunks_nested_path(tmp_path):
    """read_json_chunks with nested path extracts nested values."""
    filepath = tmp_path / "test_rows_nested.json"
    filepath.write_text(json.dumps({"data": {"items": [{"value": 1}, {"value": 2}]}}))

    result = read_json_chunks(filepath, jq_filter=".data.items[]")
    assert len(result) == 2
    assert result[0]["value"] == 1
    assert result[1]["value"] == 2


def test_read_json_chunks_missing_path(tmp_path):
    """read_json_chunks returns empty list for non-matching path."""
    filepath = tmp_path / "test_rows_missing.json"
    filepath.write_text(json.dumps({"users": []}))

    result = read_json_chunks(filepath, jq_filter=".nonexistent[]")
    assert result == []


def test_read_json_chunks_object_default_path(tmp_path):
    """read_json_chunks with default path inserts an object file as one item."""
    filepath = tmp_path / "test_rows_object.json"
    filepath.write_text(json.dumps(READ_JSON_DOCUMENT))

    result = read_json_chunks(filepath)
    assert result == [READ_JSON_DOCUMENT]


def test_read_json_chunks_jsonl(tmp_path):
    """read_json_chunks filters every jsonl line and concatenates the matches."""
    filepath = tmp_path / "test_rows.jsonl"
    filepath.write_text('{"users": [{"id": 1}]}\n{"users": [{"id": 2}]}\n')

    result = read_json_chunks(filepath, jq_filter=".users[]")
    assert result == [{"id": 1}, {"id": 2}]


def test_read_json_chunks_jsonl_default_path(tmp_path):
    """read_json_chunks with default path inserts one item per jsonl line."""
    filepath = tmp_path / "test_rows_lines.jsonl"
    filepath.write_text('{"id": 1}\n{"id": 2}\n')

    result = read_json_chunks(filepath)
    assert result == [{"id": 1}, {"id": 2}]


# ── json_glob alias tests ──


def test_json_glob_alias_resolves_to_read_json_chunks(make_ctx, tmp_path):
    """json_glob alias resolves to the same function as read_json_chunks."""
    ctx = make_ctx()
    register_tools_from_module(ctx, udan.plugins_tools_examples.plugins_json.__name__, verbose=False)

    fn_alias = ctx.registry.get_function("json_glob")
    fn_canonical = ctx.registry.get_function("read_json_chunks")
    assert fn_alias is not None
    assert fn_alias is fn_canonical


def test_json_glob_alias_callable(make_ctx, tmp_path):
    """json_glob alias works end-to-end for extraction."""
    ctx = make_ctx()
    register_tools_from_module(ctx, udan.plugins_tools_examples.plugins_json.__name__, verbose=False)

    filepath = tmp_path / "test_alias.json"
    filepath.write_text(json.dumps({"items": [{"id": "a"}, {"id": "b"}]}))

    fn_alias = ctx.registry.get_function("json_glob")
    result = fn_alias(str(filepath), jq_filter=".items[].id")
    assert result == ["a", "b"]


# ── render_json tests ──

RENDER_JSON_NOTE = """{
  "title": "Test Note",
  "tags": [
    "tag1",
    "tag2"
  ],
  "line_start": 10
}"""


def test_render_json_renders_dict():
    """render_json serializes a dict as pretty-printed JSON."""
    item = {"title": "Test Note", "tags": ["tag1", "tag2"], "line_start": 10}
    assert render_json(item) == RENDER_JSON_NOTE


def test_render_json_keeps_unknown_fields():
    """render_json serializes the dict as-is, no fields are dropped or added."""
    item = {"title": "Note", "custom_field": 42}
    assert json.loads(render_json(item)) == {"title": "Note", "custom_field": 42}


def test_render_json_non_serializable_values():
    """render_json stringifies values json cannot serialize (datetime, tuple)."""
    item = {"create_date": datetime(2023, 7, 21, 1, 20, 9), "tags": ("python",)}
    assert json.loads(render_json(item)) == {"create_date": "2023-07-21 01:20:09", "tags": ["python"]}


def test_render_json_fields_positional():
    """render_json shows only the fields passed as separate arguments, in the given order."""
    item = {"title": "Note", "tags": ["tag1"], "line_start": 10}
    assert json.loads(render_json(item, "line_start", "title")) == {"line_start": 10, "title": "Note"}


def test_render_json_fields_comma_string_and_missing():
    """render_json accepts a comma-separated fields string and skips missing fields."""
    item = {"title": "Note", "tags": ["tag1"]}
    rendered = render_json(item, " title, line_start ")
    assert json.loads(rendered) == {"title": "Note"}


def test_render_json_fields_query(tmp_path, make_ctx):
    """:json field1 field2 shows only those fields through query execution."""
    data_file = tmp_path / "data.json"
    data_file.write_text(json.dumps([{"title": "Note", "tags": ["tag1"], "line_start": 10}]))

    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, udan.plugins_tools_examples.plugins_json.__name__, verbose=False)
    _forest, _attrs, _render_specs, out = qp.execute_query(f'read_json "{data_file}", :json title line_start')

    assert json.loads(out) == {"title": "Note", "line_start": 10}


def test_render_json_query_all_fields(tmp_path, make_ctx):
    """:json without field arguments shows all fields through query execution."""
    data_file = tmp_path / "data.json"
    data_file.write_text(json.dumps([{"title": "Note", "custom_field": 42}]))

    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, udan.plugins_tools_examples.plugins_json.__name__, verbose=False)
    _forest, _attrs, _render_specs, out = qp.execute_query(f'read_json "{data_file}", :json')

    assert json.loads(out) == {"title": "Note", "custom_field": 42}


def test_json_alias_resolves_to_render_json(make_ctx):
    """json alias resolves to the same function as render_json."""
    ctx = make_ctx()
    register_tools_from_module(ctx, udan.plugins_tools_examples.plugins_json.__name__, verbose=False)

    fn_alias = ctx.registry.get_function("json")
    fn_canonical = ctx.registry.get_function("render_json")
    assert fn_alias is not None
    assert fn_alias is fn_canonical


# ── read_json query tests ──


def _make_json_ctx(make_ctx):
    """Build a context with the json plugin registered."""
    ctx = make_ctx()
    register_tools_from_module(ctx, udan.plugins_tools_examples.plugins_json.__name__, verbose=False)
    return ctx


def test_read_json_query_object_is_single_item(tmp_path, make_ctx):
    """read_json inserts an object file as a single item with the whole JSON element."""
    data_file = tmp_path / "data.json"
    data_file.write_text(json.dumps(READ_JSON_DOCUMENT))

    forest, _attrs, _render_specs, _out = make_qp(_make_json_ctx(make_ctx)).execute_query(f'read_json "{data_file}"')

    assert forest.items == [READ_JSON_DOCUMENT]


def test_read_json_query_array_inserts_many(tmp_path, make_ctx):
    """read_json inserts one item per entry of an array file."""
    data_file = tmp_path / "data.json"
    data_file.write_text(json.dumps(READ_JSON_ARRAY_ITEMS))

    forest, _attrs, _render_specs, _out = make_qp(_make_json_ctx(make_ctx)).execute_query(f'read_json "{data_file}"')

    assert forest.items == READ_JSON_ARRAY_ITEMS


def test_read_json_query_list_false_inserts_one(tmp_path, make_ctx):
    """read_json list=False inserts an array file as a single item."""
    data_file = tmp_path / "data.json"
    data_file.write_text(json.dumps(READ_JSON_ARRAY_ITEMS))

    forest, _attrs, _render_specs, _out = make_qp(_make_json_ctx(make_ctx)).execute_query(
        f'read_json "{data_file}" list=False'
    )

    assert forest.items == [READ_JSON_ARRAY_ITEMS]


def test_read_json_query_object_render_json(tmp_path, make_ctx):
    """:json renders the single item of an object file as the whole JSON element."""
    data_file = tmp_path / "data.json"
    data_file.write_text(json.dumps(READ_JSON_DOCUMENT))

    _forest, _attrs, _render_specs, out = make_qp(_make_json_ctx(make_ctx)).execute_query(
        f'read_json "{data_file}", :json'
    )

    assert json.loads(out) == READ_JSON_DOCUMENT


def test_read_json_query_jsonl_inserts_many(tmp_path, make_ctx):
    """read_json inserts one item per jsonl line through query execution."""
    data_file = tmp_path / "data.jsonl"
    data_file.write_text('{"id": 1}\n{"id": 2}\n')

    forest, _attrs, _render_specs, _out = make_qp(_make_json_ctx(make_ctx)).execute_query(f'read_json "{data_file}"')

    assert forest.items == [{"id": 1}, {"id": 2}]


# ── as_json query tests ──


def test_as_json_query_string_literal_expands(make_ctx):
    """as_json replaces a quoted string with the entries of the parsed array."""
    forest, _attrs, _render_specs, _out = make_qp(_make_json_ctx(make_ctx)).execute_query('"[1, 2, 3]", as_json')

    assert forest.items == [1, 2, 3]


def test_as_json_query_string_literal_list_false(make_ctx):
    """as_json list=False replaces a quoted string with the whole parsed array."""
    forest, _attrs, _render_specs, _out = make_qp(_make_json_ctx(make_ctx)).execute_query(
        '"[1, 2, 3]", as_json list=False'
    )

    assert forest.items == [[1, 2, 3]]


def test_as_json_query_object(make_ctx):
    """as_json replaces a quoted string with the parsed object."""
    forest, _attrs, _render_specs, _out = make_qp(_make_json_ctx(make_ctx)).execute_query("'{\"id\": 1}', as_json")

    assert forest.items == [{"id": 1}]
