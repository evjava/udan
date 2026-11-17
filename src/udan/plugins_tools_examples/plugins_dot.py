"""Plugin for generating DOT (Graphviz) diagrams."""

import subprocess
from datetime import datetime

from udan.core_tools_loading.api_annotated import annotated
from udan.core_tools_loading.api_types import Edge

DOMAIN = "dot"


def _quoted(item) -> str:
    """Quote an item as a dot node name, keeping already quoted strings as they are."""
    return f'"{item}"' if not isinstance(item, str) or item[0] != '"' else item


def _dependency_edge_lines(metadata_by_pair: dict[tuple[str, str], list[str]], labels: bool) -> list[str]:
    """Render folded edges, with the collected metadata as label when labels is on."""
    lines = []
    for (source, target), metadata in sorted(metadata_by_pair.items()):
        if labels and metadata:
            label = "\\n".join(sorted(metadata))
            lines.append(f'  "{source}" -> "{target}" [label="{label}"];')
        else:
            lines.append(f'  "{source}" -> "{target}";')
    return lines


@annotated(meta={"tool_type": "replacer", "is_nested": True})
def as_dot(nodes: list, lr: bool = False, labels: bool = True) -> list:
    """Convert nested parent-children structure to full DOT digraph.

    Expects nested structure where each node has children (e.g., from fruits + similar_fruits).
    Returns a single string with complete digraph.

    Children that are Edge items (see extend_package_imports) are folded into
    source-to-target edges: several edges between the same pair merge into one, carrying
    their metadata as label. With --labels=False the merged edges stay unlabeled.

    Use :raw render to avoid bullet prefix.

    Args:
        nodes: List of Node objects with item (parent) and children
        lr: If True, set rankdir to LR (left-to-right). Default is False (top-to-bottom).
        labels: If True, folded edges carry their metadata as label. Default is True.

    Returns:
        List with depth-pair tuple containing DOT digraph string

    Examples:
        # Input from: fruits, similar_fruits, as_dot, :raw
        # Nodes: [Node(item={'name': 'apple'}, children=[Node({'name': 'strawberry'}), ...]), ...]
        # Output:
        # digraph {
        #   rankdir=TB;
        #   "apple" -> "strawberry";
        #   "apple" -> "blueberry";
        #   ...
        # }

        # For left-to-right layout:
        # fruits, similar_fruits, as_dot --lr, :raw

        # Package dependency graph, one edge per target package:
        # ls_files src, as_str, extend_package_imports, as_dot --lr, :raw

        # Same graph without the metadata labels:
        # ls_files src, as_str, extend_package_imports, as_dot --lr --labels=False, :raw
    """
    lines: list[str] = []
    standalone: list[str] = []  # nodes with no edges
    metadata_by_pair: dict[tuple[str, str], list[str]] = {}

    for node in nodes:
        if not hasattr(node, "item") or not hasattr(node, "children"):
            continue

        parent = node.item
        parent_str = _quoted(parent)

        # Create edges to all children
        has_children = False
        if node.children:
            for child_node in node.children:
                if not hasattr(child_node, "item"):
                    continue
                child = child_node.item
                if isinstance(child, Edge):
                    metadata = metadata_by_pair.setdefault((child.source, child.target), [])
                    if child.metadata is not None and child.metadata not in metadata:
                        metadata.append(child.metadata)
                    has_children = True
                    continue
                lines.append(f"  {parent_str} -> {_quoted(child)};")
                has_children = True

        if not has_children:
            standalone.append(parent_str)

    lines.extend(_dependency_edge_lines(metadata_by_pair, labels))

    # Group standalone nodes on the same rank to avoid wide layout
    if standalone:
        lines.append(f"  {{rank=same; {'; '.join(standalone)};}}")

    rankdir_value = "LR" if lr else "TB"
    rankdir_line = f"  rankdir={rankdir_value};"
    result = "digraph {\n" + rankdir_line + "\n" + "\n".join(lines) + "\n}"
    return [(1, result)]


@annotated(meta={"tool_type": "replacer", "supported_renders": ["lines-item"]})
def as_png(items: list) -> list:
    """Convert DOT format to PNG image and return org-mode file link.

    Takes DOT format string (output from as_dot), generates PNG image,
    and returns [[path-to-image]] org-mode link.

    Args:
        items: List containing single DOT format string

    Returns:
        List with org-mode file link [[/tmp/YYYY-MM-DD--HH-MM-SS.png]]

    Examples:
        # Input: ["digraph { ... }"]
        # Output: ["#+ATTR_ORG: :width 100%\\n[[/tmp/2026-01-21--14-30-45.png]]"]
    """
    if not items or len(items) == 0:
        return []

    dot_content = items[0]
    if not isinstance(dot_content, str):
        return []

    # Generate filename with current date-time
    timestamp = datetime.now().strftime("%Y-%m-%d--%H-%M-%S")
    png_path = f"/tmp/{timestamp}.png"

    # Run dot command to generate PNG
    try:
        result = subprocess.run(
            ["dot", "-Tpng", "-o", png_path],
            input=dot_content,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return [f"Error: dot command failed: {result.stderr}"]
    except FileNotFoundError:
        return ["Error: dot command not found. Install graphviz."]

    org_pref = "#+ATTR_ORG: :width 100%"
    return [f"{org_pref}\n[[{png_path}]]"]
