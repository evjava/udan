"""Chain walking over loaded tool metadata.

The walk answers one question about a resolved chain - the tree of descriptors a
query resolved to: does any of its steps belong to a tool that declares a given
meta key. The metadatas come in as data and the meta key as an argument, so the
walk is the mechanism and the vocabulary stays with the caller.
"""

from collections.abc import Mapping

from udan.core.api_forests import Node
from udan.core_tools_loading.api_tools import ToolDescriptor, ToolMetadata


def chain_declares_meta(metadatas: Mapping[str, ToolMetadata], node: Node, meta_key: str) -> bool:
    """Does this resolved chain contain a tool declaring the meta key?

    The walk is depth-first: a node whose item is a descriptor counts when its tool
    declares the key in its meta; a node whose item is data - a literal, a spliced
    forest, the statement-list root - contributes nothing but its children, and so
    does a descriptor the metadatas do not name (an unregistered name resolves to
    nothing, so it declares nothing).

    Args:
        metadatas: Registered tool metadatas, by name or alias
        node: Resolved query tree node
        meta_key: The meta key the walk looks for

    Returns:
        True when the node or any of its children declares the key
    """
    item = node.item
    if isinstance(item, ToolDescriptor):
        metadata = metadatas.get(item.name)
        if metadata is not None and metadata.meta.get(meta_key):
            return True
    return any(chain_declares_meta(metadatas, child, meta_key) for child in node.children)
