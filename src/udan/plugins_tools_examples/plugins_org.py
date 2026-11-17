"""Org-mode file plugins for udan.

Provides inserters and filters for working with org-mode files.
"""

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from udan.core.api_forests import Item
from udan.core_tools_loading.api_annotated import annotated
from udan.plugins_tools_examples.api_types import ASTChunk
from udan.plugins_tools_examples.plugins_dev import Duplication
from udan.plugins_tools_examples.plugins_org_parser import OrgItem, parse_date, parse_org_file
from udan.plugins_tools_examples.utils_file_line import parse_file_line_reference

DOMAIN = "org"


# Image file extensions that should be rendered as images
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".bmp"}


# Org headline: one or more stars, a space, then the title
ORG_HEADLINE = re.compile(r"^(\*+)\s")

# Org property line: a descriptive list item like "- city :: London"
ORG_PROPERTY_LINE = re.compile(r"^\s*-\s*(.+?)\s*::\s*(.*)$")

# Row field holding the title of the section a row was built from
SECTION_NAME_FIELD = "name"


# Org section table helpers


def _org_headline_level(line: str) -> int:
    """Return the level of an org headline line (its number of stars), 0 for a non-headline line."""
    match = ORG_HEADLINE.match(line)
    return len(match.group(1)) if match else 0


def _org_headline_title(line: str) -> str:
    """Return the title of an org headline line (the text after the stars)."""
    match = ORG_HEADLINE.match(line)
    return line[match.end() :].strip() if match else ""


def _org_section_start(lines: list[str], index: int) -> int | None:
    """Return the index of the headline opening the section containing the given 0-based index."""
    start = index
    while start >= 0 and _org_headline_level(lines[start]) == 0:
        start -= 1
    return start if start >= 0 else None


def _org_section_end(lines: list[str], start: int) -> int:
    """Return the index after the last line of the section opened by the headline at start.

    Body lines belong to the section; the next headline at the section's own
    level or shallower ends it.
    """
    level = _org_headline_level(lines[start])
    end = start + 1
    while end < len(lines):
        line_level = _org_headline_level(lines[end])
        if line_level and line_level <= level:
            break
        end += 1
    return end


def _org_section_properties(lines: list[str], start: int, end: int) -> dict[str, str]:
    """Read the "- key :: value" lines of a section body into a dict, keys in file order."""
    properties = {}
    for body_line in lines[start + 1 : end]:
        match = ORG_PROPERTY_LINE.match(body_line)
        if match:
            properties[match.group(1)] = match.group(2).strip()
    return properties


def _org_section_rows(lines: list[str], start: int) -> list[dict]:
    """Build one row per child section of the section opened by the headline at start.

    Child sections are the headlines one level deeper than the root; each
    contributes its title under SECTION_NAME_FIELD and the "- key :: value"
    lines of its body, its own sub-sections included.
    """
    level = _org_headline_level(lines[start])
    rows = []
    index = start + 1
    while index < len(lines):
        child_level = _org_headline_level(lines[index])
        if child_level and child_level <= level:
            break
        if child_level == level + 1:
            child_end = _org_section_end(lines, index)
            row = {SECTION_NAME_FIELD: _org_headline_title(lines[index])}
            row.update(_org_section_properties(lines, index, child_end))
            rows.append(row)
            index = child_end
        else:
            index += 1
    return rows


def _pad_rows_to_columns(rows: list[dict]) -> list[dict]:
    """Give every row every column: properties a row lacks become empty strings."""
    columns = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    return [{column: row.get(column, "") for column in columns} for row in rows]


# Org-mode inserter tools


@annotated(
    meta={
        "tool_type": "inserter",
        "output_type": "OrgItem",
        "aliases": ["cur", "curs"],
        "supported_renders": ["org"],
    }
)
def insert_cur_items(path: str = "cur.org") -> list[OrgItem]:
    """Insert items from an org-mode file or directory.

    Args:
        path: Path to the org file or directory (default: cur.org)

    Returns:
        List of OrgItem objects

    If a directory is passed, recursively scans all .org files in the directory.
    """
    path_obj = Path(path).expanduser()

    if path_obj.is_dir():
        # Recursively find all .org files in directory
        items = []
        for org_file in sorted(path_obj.rglob("*.org")):
            items.extend(parse_org_file(str(org_file)))
        return items
    else:
        return parse_org_file(path)


@annotated(meta={"tool_type": "inserter", "output_type": "dict"})
def org_table_from_section_with_properties(location: str, line: int | str | None = None) -> Iterable[dict]:
    """Insert the child sections of the org section at the given location as dicts.

    The referenced line names the root section: the sections inside it (the
    headlines one level deeper) become the rows, and the "- key :: value" lines
    of a row's body become its fields under the keys they were written with. The
    section title itself goes to the name field. Rows are padded to the columns
    of the table: a property some sections lack becomes an empty string. Use the
    universal :entries render to prettify the rows.

    Args:
        location (str): File path, either "path:line" or just "path"; a path
            without a line reads from the first line.
        line (int | str): Optional line number, when location is passed without one.

    Yields:
        dict: One entry per child section, e.g. {"name": "alice", "city": "London", "age": "20"}.

    Examples:
        org_table_from_section_with_properties "example.org:2", :entries
        org_table_from_section_with_properties "example.org" 2, :entries
        org_table_from_section_with_properties "example.org", :entries
    """
    if line is None:
        parsed = parse_file_line_reference(location)
        if parsed is None:
            parsed = (Path(location), 1)
        file_path, line_number = parsed
    else:
        file_path, line_number = Path(location), int(line)

    if not file_path.is_file():
        return

    lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    index = line_number - 1
    if not 0 <= index < len(lines):
        return
    start = _org_section_start(lines, index)
    if start is None:
        return
    yield from _pad_rows_to_columns(_org_section_rows(lines, start))


@annotated(meta={"tool_type": "filter", "item_type": "OrgItem"})
def date_after(item: OrgItem, date_str: str) -> bool:
    """Filter items by date after a given date.

    Args:
        item: An OrgItem to check
        date_str: Date string in format DD.MM.YY-HH:MM:SS

    Returns:
        True if the item's date is after the given date
    """
    if not isinstance(item, OrgItem):
        return False
    if not item.date:
        return False

    item_date = parse_date(item.date)
    filter_date = parse_date(date_str)

    if item_date is None or filter_date is None:
        return False

    return item_date >= filter_date


@annotated(meta={"tool_type": "filter", "item_type": "OrgItem"})
def date_before(item: OrgItem, date_str: str) -> bool:
    """Filter items by date before a given date.

    Args:
        item: An OrgItem to check
        date_str: Date string in format DD.MM.YY-HH:MM:SS

    Returns:
        True if the item's date is before the given date
    """
    if not isinstance(item, OrgItem):
        return False
    if not item.date:
        return False

    item_date = parse_date(item.date)
    filter_date = parse_date(date_str)

    if item_date is None or filter_date is None:
        return False

    return item_date <= filter_date


@annotated(meta={"attribute_type": "simple"})
def org_title(item: OrgItem) -> str:
    """Get the title of an org item."""
    if isinstance(item, OrgItem):
        return item.title
    return ""


@annotated(meta={"attribute_type": "simple"})
def org_tags(item: OrgItem) -> str:
    """Get the tags of an org item as comma-separated string."""
    if isinstance(item, OrgItem):
        return ",".join(item.tags)
    return ""


@annotated(meta={"attribute_type": "simple"})
def org_date(item: OrgItem) -> str:
    """Get the date of an org item."""
    if isinstance(item, OrgItem):
        return item.date
    return ""


@annotated(meta={"attribute_type": "simple"})
def org_inline_image(item: str | Path) -> str:
    """Return org-mode inline image link for a file path.

    Generates [[path][path]] syntax that org-mode interprets as an inline image link.

    Args:
        item: File path as str or Path.

    Returns:
        Org-mode link string like [[path-to-image][path-to-image]].
    """
    path = Path(item) if isinstance(item, str) else item
    s = str(path)
    return f"[[{s}][{s}]]"


@annotated(meta={"attribute_type": "simple"})
def org_image(item: str | Path, width: int | None = None) -> str:
    """Return bare org-mode image link for image files, empty string for non-images.

    Body-line counterpart of render_org_images: emits ``[[path]]``, and only for
    image files (IMAGE_EXTENSIONS). Non-images return "", so
    ``extend_by_attribute org_image`` adds no body child for them.

    Args:
        item: File path as str or Path.
        width: Optional image width; when passed, emits a
            ``#+ATTR_ORG: :width <width>`` line before the link so org-mode
            scales the inline image.

    Returns:
        Org-mode link string like [[/full/path/to/image.png]] for images,
        prefixed with ``#+ATTR_ORG: :width <width>\\n`` when width is passed,
        empty string otherwise.

    Examples:
        ls_files images "*.*", file_name, org_image, extend_by_attribute org_image, :org-structure --headline=file_name

        # headline-attr: file_name
        ** screenshot.png
        [[/full/path/to/images/screenshot.png]]

        With width:

        ls_files images "*.*", file_name, extend_by_attribute (org_image --width=300), :org-structure

        # headline-attr: file_name
        ** screenshot.png
        #+ATTR_ORG: :width 300
        [[/full/path/to/images/screenshot.png]]
    """
    path = Path(item) if isinstance(item, str) else item
    if isinstance(path, Path) and path.suffix.lower() in IMAGE_EXTENSIONS:
        link = f"[[{path}]]"
        if width is not None:
            return f"#+ATTR_ORG: :width {width}\n{link}"
        return link
    return ""


# Org-mode render tools


def _render_org_item(item: OrgItem, indent: str) -> str:
    """Render an OrgItem in org-mode format."""
    stars = "*" * item.level
    lines = [f"{indent}{stars} {item.title}"]
    if item.date:
        lines.append(f"{indent}date: {item.date}")
    if item.tags:
        lines.append(f"{indent}tags: {', '.join(item.tags)}")
    if item.content and item.content.strip():
        lines.append(f"{indent}{item.content}")
    return "\n".join(lines)


def _render_org_item_content(item: Item, indent: str, depth: int = 0) -> str:
    """Render the content of an org item (without attribute name prefix)."""
    # Handle OrgItem objects
    if isinstance(item, OrgItem):
        return _render_org_item(item, indent)

    # Handle ASTChunk objects
    if isinstance(item, ASTChunk):
        return render_org_astchunk(item, depth)

    # Handle Duplication objects
    if isinstance(item, Duplication):
        return _render_org_duplication(item, depth)

    # Determine number of asterisks based on depth
    stars = "*" * (depth + 1)

    if isinstance(item, dict):
        return _render_org_dict(item, indent, stars)

    # Non-dict items: heading line has no indent
    return f"{stars} {str(item)}"


def render_org_astchunk(item: ASTChunk, depth: int) -> str:
    """Render an ASTChunk in org-mode format with :PROPERTIES: and source block."""
    stars = "*" * (depth + 1)
    if item.type == "duplication":
        heading = f"{item.source_file}:{item.line_start_number}-{item.line_end_number}"
    else:
        type_symbol = "def" if item.type == "function" else "class"
        heading = f"{type_symbol} {item.name}"
    lines = [f"{stars} {heading}"]
    lines.append(":PROPERTIES:")
    lines.append(f":source_file: {item.source_file}:{item.line_start_number}-{item.line_end_number}")
    if item.docstring:
        first_line = item.docstring.split("\n")[0]
        lines.append(f":docstring: {first_line}")
    lines.append(":END:")
    lines.append("#+begin_src python")
    for code_line in item.full_code.splitlines():
        lines.append(f"  {code_line}")
    lines.append("#+end_src")
    return "\n".join(lines)


def _render_org_duplication(item: Duplication, depth: int) -> str:
    """Render a Duplication as org heading with summary."""
    stars = "*" * (depth + 1)
    return f"{stars} {item}"


def _get_dict_title(item: dict) -> str:
    """Extract title from a dict for org-mode rendering."""
    title_parts = []
    if "function" in item:
        title_parts.append(item["function"])
    if "fpath" in item:
        fpath = item["fpath"]
        # Show just the filename, not full path
        if "/" in fpath:
            fpath = fpath.split("/")[-1]
        title_parts.append(fpath)
    # For generic dicts without function/fpath, use id and name if available
    elif "id" in item and "name" in item:
        title_parts.append(str(item["id"]))
        title_parts.append(str(item["name"]))

    return " ".join(title_parts) if title_parts else ""


def _render_org_dict(item: dict, indent: str, stars: str) -> str:
    """Render a dict in org-mode format with optional :PROPERTIES: block."""
    title = _get_dict_title(item)
    lines = []

    if title:
        lines.append(f"{stars} {title}")

    # Add :PROPERTIES: block if we have properties
    if item:
        lines.append(f"{indent}:PROPERTIES:")
        for key, value in item.items():
            lines.append(f"{indent}:{key}: {value}")
        lines.append(f"{indent}:END:")

    return "\n".join(lines)


@annotated(meta={"item_type": "OrgItem", "tool_type": "render", "aliases": ["org"]})
def render_org_generic(item: Item, indent: str = "", depth: int = 0, attrs: dict[str, Any] | None = None) -> str:
    """Render item in org-mode format with * heading and :PROPERTIES: block.

    Uses depth parameter to determine heading level:
    - depth 0: * (top level)
    - depth 1: ** (second level)
    - depth 2: *** (third level)
    etc.

    When attrs is provided (for single attribute display), shows:
    - attr_identity
    <org item content>
    """
    # Support both direct item and dict format for compatibility
    if isinstance(item, dict) and "item" in item:
        actual_item = item["item"]
        if attrs is None:
            attrs = item.get("attrs")
    else:
        actual_item = item

    # When rendering with an attribute, show attribute identity first
    if attrs:
        attr_identity = list(attrs.keys())[0]
        return f"{indent}- {attr_identity}\n{_render_org_item_content(actual_item, indent, depth)}"

    return _render_org_item_content(actual_item, indent, depth)


@annotated(meta={"item_type": "OrgItem", "tool_type": "render", "aliases": ["org-items"]})
def render_org_items(item: dict, indent: str = "") -> str:
    """Render dict items in org-mode property format."""
    if isinstance(item, dict):
        lines = [f"{indent}- {str(item)}"]
        for key, value in item.items():
            lines.append(f"{indent}  :{key}: {value}")
        return "\n".join(lines)
    return f"{indent}- {str(item)}"


@annotated(meta={"item_type": "OrgItem", "tool_type": "render", "aliases": ["org-item"]})
def render_org_item(item: dict, field1: str, field2: str, indent: str = "") -> str:
    """Render dict item as org-mode item with two fields.

    Args:
        item: Dict to render
        field1: First field name (e.g., "id")
        field2: Second field name (e.g., "name")
        indent: Indentation string

    Returns:
        Formatted string: "- {field1} :: {field2}"
    """
    if isinstance(item, dict):
        val1 = item.get(field1, "")
        val2 = item.get(field2, "")
        return f"{indent}- {val1} :: {val2}"
    return f"{indent}- {str(item)}"


@annotated(meta={"item_type": "OrgItem", "tool_type": "render", "aliases": ["images"]})
def render_org_images(item: str | Path, indent: str = "") -> str:
    """Render image file in org-mode inline image format.

    For image files (png, jpg, jpeg, gif, svg, webp, ico, bmp),
    renders in org-mode format for inline images:
    ** <path-to-image>
    [[path-to-image]]

    Args:
        item: Path or string representing a file
        indent: Indentation string

    Returns:
        Org-mode formatted inline image markup, or default org format for non-images
    """
    # Convert to Path if string
    if isinstance(item, str):
        item = Path(item)

    # Check if it's a Path object with image extension
    if isinstance(item, Path):
        if item.suffix.lower() in IMAGE_EXTENSIONS:
            path_str = str(item)
            return f"{indent}** {path_str}\n{indent}[[{path_str}]]"

    # Default: render as org-mode list item
    return f"{indent}- {str(item)}"


@annotated(meta={"item_type": "OrgItem", "tool_type": "render", "aliases": ["org-text"]})
def render_org_text(item: Item, indent: str = "", depth: int = 0, value: str = "", original_item: str = "") -> str:
    """Render extracted text content as org-mode with headline and text block.

    Used for attributes like extract_text that produce multiline text content.
    Shows the original item as a headline and the text content in a source block.

    Args:
        item: The item being rendered (or dict with attribute_value format)
        indent: Indentation string
        depth: Depth parameter
        value: The text content - passed via kwargs
        original_item: The original item for the headline - passed via kwargs

    Returns:
        Formatted string with org-mode headline and text content
    """
    if isinstance(item, dict) and item.get("_type") == "attribute_value":
        text_value = item["value"]
        headline_item = item.get("original_item") or item.get("item", "")
    elif value:
        text_value = value
        headline_item = original_item or item
    else:
        text_value = str(item)
        headline_item = ""

    lines = [f"{indent}* {headline_item}"]
    for text_line in str(text_value).splitlines():
        lines.append(f"{indent}{text_line}")
    return "\n".join(lines)


@annotated(meta={"item_type": "OrgItem", "tool_type": "render"})
def render_org_source_block(
    item: Item, indent: str = "", depth: int = 0, value: str = "", original_item: str = ""
) -> str:
    """Render attribute value as org-mode source block.

    This render formats attribute values as org-mode source blocks.

    When called from the rendering pipeline with custom attributes:
    - item: The original item (e.g., Path object)
    - value: The attribute value (Python code)
    - original_item: Passed via kwargs from the attribute_value dict

    When called directly with a dict:
    {"_type": "attribute_value", "value": <code>, "item": <original_item>}

    Args:
        item: The item being rendered (or dict with attribute_value format)
        indent: Indentation string
        value: The attribute value (code content) - passed via kwargs
        original_item: The original item for the headline - passed via kwargs

    Returns:
        Formatted string with org-mode headline and source block
    """
    # Handle dict format (direct calls or backward compatibility)
    if isinstance(item, dict) and item.get("_type") == "attribute_value":
        code_value = item["value"]
        headline_item = item.get("original_item") or item.get("item", "")
    elif value:
        # Handle kwargs format (called from rendering pipeline)
        code_value = value
        headline_item = original_item or item
    else:
        # Fallback for direct calls without proper format
        code_value = str(item)
        headline_item = ""

    lines = [
        f"{indent}* {headline_item}",
        f"{indent}#+begin_src python",
    ]
    for code_line in str(code_value).splitlines():
        lines.append(f"{indent}  {code_line}")
    lines.append(f"{indent}#+end_src")
    return "\n".join(lines)
