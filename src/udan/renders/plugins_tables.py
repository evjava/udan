"""Table render tools.

Generic renders for tabular data (markdown tables, csv, ...).
These renders work for any items and are not tied to a specific source format.
"""

from udan.core.api_attributes import AttributeDescriptor
from udan.core.api_forests import Item
from udan.core.utils_binding import convert_boolean_string
from udan.core_tools_loading.api_annotated import annotated
from udan.renders.api_renders import SHAPE_CHILDREN
from udan.renders.plugins_renders import _apply_col_specs, _parse_col_spec

DOMAIN = "tables"

# -- entries format -----------------------------------------------------------


def entry_key_values(item: Item) -> list[tuple[str, str]]:
    """Extract (key, value) pairs for one entry; non-dict items get a single "item" field.

    Row-like items exposing a dict ``row_data`` (CsvRow) render one pair
    per column with full values, in the item's own column order.
    """
    return [(str(key), str(value)) for key, value in _entry_source_dict(item).items()]


def _entry_source_dict(item: Item) -> dict:
    """The dict whose fields one entry shows; non-dict items expose a single "item" field."""
    if isinstance(item, dict):
        return item
    row_data = getattr(item, "row_data", None)
    if isinstance(row_data, dict):
        return row_data
    return {"item": str(item)}


def _entry_key_values_with_fields(item: Item, col_specs: list[tuple[str, str, str]]) -> list[tuple[str, str]]:
    """(key, value) pairs for one entry restricted to the fields the col specs name."""
    row = _apply_col_specs([_entry_source_dict(item)], col_specs)[0]
    return [(str(key), str(value)) for key, value in row.items()]


def _render_entry_lines(entry: list[tuple[str, str]], entry_index: int, key_width: int) -> list[str]:
    """Render one entry as a header plus "key :: value" lines with keys padded to key_width."""
    lines = [f"** entry-{entry_index}"]
    lines.extend(f"- {key.ljust(key_width)} :: {value}" for key, value in entry)
    return lines


@annotated(
    meta={
        "item_type": "group",
        "tool_type": "render",
        "aliases": ["entries"],
        "shape": SHAPE_CHILDREN,
        "attribute_type": "aggregate",
    }
)
def render_entries(
    depths: list[int],
    children: list[Item],
    attr_ds: list[AttributeDescriptor],
    *fields: str,
    align: bool | str = True,
) -> str:
    """Render items as numbered entries with "key :: value" lines.

    Universal render for tabular row items: each item becomes one entry block
    with a "** entry-N" header and one "- key :: value" line per dict key.
    Non-dict items are rendered with a single "item" field.

    Keys are padded to the longest key across all items, so values start on
    the same level. Pass --align=False to disable padding.

    Args:
        depths: List of depth values for each item (not used, kept for signature)
        children: List of items to render
        attr_ds: Attribute descriptors (not used, kept for signature)
        *fields: Optional fields to render, in the order given (e.g. :entries name city).
                 Accepts the same "header:{attr:fmt}" specs as :table. A field an item
                 lacks renders with an empty value. Without fields all fields are rendered.
        align: Pad keys so values are aligned (default: True)

    Returns:
        Formatted string with one entry block per item.

    Examples:
        md_table "notes.md:3", :entries
        read_csv "data.csv", :entries
        read_csv "data.csv", :entries --align=False
        read_csv "data.csv", :entries name
        read_csv "data.csv", :entries name "cost:{price:.2f}"
    """
    if fields:
        col_specs = [_parse_col_spec(field) for field in fields]
        entries = [_entry_key_values_with_fields(item, col_specs) for item in children]
    else:
        entries = [entry_key_values(item) for item in children]
    aligned = convert_boolean_string(align) if isinstance(align, str) else align
    key_width = max((len(key) for entry in entries for key, _ in entry), default=0) if aligned else 0
    blocks = [
        "\n".join(_render_entry_lines(entry, entry_index, key_width))
        for entry_index, entry in enumerate(entries, start=1)
    ]
    return "\n".join(blocks)
