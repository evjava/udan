"""Render descriptors and metadata system.

This module defines the render descriptor and metadata classes, similar
to the other tool types, for handling different output formats.

Renders are now loaded as plugins (tools) from modules like
plugins_renders.py and can be registered dynamically.
"""

from typing import Any

from udan.core.api_attributes import AttributeDescriptor
from udan.core_tools_loading.api_tools import ToolDescriptor, ToolKind

# Render shape: does the render take one item, or the whole forest at once?
# Declared in meta as `shape`. (`item_type` is something else: the type of the items
# the render formats, kept in meta like the shape.)
SHAPE_ITEM = "item"  # Per-item render: fn(item, indent, depth, ...)
SHAPE_CHILDREN = "children"  # Aggregate render: fn(depths, ...) or fn(depths, forest, attr_ds, ctx)

# Render Frontend Values
# ======================

# Metadata key for the render's output frontend, set in the annotated meta dict.
# The value names the OUTPUT FORMAT of the render, not the client: udan's own
# renders produce plain text and declare FRONTEND_TEXT (the default). During
# render resolution the requested frontend selects the matching variant of a
# render name (e.g. two renders aliased "table", one per frontend), so a
# package declares a further frontend value next to the renders producing it.
FRONTEND: str = "frontend"
FRONTEND_TEXT: str = "text"

RENDER = ToolKind(name="render", filter_group="render", variant_meta_key=FRONTEND)
"""Formats a forest as output. Its meta `shape` is the render shape above, and its item
contract stays in meta `item_type` (never promoted, unlike the kinds that promote their
item contract)."""

# Attribute descriptor for the render system attribute (set during pre-render phase)
RENDER_ATTR = AttributeDescriptor.create("render", args={})


class RenderDescriptor(ToolDescriptor):
    """Descriptor for a render tool."""

    # True when this descriptor was NOT typed by the user but suggested by a
    # tool's 'supported_renders' metadata (query processor fallback).
    # Frontends use this to distinguish explicit user choice (e.g. ':table')
    # from a tool's default CLI render preference.
    from_supported: bool = False

    def __repr__(self) -> str:
        if self.args:
            return f"Render({self.name}, args={self.args})"
        return f"Render({self.name})"


def is_aggregate_render(registry: Any, key: str) -> bool:
    """Does this render take all children instead of a single item?

    It lives in this package, not on the registry, because the aggregate input
    shape is a word of the render domain.

    Args:
        registry: Tools registry the render resolves from
        key: Render name or alias

    Returns:
        True when the render is registered with the aggregate (children) input type
    """
    metadata = registry.get_metadata(key)
    return bool(metadata and metadata.meta and metadata.meta.get("shape") == SHAPE_CHILDREN)
