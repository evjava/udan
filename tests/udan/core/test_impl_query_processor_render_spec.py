"""Tests for render specification handling in QueryProcessor."""

import pytest

from udan.core.api_constants import DEBUG, NODE_ROOT_ITEM
from udan.core.api_exceptions import ExceptionWithAdvice
from udan.core.api_forests import Node
from udan.core.api_query_processor import QueryMiss, QueryProcessorAPI
from udan.renders import plugins_renders
from udan.renders.api_renders import RenderDescriptor


@pytest.fixture
def handler(make_ctx):
    """Create the QueryProcessor whose render spec handling is under test."""
    ctx = make_ctx(plugins_renders)
    return ctx.container.get(QueryProcessorAPI)


@pytest.fixture
def exec_ctx(make_ctx):
    """Exec context for query-time logging in direct handler calls."""
    return make_ctx(plugins_renders).create_exec_context()


def test_get_expected_render_args_for_attr(handler):
    """Test that attr render expects 1 argument."""
    assert handler._get_expected_render_args("attr") == 1


def test_get_expected_render_args_for_unknown_render(handler):
    """Test that unknown render returns 0."""
    assert handler._get_expected_render_args("unknown_render_xyz") == 0


def test_get_expected_render_args_for_list_render(handler):
    """Test that list render expects 0 args (aggregate render)."""
    # list is an aggregate render with shape="children"
    assert handler._get_expected_render_args("list") == 0


def test_validate_render_name_with_valid_render(handler):
    """Test that valid render names pass validation."""
    # Should not raise exception - use raw which is a valid render alias
    handler._validate_render_name("raw")


def test_validate_render_name_with_attr_special_case(handler):
    """Test that attr render is always valid (special case)."""
    handler._validate_render_name("attr")


def test_validate_render_name_with_invalid_render(handler):
    """An unknown render name is a miss carrying the fragment and the kind."""
    with pytest.raises(QueryMiss) as exc_info:
        handler._validate_render_name("nonexistent_render")

    # What answers it is the answerers' decision; the miss carries the data
    assert exc_info.value.pattern == "nonexistent_render"
    assert exc_info.value.tool_type == "render"


def test_resolve_render_name_exact(handler, exec_ctx):
    """Exact render keys (name or alias) are returned as is."""
    assert handler._resolve_render_name("render_format", exec_ctx) == "render_format"
    assert handler._resolve_render_name("fmt", exec_ctx) == "fmt"


def test_resolve_render_name_substring_same_render(handler, exec_ctx):
    """Short name matching a render and its alias resolves to the shortest key."""
    assert handler._resolve_render_name("term", exec_ctx) == "term-list-item"


def test_resolve_render_name_substring_unknown(handler, exec_ctx):
    """Name matching no render is returned unchanged for _validate_render_name to report."""
    assert handler._resolve_render_name("nonexistent_render", exec_ctx) == "nonexistent_render"


def test_resolve_render_name_substring_ambiguous(handler, exec_ctx):
    """Name matching several renders is a miss narrowed to the matches."""
    with pytest.raises(QueryMiss) as exc_info:
        handler._resolve_render_name("aggregate", exec_ctx)

    assert exc_info.value.pattern == "aggregate"
    assert exc_info.value.tool_type == "render"
    assert "ambiguous render 'aggregate'" in exc_info.value.reason


def test_resolve_render_name_prefers_unique_prefix(handler, exec_ctx):
    """A fragment that prefixes exactly one of several matches resolves to it.

    `list-i` substring-matches both `list-item` and `term-list-item`; only
    `list-item` starts with it, so the prefix match wins over the ambiguity listing.
    """
    assert handler._resolve_render_name("list-i", exec_ctx) == "list-item"


def test_resolve_render_name_multiple_prefixes_stay_ambiguous(handler, exec_ctx):
    """Several prefix matches keep the miss: there is no single one to name."""
    with pytest.raises(QueryMiss) as exc_info:
        handler._resolve_render_name("render_", exec_ctx)

    assert exc_info.value.pattern == "render_"
    assert "ambiguous render 'render_'" in exc_info.value.reason


def test_collect_render_args_from_children_basic(handler):
    """Test collecting basic render args from children."""
    query_node = Node(item=NODE_ROOT_ITEM, children=[Node.leaf("arg1"), Node.leaf("arg2")])
    tools_keys = list(handler._registry.get_tools())
    render_args, consumed = handler._collect_render_args_from_children(query_node, 2, tools_keys, 0)
    assert render_args == ["arg1", "arg2"]
    assert consumed == 2


def test_collect_render_args_consumes_until_limit(handler):
    """Test that arg collection stops when expected number of args is reached."""
    query_node = Node(
        item=NODE_ROOT_ITEM,
        children=[
            Node.leaf("arg1"),
            Node.leaf("arg2"),
            Node.leaf("arg3"),
        ],
    )
    tools_keys = list(handler._registry.get_tools())
    render_args, consumed = handler._collect_render_args_from_children(query_node, 2, tools_keys, 0)
    assert render_args == ["arg1", "arg2"]
    assert consumed == 2


def test_collect_render_args_includes_named_args(handler):
    """Test that named args (--key=value) are always consumed."""
    query_node = Node(
        item=NODE_ROOT_ITEM,
        children=[
            Node.leaf("--field=name"),
            Node.leaf("--format=json"),
        ],
    )
    tools_keys = list(handler._registry.get_tools())
    render_args, consumed = handler._collect_render_args_from_children(query_node, 0, tools_keys, 0)
    assert render_args == ["--field=name", "--format=json"]
    assert consumed == 2


def test_collect_render_args_positional_fallback(handler):
    """Test that a single non-operator child is consumed as positional arg."""
    query_node = Node(item=NODE_ROOT_ITEM, children=[Node.leaf("myfield")])
    tools_keys = list(handler._registry.get_tools())
    render_args, consumed = handler._collect_render_args_from_children(query_node, 0, tools_keys, 0)
    assert render_args == ["myfield"]
    assert consumed == 1


def test_handle_render_spec_non_string(handler, exec_ctx):
    """Test handle_render_spec with non-string item."""
    result = handler._handle_render_spec(123, [], Node.leaf("x"), [], exec_ctx)
    assert result is None


def test_handle_render_spec_no_colon_prefix(handler, exec_ctx):
    """Test handle_render_spec with string not starting with colon."""
    result = handler._handle_render_spec("regular", [], Node.leaf("x"), [], exec_ctx)
    assert result is None


def test_handle_render_spec_empty_colon(handler, exec_ctx):
    """A bare `:` in argument position is a render-kind miss."""
    query_node = Node.leaf("x")
    # Chain-position `:` is lowered by the sugar; this argument-position survivor
    # is a miss, and the registered answerers decide what the query continues with
    with pytest.raises(QueryMiss) as exc_info:
        handler._handle_render_spec(":", [], query_node, [], exec_ctx)

    assert exc_info.value.pattern == ""
    assert exc_info.value.tool_type == "render"


def test_handle_render_spec_empty_after_colon(handler, exec_ctx):
    """Test handle_render_spec with just colon followed by space."""
    query_node = Node.leaf("x")
    with pytest.raises(ExceptionWithAdvice) as exc_info:
        handler._handle_render_spec(": ", [], query_node, [], exec_ctx)
    assert "Render spec cannot be empty" in str(exc_info.value)


def test_handle_render_spec_basic(handler, exec_ctx):
    """Test basic render spec handling."""

    query_node = Node.leaf("x")
    render = []
    result = handler._handle_render_spec(":list", render, query_node, [], exec_ctx)
    assert any(isinstance(r, RenderDescriptor) and r.name == "list" for r in render)
    assert result is None  # No children remaining


def test_handle_render_spec_with_inline_args(handler, exec_ctx):
    """Test render spec with inline arguments."""

    query_node = Node.leaf("x")
    render = []
    handler._handle_render_spec(":table id name", render, query_node, [], exec_ctx)
    assert any(isinstance(r, RenderDescriptor) and r.name == "table" and r.args == ("id", "name") for r in render)


def test_handle_render_spec_insufficient_args(handler, exec_ctx):
    """Test render spec with insufficient arguments."""
    # attr render expects 1 argument
    query_node = Node(item=NODE_ROOT_ITEM, children=[])
    render = []
    with pytest.raises(ExceptionWithAdvice) as exc_info:
        handler._handle_render_spec(":attr", render, query_node, [], exec_ctx)
    assert "expects 1 arguments, got 0" in str(exc_info.value)


def test_handle_render_spec_with_children_args(handler, exec_ctx):
    """Test render spec collecting args from children."""
    query_node = Node(item=NODE_ROOT_ITEM, children=[Node.leaf("field1")])
    render = []
    result = handler._handle_render_spec(":attr", render, query_node, [], exec_ctx)
    assert "attr" in str(render)
    assert result is None  # Child consumed


def test_handle_render_spec_with_remaining_children(handler, exec_ctx):
    """Test render spec leaves remaining children for further processing."""
    query_node = Node(
        item=NODE_ROOT_ITEM,
        children=[Node.leaf("arg1"), Node.leaf("remaining_op")],
    )
    render = []
    result = handler._handle_render_spec(":list", render, query_node, [], exec_ctx)
    assert result is not None
    assert result.item == "remaining_op"


def test_try_handle_render_spec_with_render_spec(handler, exec_ctx):
    """Test _try_handle_render_spec detects render specs."""
    query_node = Node.leaf(":list")
    render = []
    last_operator = []
    tools_keys = list(handler._registry.get_tools())
    handled, result = handler._try_handle_render_spec(
        query_node,
        [],
        render,
        last_operator,
        tools_keys,
        lambda n, a, r, last_op: n,
        exec_ctx,
    )
    assert handled is True
    assert any(isinstance(r, RenderDescriptor) and r.name == "list" for r in render)


def test_try_handle_render_spec_validates_invalid_renders(handler, exec_ctx):
    """Test _try_handle_render_spec raises exception for invalid renders."""
    query_node = Node.leaf(":nonexistent_render")
    render = []
    last_operator = []
    tools_keys = list(handler._registry.get_tools())
    # Invalid render specs are misses the registered answerers answer
    with pytest.raises(QueryMiss):
        handler._try_handle_render_spec(
            query_node,
            [],
            render,
            last_operator,
            tools_keys,
            lambda n, a, r, last_op: n,
            exec_ctx,
        )


def test_try_handle_render_spec_does_not_handle_debug_marker(handler, make_ctx):
    """DEBUG marker is not a render spec; it is handled per-query by the query processor."""
    ctx = make_ctx(plugins_renders)
    query_node = Node.leaf(DEBUG)
    render = []
    last_operator = []
    tools_keys = list(handler._registry.get_tools())
    exec_ctx = ctx.create_exec_context()
    handled, result = handler._try_handle_render_spec(
        query_node,
        [],
        render,
        last_operator,
        tools_keys,
        lambda n, a, r, last_op: n,
        exec_ctx,
    )
    assert handled is False
    assert result is None
    # Render spec handling must not flip debug mode on the exec context
    assert exec_ctx.is_debug is False


def test_try_handle_render_spec_no_match(handler, exec_ctx):
    """Test _try_handle_render_spec with non-render item."""
    query_node = Node.leaf("regular_item")
    render = []
    last_operator = []
    tools_keys = list(handler._registry.get_tools())
    handled, result = handler._try_handle_render_spec(
        query_node,
        [],
        render,
        last_operator,
        tools_keys,
        lambda n, a, r, last_op: n,
        exec_ctx,
    )
    assert handled is False
    assert result is None


def test_filter_render_specs_from_children(handler, exec_ctx):
    """Test filtering render specs from children."""

    render = []
    children = [
        Node.leaf("regular"),
        Node.leaf(":list"),
        Node.leaf("another"),
        Node.leaf(":fmt"),
    ]
    filtered = handler._filter_render_specs_from_children(children, render, exec_ctx)
    assert len(filtered) == 2
    assert filtered[0].item == "regular"
    assert filtered[1].item == "another"
    assert any(isinstance(r, RenderDescriptor) and r.name == "list" for r in render)
    assert any(isinstance(r, RenderDescriptor) and r.name == "fmt" for r in render)


def test_collect_supported_renders_empty_tree(handler):
    """Test collecting supported renders from empty tree."""
    node = Node.leaf("test")
    renders = handler._collect_supported_renders(node)
    assert renders == []


def test_collect_supported_renders_from_simple_node(handler):
    """Test collecting supported renders from a simple node tree."""
    # Create a tree with leaf nodes (no operators)
    node = Node(item=NODE_ROOT_ITEM, children=[Node.leaf("child1"), Node.leaf("child2")])
    renders = handler._collect_supported_renders(node)
    assert renders == []
