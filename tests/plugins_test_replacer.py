"""Test tools for the replacer plugin's tests.

Flat and nested replacers with deterministic output, so the applier's two branches
can be asserted exactly.
"""

from typing import Any

from udan.core_tools_loading.api_annotated import annotated


@annotated(meta={"tool_type": "replacer"})
def replacer_upper(items: list[Any]) -> list[str]:
    """Replacer that upper-cases the level's items."""
    return [str(item).upper() for item in items]


@annotated(meta={"tool_type": "replacer", "is_nested": True})
def replacer_depths(nodes: list[Any]) -> list[tuple[int, Any]]:
    """Nested replacer returning the subtree's items at their depths, unchanged."""
    results = []

    def traverse(node_list: list[Any], depth: int) -> None:
        for node in node_list:
            results.append((depth, node.item))
            if node.children:
                traverse(node.children, depth + 1)

    traverse(nodes, 0)
    return results
