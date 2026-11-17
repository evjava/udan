"""Built-in render tools.

This module contains standard render functions that can be registered
as tools. Each render is marked with @annotated decorator and
tool_type="render".

Render Input Types:
- "item": Per-item render - takes a single item and renders it
- "items": Aggregate render - takes all items and renders them together
"""

import re
from collections.abc import Callable, Iterable
from typing import Any

from tabulate import tabulate  # type: ignore[import-untyped]

from udan.attributes.api_attribute_storage import AttributeStorageAPI
from udan.core.api_attributes import SYSTEM, AttributeDescriptor, AttributeValue
from udan.core.api_forests import Item
from udan.core.api_item_types import fits_chain
from udan.core.api_logger import LoggerAPI
from udan.core.api_output_engine import OutputEngineAPI
from udan.core.api_type_system import ForestTypeDescriptor, TypeSystemAPI
from udan.core_tools_loading.api_annotated import annotated
from udan.core_tools_loading.api_tools import ToolDescriptor, ToolMetadata
from udan.core_tools_loading.api_tools_registry import ToolsRegistryAPI
from udan.core_tools_loading.api_types import Group
from udan.core_tools_loading.utils_str import cut_if_needed
from udan.decompof import Plugin, decorate, provide
from udan.renders.api_render_engine import RenderEngineAPI
from udan.renders.api_renders import FRONTEND, FRONTEND_TEXT, RENDER, SHAPE_CHILDREN, SHAPE_ITEM
from udan.renders.impl_render_engine import RenderEngineImpl


@annotated(meta={"tool_type": "attribute", SYSTEM: True})
def render(item: Item, depth: int = 0) -> str:
    """Which render was used for this item?

    This system attribute stores the render name used for each item.
    It is calculated during the pre-render phase, not during normal
    attribute calculation.

    Returns:
        Render name (e.g., "org", "table", "list", "term-list-item")
    """
    # Default fallback - should be overridden by pre-render phase
    return "term-list-item"


# Description truncation constants (local to this module)
_BRIEF_DESC_TRUNCATION_LENGTH = 60
_PREFIX_TRUNCATION_LENGTH = 45
_ALIASES_MARKER = " (aliases: "


@annotated(meta={"item_type": "dict", "tool_type": "render", "aliases": ["attr"], "shape": SHAPE_ITEM})
def render_attr(
    item: Item,
    field_name: str = "",
    indent: str = "",
    attrs: dict[str, Any] | None = None,
) -> str:
    """Render an item by extracting a specific field.

    Extracts and displays only the specified field from a single item.
    For dict items, extracts the key directly.
    For attributes, extracts the attribute value by identity.

    Args:
        item: The item to render (can be a dict or have special keys)
        field_name: Field name to extract (e.g., "name", "color", "translate_ru")
        indent: Indentation string
        attrs: Attributes dict with attribute identities as keys

    Returns:
        Formatted string with extracted value
    """
    if not field_name:
        # Fallback to default string representation if no field specified
        return f"{indent}{str(item)}"

    # Check if item has the field directly (for dict items)
    if isinstance(item, dict) and "item" in item:
        actual_item = item["item"]
        if isinstance(actual_item, dict) and field_name in actual_item:
            return f"{indent}{actual_item[field_name]}"
    elif isinstance(item, dict) and field_name in item:
        return f"{indent}{item[field_name]}"

    # Check attrs dict for the field_name (which is the attribute identity)
    if attrs and field_name in attrs:
        attr_value = attrs[field_name]
        # If attr_value is a dict and contains the field
        if isinstance(attr_value, dict) and field_name in attr_value:
            return f"{indent}{attr_value[field_name]}"
        if attr_value is not None:
            return f"{indent}{attr_value}"
        # Return empty string for None values (don't output anything)
        return ""

    # Fallback: try to get field from item using getattr
    try:
        actual_item = item.get("item") if isinstance(item, dict) and "item" in item else item
        value = getattr(actual_item, field_name, "")
        return f"{indent}{value}" if value else ""
    except Exception:
        return ""


@annotated(meta={"item_type": "any", "tool_type": "render", "aliases": ["raw"], "shape": SHAPE_ITEM})
def render_raw(item: Item, indent: str = "", attrs: dict | None = None) -> str:
    """Render item as raw string (str() representation)."""
    if isinstance(item, Group):
        parts = ["'type': 'group'", f"'key': {item.key!r}"]
        if attrs:
            for k, v in attrs.items():
                parts.append(f"{k!r}: {v!r}")
        return f"{indent}{{{', '.join(parts)}}}"
    return f"{indent}{str(item)}"


def _resolve_attr_path(attrs: dict[str, Any] | None, path: str) -> Any:
    """Resolve a dot-separated attribute path to value.

    Args:
        attrs: Attributes dict from context
        path: Dot-separated attribute path (e.g., 'a.b')

    Returns:
        Value at path, or None if not found
    """
    if not attrs:
        return None

    # Split path into components
    parts = path.split(".")
    value = attrs

    for part in parts:
        if isinstance(value, dict):
            value = value.get(part)
            if value is None:
                return None
        else:
            return None

    return value


_ITEM_SUBSCRIPT_PATTERN = re.compile(r"^item\[(.+?)\]$")


def _resolve_item_field(item: Item, field_name: str) -> Any:
    """Resolve a field of the item itself: dict key or object attribute.

    Supports '{name}' (direct field of a dict item) and '{item[name]}' / "{item['name']}"
    (explicit subscript form).

    Args:
        item: The item being rendered
        field_name: Placeholder name without braces

    Returns:
        Field value, or None when the item has no such field
    """
    subscript = _ITEM_SUBSCRIPT_PATTERN.match(field_name)
    if subscript:
        key = subscript.group(1).strip("\"'")
        return item.get(key) if isinstance(item, dict) else getattr(item, key, None)
    if isinstance(item, dict):
        return item.get(field_name)
    return getattr(item, field_name, None)


def _format_with_attr_refs(
    format_string: str,
    item: Item,
    attrs: dict[str, Any] | None,
    indent: str = "",
) -> str:
    """Format string with attribute references.

    Supports:
    - {item} - The item itself (string representation)
    - {attr.path} - Attribute value at dot-separated path
    - {attr.path:format} - Formatted value (e.g., {:.1f})
    - {field} / {item[field]} - Field of the item itself (dict key or object attribute)
    - Constant string without placeholders - returned as-is

    Args:
        format_string: Format string with attribute references
        item: The item being rendered
        attrs: Attributes dict from context
        indent: Indentation string

    Returns:
        Formatted string
    """
    # Parse format string to get field names with their positions
    # We need to manually substitute to handle field names with dots
    result = format_string
    field_pattern = r"\{([^}:]+)(:([^}]*))?\}"
    matches = list(re.finditer(field_pattern, format_string))

    # Format string without placeholders is a constant: return it as-is
    # (the render engine repeats it for every item)
    if not matches:
        return result

    # Find all field placeholders and their positions
    for match in matches:
        field_name = match.group(1)
        format_spec = match.group(3) or ""
        placeholder = match.group(0)

        # Resolve the value for this field
        if field_name == "item":
            # Handle dict format with 'item' key (internal representation)
            if isinstance(item, dict) and "item" in item:
                value = str(item["item"])
            else:
                value = str(item)
        else:
            # Resolve attribute path first (explicit attrs win over item fields),
            # then fall back to the item's own fields
            resolved = _resolve_attr_path(attrs, field_name)
            if resolved is None:
                resolved = _resolve_item_field(item, field_name)

            # Apply format spec if value exists
            if resolved is not None and format_spec:
                try:
                    # format_spec already includes the dot (e.g., ".1f")
                    resolved = format(resolved, format_spec)
                except ValueError, TypeError:
                    pass  # Keep original value if format fails

            # Convert to string
            if resolved is None:
                value = ""
            elif not isinstance(resolved, str):
                value = str(resolved)
            else:
                value = resolved

        # Replace the placeholder with the actual value
        result = result.replace(placeholder, value, 1)

    # If result is empty or unchanged, fall back to item
    if not result or result == format_string:
        return f"{indent}{str(item)}"

    return result


@annotated(meta={"item_type": "any", "tool_type": "render", "aliases": ["fmt"], "shape": SHAPE_ITEM})
def render_format(
    item: Item,
    format: str = "{item}",
    indent: str = "",
    attrs: dict[str, Any] | None = None,
    *rest: str,
) -> str:
    """Generic formatter render with attribute references.

    Uses format strings with attribute path references, inspired by Potluck's
    pattern language. Format strings are passed directly as arguments.

    Args:
        item: The item being rendered
        format: Format string with attribute references (default: "{item}")
        indent: Indentation string (for API compatibility)
        attrs: Attributes dict from context
        *rest: Additional format arguments (joined with spaces if format is default)

    Returns:
        Formatted string

    Examples:
        # Attribute path in the format string
        ls_files src, file_created, :fmt "- {item} :: {file_created}"
    """
    # If additional arguments are provided and format is default, join them as format string
    if rest and format == "{item}":
        format = " ".join(rest)
    # If both format and rest are provided, rest takes precedence
    elif rest:
        format = " ".join(rest)

    return _format_with_attr_refs(format, item, attrs, indent)


@annotated(meta={"item_type": "any", "tool_type": "render", "aliases": ["list-item"], "shape": SHAPE_ITEM})
def render_list(item: Item, indent: str = "", depth: int = 0) -> str:
    """Render item as a list element with nested brackets based on depth.

    Items at depth 0 are rendered as-is: a
    Items at depth 1 are wrapped in brackets: [a]
    Items at depth 2 are wrapped in double brackets: [[a]]
    And so on...

    If the item is already a list, it's rendered directly without extra brackets.
    This preserves list structure when using extenders that return lists.

    Args:
        item: The item to render
        indent: Indentation string (not used for list format, kept for compatibility)
        depth: Depth level for determining bracket nesting

    Returns:
        Formatted string with appropriate brackets
    """
    # If item is already a list, render it directly without adding extra brackets
    if isinstance(item, list):
        return str(item)

    # Wrap in brackets based on depth
    brackets = depth * "["
    brackets_close = depth * "]"
    return f"{brackets}{str(item)}{brackets_close}"


@annotated(
    meta={
        "item_type": "any",
        "tool_type": "render",
        "aliases": ["term-list-item"],
        "shape": SHAPE_ITEM,
    }
)
def render_term_list_item(item: Item, indent: str = "", depth: int = 0, attrs: dict[str, Any] | None = None) -> str:
    """Render item as a terminal list item with optional attribute value.

    Formats items as "- item" or "- item :: value" depending on whether
    an attribute value is provided. Indentation is based on depth (depth 0 = no indent,
    depth 1 = 2 spaces, depth 2 = 4 spaces, etc.)

    Args:
        item: The item to render (or dict with 'item' and 'attrs' keys)
        indent: Indentation string (not used, kept for compatibility)
        depth: Depth level for determining indentation (0=no indent, 1=2 spaces, etc.)
        attrs: Optional attributes dict to append with :: separator

    Returns:
        Formatted string "- item" or "- item :: value"
    """
    # Calculate indentation based on depth: depth 0 = 0 spaces, depth 1 = 2 spaces, depth 2 = 4 spaces, etc.
    calculated_indent = "  " * depth

    # Support both direct item and dict format for compatibility
    if isinstance(item, dict) and "item" in item:
        actual_item = item["item"]
        if attrs is None:
            attrs = item.get("attrs", {})
    else:
        actual_item = item

    if attrs:
        # Get the first attribute value
        attr_value = next(iter(attrs.values()), None)
        if attr_value is not None:
            return f"{calculated_indent}- {actual_item} :: {attr_value}"
    return f"{calculated_indent}- {actual_item}"


@annotated(
    meta={
        "item_type": "any",
        "tool_type": "render",
        "aliases": ["table-row-single"],
        "shape": SHAPE_ITEM,
    }
)
def render_table(item: dict, indent: str = "") -> str:
    """Render dict item as a table row (per-item render)."""
    if isinstance(item, dict):
        # Convert dict to list of tuples for tabulate
        # Format: [(key, value), ...]
        table_data = [(k, str(v).replace("\n", " ")[:40]) for k, v in item.items()]
        return tabulate(table_data, tablefmt="plain", headers=["key", "value"])
    return f"{indent}- {str(item)}"


@annotated(meta={"item_type": "dict", "tool_type": "render", "aliases": ["table-row"], "shape": SHAPE_ITEM})
def render_table_row(item: Item, indent: str = "", depth: int = 0, attrs: dict[str, Any] | None = None) -> str:
    """Render item as a table row with attribute values.

    Formats items as "|> item|val1|val2|" for multi-attribute display.

    Args:
        item: The item to render (or dict with 'item' and 'attrs' keys)
        indent: Indentation string
        depth: Depth parameter (accepted for compatibility, not used)
        attrs: Attributes dict with attribute identities as keys

    Returns:
        Formatted table row string "|> item|val1|val2|"
    """
    # Support both direct item and dict format for compatibility
    if isinstance(item, dict) and "item" in item:
        actual_item = item["item"]
        if attrs is None:
            attrs = item.get("attrs", {})
    else:
        actual_item = item
        if attrs is None:
            attrs = {}

    if attrs:
        # Convert attrs dict to list of values in order
        attr_values = list(attrs.values())
        tbl = "|".join(map(str, attr_values))
        return f"|>{indent} {actual_item}|{tbl}|"
    return f"{indent}- {actual_item}"


@annotated(meta={"item_type": "any", "tool_type": "render", "aliases": ["lines-item"], "shape": SHAPE_ITEM})
def render_lines_item(item: Item, indent: str = "") -> str:
    """Render item as a bare line without a bullet prefix.

    This render outputs items without the leading "- " prefix, making it
    suitable for generating structured text formats like DOT graph files.

    Args:
        item: The item to render
        indent: Indentation string (prepended to the item)

    Returns:
        Formatted string without bullet prefix
    """
    return f"{indent}{str(item)}"


@annotated(
    meta={
        "item_type": "group",
        "tool_type": "render",
        "aliases": ["group-header"],
        "shape": SHAPE_ITEM,
    }
)
def render_group_header(
    item: Group | dict[str, Any],
    indent: str = "",
    depth: int = 0,
    key_descriptor: ToolDescriptor | None = None,
    key: AttributeValue = None,
) -> str:
    """Render Group item as a section header.

    Formats as "- {descriptor}={key} ::" or "- {key} ::" depending on
    whether the grouping ran over a named tool.

    Args:
        item: The Group item to render (or dict with 'key_descriptor' and 'key' keys)
        indent: Indentation string
        depth: Depth parameter (for compatibility with rendering pipeline)
        key_descriptor: The descriptor the grouping ran over, when there was one
        key: The group key/value

    Returns:
        Formatted group header string
    """
    # Support both direct Group and dict format for compatibility
    if isinstance(item, dict):
        if key_descriptor is None:
            value = item.get("key_descriptor")
            if isinstance(value, ToolDescriptor):
                key_descriptor = value
        if key is None:
            key = item.get("key")
    else:
        # Direct Group object
        if hasattr(item, "key_descriptor"):
            key_descriptor = item.key_descriptor
        if hasattr(item, "key"):
            key = item.key

    if key_descriptor is not None and getattr(key_descriptor, "name", None):
        return f"{indent}- {key_descriptor.name}={key} ::"
    return f"{indent}- {key} ::"


@annotated(
    meta={
        "item_type": "dict",
        "tool_type": "render",
        "aliases": ["attr-then-multiline"],
        "shape": SHAPE_ITEM,
    }
)
def render_attr_then_multiline(
    item: Item,
    indent: str = "",
    depth: int = 0,
    attr_identity: str = "",
    multiline_content: str = "",
) -> str:
    """Render attribute name first, then multi-line content.

    Used when a custom render produces multi-line output (like org format)
    and we want to show the attribute name first, then the content.

    Args:
        item: The item being rendered (not used in output, kept for compatibility)
        indent: Indentation string
        depth: Depth parameter (accepted for compatibility, not used)
        attr_identity: The attribute identity/name to show first
        multiline_content: The multi-line content to show after

    Returns:
        Multi-line string with attribute identity first, then content
    """
    lines = [f"{indent}- {attr_identity}"]
    if multiline_content:
        content_lines = multiline_content.splitlines()
        lines.extend(content_lines)
    return "\n".join(lines)


@annotated(
    meta={
        "item_type": "tool_group",
        "tool_type": "render",
        "aliases": ["introspect-item"],
        "shape": SHAPE_ITEM,
    }
)
def render_introspect(item: dict, indent: str = "") -> str:
    """Render introspection item in formatted output.

    For introspection dictionaries (returned by help inserter),
    formats as "{name} :: {description}". Group headers are Group items
    handled by the engine (group-header render), not here.

    Args:
        item: Dict with introspection data (name, description, location)
        indent: Indentation string

    Returns:
        Formatted string for introspection output
    """
    if not isinstance(item, dict):
        return f"{indent}- {str(item)}"

    # Regular item - format as "name :: description"
    name = item.get("name", "")
    description = item.get("description", "")
    location = item.get("location")

    # Get first line of description
    brief_desc = description.split("\n")[0].strip()

    # Truncate if too long, but preserve aliases if present
    if len(brief_desc) > _BRIEF_DESC_TRUNCATION_LENGTH:
        # Check if there's an aliases section at the end
        aliases_idx = brief_desc.rfind(_ALIASES_MARKER)
        if aliases_idx > 0:
            # Keep the full aliases part, truncate the beginning
            aliases_part = brief_desc[aliases_idx:]  # Already has leading space
            # Truncate the beginning part
            prefix = brief_desc[:aliases_idx].strip()
            # Find a good cutoff point in the prefix
            if len(prefix) > _PREFIX_TRUNCATION_LENGTH:
                # Truncate prefix to ~45 chars total (including "...")
                prefix = cut_if_needed(prefix, _PREFIX_TRUNCATION_LENGTH)
            brief_desc = prefix + aliases_part  # No extra space needed
        else:
            brief_desc = cut_if_needed(brief_desc, _BRIEF_DESC_TRUNCATION_LENGTH)

    # Format with trailing space if description is empty
    # Note: indent already contains depth-based indentation
    result = f"{indent}- {name} ::"
    if brief_desc:
        result += f" {brief_desc}"
    if location:
        result += f" [{location}]"

    return result


# ============================================================================
# Aggregate Renders (shape="children")
# These renders take all items (as depths and children) and render them together
# ============================================================================


@annotated(
    meta={
        "item_type": "group",
        "tool_type": "render",
        "aliases": ["list"],
        "shape": SHAPE_CHILDREN,
        "attribute_type": "aggregate",
    }
)
def render_list_aggregate(
    depths: list[int],
    children: list[Item],
    attr_ds: list[AttributeDescriptor],
    registry: ToolsRegistryAPI | None = None,
) -> str:
    """Aggregate render: creates comma-separated list from all items.

    Items are rendered using the per-item 'list-item' render to get proper
    bracket nesting based on depth.

    Args:
        depths: List of depth values for each item
        children: List of items to render
        attr_ds: Attribute descriptors (not used, kept for signature)
        registry: Tools registry for resolving per-item renders (injected or passed from RenderEngine)

    Returns:
        Formatted string like "[item1, item2, item3]"
    """
    if registry is None:
        raise RuntimeError("render_list_aggregate requires registry parameter")

    items = []
    # Use the per-item list-item render for proper depth-based bracket nesting
    item_render_fn = registry.resolve("list-item", kind=RENDER).fn
    for depth, item in zip(depths, children):
        rendered = item_render_fn(item, "", depth)
        items.append(rendered)
    return f"[{', '.join(items)}]"


def _join_rendered_items(
    depths: list[int],
    children: list[Item],
    rendered_items: list[str],
    decorate: Callable[[str], str],
) -> str:
    """Join per-item rendered lines, one per line, indented by depth.

    Args:
        depths: List of depth values for each item
        children: List of items to render (aligned with rendered_items)
        rendered_items: Per-item rendered lines supplied by the render engine
        decorate: Turns an indented line into the final line (adds the layout)

    Returns:
        One line per item, e.g. "- item1\n- item2"
    """
    lines = []
    for depth, rendered in zip(depths, rendered_items):
        lines.append(decorate("  " * depth + rendered))
    return "\n".join(lines)


@annotated(
    meta={
        "item_type": "group",
        "tool_type": "render",
        "aliases": ["lines"],
        "shape": SHAPE_CHILDREN,
        "attribute_type": "aggregate",
    }
)
def render_lines_aggregate(
    depths: list[int],
    children: list[Item],
    attr_ds: list[AttributeDescriptor],
    rendered_items: list[str] | None = None,
) -> str:
    """Aggregate render: joins the per-item rendered lines without any prefix.

    Each line is the item rendered by its own per-item render (e.g. commit-log
    for commits), indented by depth - nothing else is added.

    Args:
        depths: List of depth values for each item
        children: List of items to render
        attr_ds: Attribute descriptors (not used, kept for signature)
        rendered_items: Per-item rendered lines supplied by the render engine,
            aligned with children

    Returns:
        One line per item, e.g. "item1\nitem2"
    """
    _ = attr_ds, children
    if rendered_items is None:
        raise RuntimeError("render_lines_aggregate requires rendered_items parameter")
    return _join_rendered_items(depths, children, rendered_items, lambda line: line)


@annotated(
    meta={
        "item_type": "group",
        "tool_type": "render",
        "aliases": ["bullets"],
        "shape": SHAPE_CHILDREN,
        "attribute_type": "aggregate",
    }
)
def render_bullets_aggregate(
    depths: list[int],
    children: list[Item],
    attr_ds: list[AttributeDescriptor],
    rendered_items: list[str] | None = None,
) -> str:
    """Aggregate render: joins the per-item rendered lines into a hyphen list.

    Each line is the item rendered by its own per-item render (e.g. commit-log
    for commits), indented by depth and prefixed with '- '. Lines that already
    carry their own '- ' prefix (org-item, group headers) are not re-bulleted.

    Args:
        depths: List of depth values for each item
        children: List of items to render
        attr_ds: Attribute descriptors (not used, kept for signature)
        rendered_items: Per-item rendered lines supplied by the render engine,
            aligned with children

    Returns:
        One line per item, e.g. "- item1\n- item2"
    """
    _ = attr_ds, children
    if rendered_items is None:
        raise RuntimeError("render_bullets_aggregate requires rendered_items parameter")

    def _bullet(line: str) -> str:
        if line.lstrip().startswith("- "):
            # Already a list item on its own (org-item, group header)
            return line
        # Insert the bullet after the depth indentation
        content = line.lstrip(" ")
        return f"{line[: len(line) - len(content)]}- {content}"

    return _join_rendered_items(depths, children, rendered_items, _bullet)


@annotated(
    meta={
        "item_type": "group",
        "tool_type": "render",
        "aliases": ["table"],
        "shape": SHAPE_CHILDREN,
        "attribute_type": "aggregate",
        FRONTEND: FRONTEND_TEXT,
    }
)
def render_table_aggregate(  # noqa: C901, PLR0912
    depths: list[int],
    children: list[Item],
    attr_ds: list[AttributeDescriptor],
    *columns: str,
    items_attrs: list[dict] | None = None,
) -> str:
    """Aggregate render: creates table from all dict items.

    Collects all dict items and formats them as a table with headers.
    Handles grouped data (Group markers) by rendering separate tables with headers.
    Scalar items without attributes are rendered as a depth/item table.

    Uses custom formatting to match legacy table output (right-aligned numbers).

    Args:
        depths: List of depth values for each item
        children: List of items to render
        attr_ds: Attribute descriptors (not used, kept for signature)
        *columns: Optional column names to display (e.g., :table id entry)
                  If not specified, shows all columns from all items

    Returns:
        Formatted table string

    Examples:
        :table              # Show all columns
        :table id entry     # Show only id and entry columns
        :table name language  # Show only name and language columns
    """
    # Check if this is grouped data (Group markers at depth 0, items at depth 1)
    if _is_grouped_data(depths, children):
        return _render_grouped_tables(depths, children)

    # Collect dict items and non-dict items (with depths for indentation)
    dict_items: list[dict] = []
    non_dict_items: list[tuple[int, Item]] = []

    for depth, item in zip(depths, children):
        if isinstance(item, dict):
            dict_items.append(item)
        elif isinstance(item, (list, tuple)):
            # Check if this is a list of dicts (from group_by_field)
            if _is_list_of_dicts(item):
                # Add all dicts to the table
                dict_items.extend(item)
            else:
                non_dict_items.append((depth, item))
        else:
            non_dict_items.append((depth, item))

    # Promote non-dict items to dict items using resolved attribute values
    if not dict_items and non_dict_items and items_attrs:
        for i, (depth, item) in enumerate(non_dict_items):
            attrs = items_attrs[i] if i < len(items_attrs) else {}
            row: dict[str, Any] = {"item": str(item)}
            for attr_name, val in attrs.items():
                if isinstance(val, dict):
                    row.update(val)
                else:
                    row[attr_name] = val
            dict_items.append(row)
        non_dict_items = []

    if not dict_items:
        # No dict items - render as depth/item table
        rows = [{"depth": depth, "item": str(item)} for depth, item in non_dict_items]
        return _build_table_output_legacy(rows, ["depth", "item"])

    # Filter to only specified columns if provided
    if columns:
        # Parse column specs: 'header:{attr:fmt}' or plain 'key'
        col_specs = [_parse_col_spec(c) for c in columns]
        headers = [spec[0] for spec in col_specs]
        dict_items = _apply_col_specs(dict_items, col_specs)
    else:
        # No columns specified - use all keys like regular table
        all_keys: dict[str, None] = {}
        for item in dict_items:
            for key in item.keys():
                all_keys[key] = None
        headers = list(all_keys.keys())

    # Move 'name' to front if it exists
    if "name" in headers and headers[0] != "name":
        headers.remove("name")
        headers.insert(0, "name")

    # Build table using custom formatting (to match legacy output)
    result = _build_table_output_legacy(dict_items, headers)

    # Append non-dict items if any
    if non_dict_items:
        lines = [result]
        for depth, item in non_dict_items:
            indent = "  " * depth
            lines.append(f"{indent}- {str(item)}")
        return "\n".join(lines)

    return result


@annotated(
    meta={
        "item_type": "group",
        "tool_type": "render",
        "aliases": ["org-aggregate"],
        "shape": SHAPE_CHILDREN,
        "attribute_type": "aggregate",
    }
)
def render_org_aggregate(
    depths: list[int],
    children: list[Item],
    attr_ds: list[AttributeDescriptor],
) -> str:
    """Aggregate render: creates org-mode outline with depth-based * markers.

    Each item is rendered as an org-mode headline with * markers
    indicating nesting depth.

    Args:
        depths: List of depth values for each item
        children: List of items to render
        attr_ds: Attribute descriptors (not used, kept for signature)

    Returns:
        Formatted org-mode outline string
    """
    lines = []
    for depth, item in zip(depths, children):
        # Org-mode uses * for depth (depth 0 = *, depth 1 = **, etc.)
        prefix = "*" * (depth + 1)
        lines.append(f"{prefix} {str(item)}")
    return "\n".join(lines)


def _resolve_attr(attr_ds: list[AttributeDescriptor], name: str) -> Any:
    """Find attribute descriptor by name in attr_ds list."""
    for at_d in attr_ds:
        if at_d.name == name:
            return at_d
    return None


def _resolve_props(attr_ds: list[AttributeDescriptor], properties: str) -> list[tuple[str, Any]]:
    """Resolve comma-separated property names to (name, descriptor) pairs."""
    result = []
    for prop_name in [p.strip() for p in properties.split(",") if p.strip()]:
        at_d = _resolve_attr(attr_ds, prop_name)
        if at_d:
            result.append((prop_name, at_d))
    return result


def _render_headline(
    item: Item,
    storage: AttributeStorageAPI | None,
    headline_at_d: AttributeDescriptor | None,
    tags_at_d: AttributeDescriptor | None,
) -> str:
    """Render a single org headline with optional headline attr and tags."""
    headline_text = str(item)
    if storage is not None and headline_at_d is not None:
        headline_val = storage.get_attr_value(headline_at_d, item)
        if headline_val:
            headline_text = str(headline_val)
    tag_str = ""
    if storage is not None and tags_at_d is not None:
        tags_val = storage.get_attr_value(tags_at_d, item)
        if tags_val:
            tag_str = " " + "".join(f":{t}" for t in tags_val) + ":"
    return f"** {headline_text}{tag_str}"


@annotated(
    meta={
        "item_type": "group",
        "tool_type": "render",
        "aliases": ["org-structure"],
        "shape": SHAPE_CHILDREN,
        "attribute_type": "aggregate",
    }
)
def render_org_dump(
    depths: list[int],
    children: list[Item],
    attr_ds: list[AttributeDescriptor],
    storage: AttributeStorageAPI | None = None,
    tags: str = "",
    properties: str = "",
    headline: str = "",
) -> str:
    """Aggregate render: org headings with optional tags, properties + content body.

    Depth-0 items are rendered as ``** item`` headings.
    If ``headline`` is set, uses the named attribute value as headline text instead of str(item).
    If ``tags`` is set, appends org-style tags (``:t1:t2:t3:``).
    If ``properties`` is set, shows a :PROPERTIES: drawer with named attributes.
    Depth-1 items are rendered as plain body text (no stars).

    Args:
        depths: List of depth values for each item.
        children: List of items to render.
        attr_ds: Attribute descriptors.
        storage: Attribute storage (injected).
        tags: Attribute name for org tags (e.g., ``extract_tags`` composed in the
            chain as ``extract_tags(extract_text)``, resolved by its name).
        properties: Comma-separated attribute names for :PROPERTIES: drawer
            (e.g., ``file_created``).
        headline: Attribute name to use as headline text instead of str(item)
            (e.g., ``relative_path``).

    Produces output like::

        ** file.pdf :tag1:tag2:
        :PROPERTIES:
        :file_created: 2026-05-09--14-30--000000
        :END:
        extracted text content here
    """
    tags_at_d = _resolve_attr(attr_ds, tags) if tags else None
    headline_at_d = _resolve_attr(attr_ds, headline) if headline else None
    prop_at_ds = _resolve_props(attr_ds, properties) if properties else []

    lines = []
    if headline:
        lines.append(f"# headline-attr: {headline}")
    for depth, item in zip(depths, children):
        if depth == 0:
            lines.append(_render_headline(item, storage, headline_at_d, tags_at_d))
            if storage is not None and prop_at_ds:
                lines.append(":PROPERTIES:")
                for prop_name, prop_at_d in prop_at_ds:
                    val = storage.get_attr_value(prop_at_d, item)
                    if val is not None:
                        lines.append(f":{prop_name}: {val}")
                lines.append(":END:")
        else:
            lines.append(str(item))
    return "\n".join(lines)


@annotated(
    meta={
        "item_type": "group",
        "tool_type": "render",
        "aliases": ["org-list"],
        "shape": SHAPE_CHILDREN,
        "attribute_type": "aggregate",
    }
)
def render_org_list_aggregate(
    depths: list[int],
    children: list[Item],
    attr_ds: list[AttributeDescriptor],
) -> str:
    """Aggregate render: creates org-mode list with - prefix and indentation.

    Each item is rendered as a list item with - prefix and indentation
    based on depth.

    Args:
        depths: List of depth values for each item
        children: List of items to render
        attr_ds: Attribute descriptors (not used, kept for signature)

    Returns:
        Formatted org-mode list string
    """
    lines = []
    for depth, item in zip(depths, children):
        indent = "  " * depth
        lines.append(f"{indent}- {str(item)}")
    return "\n".join(lines)


# ============================================================================
# Helper functions for aggregate table rendering
# ============================================================================


def _is_grouped_data(depths: list[int], children: list) -> bool:
    """Check if data contains grouped data (Group markers with nested items)."""
    # Look for Group objects at depth 0, followed by items at depth 1
    for i, depth in enumerate(depths):
        item = children[i]
        if depth == 0 and _is_group_item(item):
            # Check if next items at depth 1 exist
            if i + 1 < len(depths):
                next_depth = depths[i + 1]
                if next_depth == 1:
                    return True
    return False


def _is_group_item(item: Item) -> bool:
    """Check if item is a Group object."""
    # Check for Group object without importing core_api_types at runtime
    return hasattr(item, "__class__") and item.__class__.__name__ == "Group"


def _is_list_of_dicts(item) -> bool:
    """Check if item is a non-empty list of all dicts."""
    if not item:
        return False
    return all(isinstance(subitem, dict) for subitem in item)


def _group_section_title(item) -> str:
    """Build a group section title like "color=red" from a Group item.

    Uses the grouping descriptor's name when available, otherwise just
    the group key.
    """
    descriptor = getattr(item, "key_descriptor", None)
    if descriptor is not None and getattr(descriptor, "name", None):
        return f"{descriptor.name}={item.key}"
    return str(item.key)


def _render_grouped_tables(depths: list[int], children: list) -> str:
    """Render grouped data as separate tables with section headers.

    Processes the hierarchical structure where Group markers (depth 0)
    have child items (depth 1), rendering each group as a separate table.

    Args:
        depths: List of depth values for each item
        children: List of items

    Returns:
        Formatted output with separate tables for each group
    """
    output_sections: list[str] = []
    current_group_items: list[dict] = []
    current_group_name: str | None = None
    all_items: list[dict] = []

    # Process items in order to collect groups
    for depth, item in zip(depths, children):
        if depth == 0 and _is_group_item(item):
            # Previous group complete - render it
            if current_group_items:
                output_sections.append(_render_single_group(current_group_name, current_group_items, all_items))
                current_group_items = []

            # Start new group
            if hasattr(item, "key"):
                current_group_name = _group_section_title(item)
            else:
                current_group_name = str(item)

        elif depth == 1 and isinstance(item, dict):
            # Add dict to current group
            current_group_items.append(item)
            all_items.append(item)
        elif depth == 1:
            # Scalar item - promote to a single-column row
            row: dict[str, Any] = {"item": str(item)}
            current_group_items.append(row)
            all_items.append(row)

    # Don't forget the last group
    if current_group_items:
        output_sections.append(_render_single_group(current_group_name, current_group_items, all_items))

    return "\n".join(output_sections).strip()


def _render_single_group(group_name: str | None, items: list, all_items: list) -> str:
    """Render a single group as a table with section header.

    Args:
        group_name: Name of the group (e.g., "red", "orange")
        items: List of dicts in this group
        all_items: All items across all groups (for collecting headers)

    Returns:
        Formatted section with header and table
    """
    # Get headers from all items (ensures consistent columns across groups)
    all_keys: dict[str, None] = {}
    for item in all_items:
        for key in item.keys():
            all_keys[key] = None
    headers = list(all_keys.keys())

    # Move 'name' to front if it exists
    if "name" in headers and headers[0] != "name":
        headers.remove("name")
        headers.insert(0, "name")

    # Build table using legacy formatting
    table = _build_table_output_legacy(items, headers)

    # Build section with org-style heading
    section = f"* {group_name}\n"
    return section + table


def _parse_col_spec(spec: str) -> tuple[str, str, str]:
    """Parse column spec like 'header:{attr.path:fmt}' or plain 'key'.

    Returns (header, attr_path, format_spec).
    - 'name' -> ('name', 'name', '')
    - 'cov:{percent_covered:.0f}' -> ('cov', 'percent_covered', '.0f')
    - 'fn:{function_name}' -> ('fn', 'function_name', '')
    """
    if ":" not in spec or "{" not in spec:
        return (spec, spec, "")
    # Format: header:{attr:fmt}
    colon_pos = spec.index(":")
    header = spec[:colon_pos]
    template = spec[colon_pos + 1 :]
    # Parse {attr:fmt}
    m = re.match(r"\{([^}:]+)(?::([^}]*))?\}", template)
    if m:
        return (header, m.group(1), m.group(2) or "")
    return (header, template.strip("{}"), "")


def _apply_col_specs(items: list[dict], col_specs: list[tuple[str, str, str]]) -> list[dict]:
    """Apply column specs to dict items, extracting and formatting values."""
    result = []
    for item in items:
        row = {}
        for header, attr_path, fmt_spec in col_specs:
            val = _resolve_dict_path(item, attr_path)
            if val is not None and fmt_spec:
                try:
                    val = format(val, fmt_spec)
                except ValueError, TypeError:
                    pass
            row[header] = val if val is not None else ""
        result.append(row)
    return result


def _resolve_dict_path(d: dict, path: str) -> Any:
    """Resolve dot-separated path in dict, e.g. 'coverage.percent_covered'."""
    parts = path.split(".")
    current: Any = d
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
        if current is None:
            return None
    return current


def _build_table_output_legacy(items: list, headers: list) -> str:
    """Build formatted table output from dict items using legacy formatting.

    Replicates the custom table formatting from core_rendering.py with:
    - Right-aligned numbers
    - Left-aligned strings
    - Custom separator with + at intersections

    Args:
        items: List of dicts
        headers: List of column headers

    Returns:
        Formatted table string
    """
    # Build table data
    table_data = []
    for item in items:
        row = [str(item.get(key, "")) for key in headers]
        table_data.append(row)

    # Calculate column widths
    col_widths = _calculate_column_widths_legacy(headers, table_data)

    # Build header row
    header_row = "| " + " | ".join(h.ljust(w) for h, w in zip(headers, col_widths)) + " |"

    # Build separator row with + at intersections
    separator = "|-" + "-+-".join("-" * w for w in col_widths) + "-|"

    # Build data rows
    data_rows = []
    for row in table_data:
        formatted_cells = []
        for val, width in zip(row, col_widths):
            # Right-align numbers, left-align strings
            try:
                float(val)
                formatted_cells.append(val.rjust(width))
            except ValueError, TypeError:
                formatted_cells.append(val.ljust(width))
        data_rows.append("| " + " | ".join(formatted_cells) + " |")

    return "\n".join([header_row, separator] + data_rows)


def _calculate_column_widths_legacy(headers: list, table_data: list) -> list:
    """Calculate column widths for table formatting.

    Args:
        headers: List of column headers
        table_data: List of data rows

    Returns:
        List of column widths
    """
    col_widths = [len(h) for h in headers]
    for row in table_data:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(val))
    return col_widths


# =============================================================================
# The package's kind service and container contribution
# =============================================================================


class RenderEngine(RenderEngineImpl):
    """The package's kind service.

    A kind service declares its KINDS where the container harvests them - a plugin
    package's plugins_*.py modules - and the KINDS themselves live on the contract
    (RenderEngineAPI, this package's own); the rendering lives on the base class.
    """


class RenderTypeSystem(TypeSystemAPI):
    """The type system with the render-narrowed suggestions ranked.

    The core type system answers `:` narrowing with the flat per-kind section;
    the render surface reads better ranked - the renders the chain itself
    endorses (its tools' supported_renders) and the ones whose declared
    item semantic names a level lead, the type-compatible rest follows. The
    wrapper is this package's decoration around the core service, so core keeps
    no render vocabulary.
    """

    def __init__(self, base: TypeSystemAPI, registry: ToolsRegistryAPI) -> None:
        """Wrap the core type system with the render ranking.

        Args:
            base: The core type system the folding and the checks delegate to
            registry: Tools registry the renders resolve from
        """
        self._base = base
        self._registry = registry

    def combine(self, ftd: ForestTypeDescriptor, descriptor: ToolDescriptor) -> ForestTypeDescriptor:
        return self._base.combine(ftd, descriptor)

    def require_source_for_output(self, ftd: ForestTypeDescriptor, output_ds: Iterable[ToolDescriptor], node) -> None:
        return self._base.require_source_for_output(ftd, output_ds, node)

    def suggest(
        self,
        ftd: ForestTypeDescriptor,
        pattern: str = "",
        tool_type: str = "",
        endorsed: Iterable[str] = (),
    ) -> dict[str, dict[str, ToolMetadata]]:
        """Ranked sections when narrowed to renders, the core's answer otherwise.

        Args:
            ftd: Forest type descriptor of the chain built so far
            pattern: Substring matched against the name, the domain-qualified name,
                and the aliases
            tool_type: Kind filter; the render filter gets the ranked sections
            endorsed: Render names declared by the chain's tools

        Returns:
            Dict of section heading -> canonical render name -> metadata
        """
        if tool_type != RENDER.name:
            return self._base.suggest(ftd, pattern, tool_type, endorsed)
        levels = [depth.name for depth in ftd.depths]
        level_identities = levels + [depth.semantic for depth in ftd.depths if depth.semantic]
        endorsed_names = set(endorsed)
        semantic: dict[str, ToolMetadata] = {}
        compatible: dict[str, ToolMetadata] = {}
        metadatas = self._registry.get_metadatas(kind=RENDER)
        for name, r_m in sorted((n, m) for n, m in metadatas.items() if n == m.name):
            if _is_semantic_render(r_m, endorsed_names, set(level_identities)):
                semantic[name] = r_m
            elif fits_chain(r_m, levels):
                compatible[name] = r_m
        sections: dict[str, dict[str, ToolMetadata]] = {}
        if semantic:
            sections["Semantic renders:"] = semantic
        if compatible:
            sections["Type-compatible renders:"] = compatible
        return sections


def _is_semantic_render(metadata: ToolMetadata, supported: set[str], level_identities: set[str]) -> bool:
    """Does this render match the chain semantically?

    Args:
        metadata: Metadata of the render
        supported: Render names declared by the chain's tools (canonical names and aliases)
        level_identities: Item-type names and semantics of the forest levels built so far

    Returns:
        True when the render is named by the chain's supported_renders or its declared
        item semantic names one of the levels (a level carries its meaning either as the
        declared semantic, e.g. "fruit", or as the item-type name itself, e.g. "CommitInfo")
    """
    if supported & ({metadata.name} | set(metadata.meta.get("aliases", []))):
        return True
    item_semantic = metadata.meta.get("item_semantic")
    return item_semantic is not None and item_semantic in level_identities


class RendersPlugin(Plugin):
    """The package's container contribution.

    Providing the render engine contributes the output step: the service the core
    calls to turn an applied forest into text. The decorations are what make it
    reachable without any core module naming it - the core's own output engine and
    type system are replaced by the rendering ones.
    """

    @provide
    def render_engine(
        self,
        logger: LoggerAPI,
        registry: ToolsRegistryAPI,
        attribute_storage: AttributeStorageAPI,
    ) -> RenderEngineAPI:
        """Create the render engine: the service that renders a forest to text.

        Args:
            logger: Logger instance
            registry: Tools registry the renders resolve from
            attribute_storage: The store the rendered attribute values are read from

        Returns:
            The render engine
        """
        return RenderEngine(logger=logger, registry=registry, attribute_storage=attribute_storage)

    @decorate
    def output_engine_with_renders(self, fallback: OutputEngineAPI, render: RenderEngineAPI) -> OutputEngineAPI:
        """Answer the core's output seam with the render engine.

        Args:
            fallback: The core's own output engine (no output package enabled);
                replaced, not wrapped - rendering is the whole answer
            render: The render engine this package provides

        Returns:
            The render engine, under the core's output contract
        """
        return render

    @decorate
    def type_system_with_renders(self, base: TypeSystemAPI, registry: ToolsRegistryAPI) -> TypeSystemAPI:
        """Rank the render-narrowed suggestions; the core answers for everything else."""
        return RenderTypeSystem(base, registry)


DOMAIN = "renders"
PLUGIN = RendersPlugin
