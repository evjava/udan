"""Test helper functions for udan tests."""

from udan.core.api_constants import NODE_ROOT_ITEM
from udan.core.api_forests import Node
from udan.core.api_query_processor import QueryProcessorAPI
from udan.core.impl_udan_context import UdanContext
from udan.parsing.impl_utils_parsing import parse_tree


def parse_and_interpret(ctx: UdanContext, tree: str) -> Node | None:
    """Parse and interpret a tree string.

    ⚠️ **ARCHITECTURAL DEBT**: This is a temporary workaround that should be eliminated.

    **Why this is bad**: Test flow should mimic real usage flow. Instead of directly
    calling private implementation methods, tests should use the public API
    (QueryProcessorAPI._resolve_query()) just like real code does.

    **Future fix**: Add a public method to QueryProcessorAPI (e.g., `interpret_node()`)
    that properly exposes query interpretation without relying on private methods.
    See analysis: 2026-03-22--18-31--interpret-query-architectural-issue-analysis.md

    Args:
        ctx: The engine context the processor is resolved over
        tree: The tree string to parse and interpret

    Returns:
        The interpreted Node, or None if interpretation fails or debug mode consumed it
    """
    processor = ctx.container.get(QueryProcessorAPI)
    exec_ctx = ctx.create_exec_context()
    node = parse_tree(tree)
    if node.item == NODE_ROOT_ITEM and len(node.children) == 1:
        child = node.children[0]
        # Handle CHAIN nodes: validate and unwrap
        if isinstance(child.item, str) and child.item == "CHAIN":
            processor._validate_chain(child.children)
            # Interpret first item in chain (single-node interpretation)
            return processor._interpret_query(child.children[0], [], [], last_operator=[], ctx=exec_ctx)
        return processor._interpret_query(child, [], [], last_operator=[], ctx=exec_ctx)
    elif node.item == NODE_ROOT_ITEM and len(node.children) > 1:
        # Interpret each child separately and return a ROOT node with interpreted children
        interpreted_children = []
        for child in node.children:
            # Handle CHAIN nodes: validate and unwrap
            if isinstance(child.item, str) and child.item == "CHAIN":
                processor._validate_chain(child.children)
                for chain_item in child.children:
                    interpreted_child = processor._interpret_query(chain_item, [], [], last_operator=[], ctx=exec_ctx)
                    if interpreted_child is not None:
                        interpreted_children.append(interpreted_child)
            else:
                interpreted_child = processor._interpret_query(child, [], [], last_operator=[], ctx=exec_ctx)
                if interpreted_child is not None:
                    interpreted_children.append(interpreted_child)
        return Node(item=NODE_ROOT_ITEM, children=interpreted_children) if interpreted_children else None
    else:
        return processor._interpret_query(node, [], [], last_operator=[], ctx=exec_ctx)


def parse_and_resolve(ctx: UdanContext, tree: str):
    """Parse and fully resolve a query string using resolve_query.

    This mimics the real usage flow (parse -> resolve_query) and includes
    chain validation. Use this for tests that need the full resolution pipeline.

    Args:
        ctx: UdanContext instance
        tree: The query string to parse and resolve

    Returns:
        Tuple of (forest, attribute_descriptors, render_descriptors)

    Raises:
        ExceptionWithAdvice: If chain validation fails or other errors occur
    """
    processor = ctx.container.get(QueryProcessorAPI)
    node = parse_tree(tree, unwrap_single_roots=False)
    return processor.resolve_query(node, ctx.create_exec_context())
