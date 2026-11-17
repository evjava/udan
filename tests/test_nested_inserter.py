"""Tests for nested inserter functionality.

This module tests the is_nested feature of inserters, which allows them
to return Iterable[tuple[int, Item]] to build tree structures.
"""

import sys

import pytest

from udan.attributes import plugins_operators_attribute
from udan.attributes.api_attribute_runtime import AttributeRuntimeAPI
from udan.attributes.api_attribute_storage import AttributeStorageAPI
from udan.attributes.impl_attribute_runtime import AttributesContext
from udan.core.api_constants import NODE_ROOT_ITEM
from udan.core.api_forests import Node
from udan.core.api_operators import OperatorDescriptor
from udan.core.api_query_processor import QueryProcessorAPI
from udan.core.impl_udan_context import UdanContext
from udan.core_tools_loading.api_annotated import annotated
from udan.core_tools_loading.impl_tools_loader import ToolsLoader
from udan.operator.api_operator_engine import OperatorsEngineAPI
from udan.parsing.impl_utils_parsing import parse_tree
from udan.plugins_history import plugins_history
from udan.plugins_tools_core import plugins_system
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.plugins_tools_examples import plugins_builtins
from udan.renders import plugins_renders


@annotated(meta={"tool_type": "inserter", "is_nested": True})
def insert_nested_123() -> list[tuple[int, int]]:
    """Insert a nested tree structure: 1 -> 2 -> 3.

    Returns:
        List of (depth, item) pairs representing the tree structure
    """
    return [(0, 1), (1, 2), (2, 3)]


@annotated(meta={"tool_type": "inserter", "is_nested": True})
def insert_nested_multiple() -> list[tuple[int, str]]:
    """Insert a nested tree with multiple top-level items.

    Returns:
        List of (depth, item) pairs representing a tree with multiple roots
    """
    return [(0, "a"), (0, "b"), (1, "c")]


@annotated(meta={"tool_type": "inserter", "is_nested": True})
def insert_nested_complex() -> list[tuple[int, str]]:
    """Insert a complex nested tree structure.

    Returns:
        List of (depth, item) pairs representing a complex tree
    """
    return [
        (0, "root1"),
        (1, "child1"),
        (2, "grandchild1"),
        (1, "child2"),
        (0, "root2"),
        (1, "child3"),
    ]


def apply_operator(ctx: UdanContext, tree: str) -> Node:
    """Helper to parse, interpret, and apply an operator."""
    node = parse_tree(tree)
    processor = ctx.container.get(QueryProcessorAPI)
    exec_ctx = ctx.create_exec_context()
    last_operator: list[OperatorDescriptor] = []
    if node.item == NODE_ROOT_ITEM and len(node.children) == 1:
        op_node = processor._interpret_query(node.children[0], [], [], last_operator, exec_ctx)
    else:
        op_node = processor._interpret_query(node, [], [], last_operator, exec_ctx)

    # Apply the operator
    context = AttributesContext(
        attribute_runtime=ctx.container.get(AttributeRuntimeAPI),
        attribute_storage=ctx.container.get(AttributeStorageAPI),
        ctx=exec_ctx,
    )
    operator = _engine(ctx)._resolve_operator(op_node.item)
    result = list(operator.apply(exec_ctx, context, []))

    # Return the first (and should be only) result node
    assert len(result) == 1
    return result[0]


@pytest.fixture
def ctx_with_nested_inserters(make_ctx):
    """Fixture that provides an UdanContext with nested inserters registered."""
    ctx = make_ctx(
        plugins_demo,
        plugins_fruits,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_system,
        plugins_history,
        plugins_renders,
    )
    test_module = sys.modules[__name__]
    loader = ToolsLoader(cache_dir=None, use_cache=False)
    metadata_fns = loader.load_from_module(test_module)
    ctx._register_many_metadatas(metadata_fns)
    return ctx


def test_nested_simple(ctx_with_nested_inserters: UdanContext):
    """Test simple nested insertion: 1 -> 2 -> 3."""
    root = apply_operator(ctx_with_nested_inserters, "insert_nested_123")

    # Convert to forest and check structure
    forest = root.convert_to_forest()
    # Note: convert_to_forest skips the root node
    # Forest contains children starting at depth 0
    assert forest.items == [2, 3]
    assert forest.depths == [0, 1]


def test_nested_multiple_roots(ctx_with_nested_inserters: UdanContext):
    """Test nested insertion with multiple top-level items.

    Note: When there are multiple roots, the inserter yields them sequentially.
    The apply_operator helper only returns the first root, so this test
    needs to be adjusted to handle multiple results.
    """
    # Parse and interpret the query
    node = parse_tree("insert_nested_multiple")
    # parse_tree wraps in ROOT, so get the child
    exec_ctx = ctx_with_nested_inserters.create_exec_context()
    last_operator: list[OperatorDescriptor] = []
    op_node = ctx_with_nested_inserters.container.get(QueryProcessorAPI)._interpret_query(
        node.children[0],
        [],
        [],
        last_operator,
        exec_ctx,
    )

    # Apply the operator and get all results
    context = AttributesContext(
        attribute_runtime=ctx_with_nested_inserters.container.get(AttributeRuntimeAPI),
        attribute_storage=ctx_with_nested_inserters.container.get(AttributeRuntimeAPI).attribute_storage,
        ctx=exec_ctx,
    )
    operator = _engine(ctx_with_nested_inserters)._resolve_operator(op_node.item)
    results = list(operator.apply(exec_ctx, context, []))

    assert len(results) == 2

    # Convert results to forests and check structure
    # Note: convert_to_forest skips the root node
    forest1 = results[0].convert_to_forest()
    assert forest1.items == []
    assert forest1.depths == []

    forest2 = results[1].convert_to_forest()
    assert forest2.items == ["c"]
    assert forest2.depths == [0]


def test_nested_complex(ctx_with_nested_inserters: UdanContext):
    """Test complex nested tree structure."""
    # Parse and interpret the query
    node = parse_tree("insert_nested_complex")
    # parse_tree wraps in ROOT, so get the child
    exec_ctx = ctx_with_nested_inserters.create_exec_context()
    last_operator: list[OperatorDescriptor] = []
    op_node = ctx_with_nested_inserters.container.get(QueryProcessorAPI)._interpret_query(
        node.children[0],
        [],
        [],
        last_operator,
        exec_ctx,
    )

    # Apply the operator and get all results
    context = AttributesContext(
        attribute_runtime=ctx_with_nested_inserters.container.get(AttributeRuntimeAPI),
        attribute_storage=ctx_with_nested_inserters.container.get(AttributeRuntimeAPI).attribute_storage,
        ctx=exec_ctx,
    )
    operator = _engine(ctx_with_nested_inserters)._resolve_operator(op_node.item)
    results = list(operator.apply(exec_ctx, context, []))

    assert len(results) == 2

    # Convert results to forests and check structure
    # Note: convert_to_forest skips the root node
    forest1 = results[0].convert_to_forest()
    assert forest1.items == ["child1", "grandchild1", "child2"]
    assert forest1.depths == [0, 1, 0]

    forest2 = results[1].convert_to_forest()
    assert forest2.items == ["child3"]
    assert forest2.depths == [0]


def _engine(ctx):
    """The operators engine, resolved from the container the fixture built."""
    return ctx.container.get(OperatorsEngineAPI)
