"""JSON file plugin for reading and parsing JSON data.

This plugin provides inserters for reading JSON and JSONL files from the
filesystem and inserting their JSON elements as items.

Supports:
- Reading JSON files: one item per JSON element (an object file is a single item)
- Expanding a top-level JSON array into many items (`list=True`)
- Reading JSONL files (.jsonl): one item per line
- Extracting specific JSON paths using jq-like syntax
- Handling nested JSON structures
- Replacing string items with their parsed JSON values (`as_json`)
- Rendering item dicts as JSON strings
"""

import json
import re
from pathlib import Path

from udan.core.api_forests import Item
from udan.core_tools_loading.api_annotated import annotated
from udan.core_tools_loading.api_types import JsonValue

DOMAIN = "json"


def resolve_json_path(data: JsonValue, path: str) -> list[JsonValue]:
    """Resolve a jq-like path against parsed JSON data.

    Tokenizes the path into .key and [] segments, then walks the data.

    Args:
        data: Parsed JSON data (dict, list, or scalar)
        path: Path pattern, e.g. ".items[].name"

    Returns:
        List of matched items
    """
    tokens = re.findall(r"\.(\w+)|(\[\])", path)
    results: list[JsonValue] = [data]

    for dot_key, bracket in tokens:
        if bracket:
            results = [item for r in results if isinstance(r, list) for item in r]
        elif dot_key:
            results = [r[dot_key] for r in results if isinstance(r, dict) and dot_key in r]

    return results


def _load_json_elements(filepath: str | Path) -> list[JsonValue]:
    """Load the JSON elements of a file: one element for a JSON file, one per line for a JSONL file.

    Args:
        filepath: Path to a JSON or JSONL file (str or Path)

    Returns:
        Single-element list for a JSON file, one element per non-empty line for a .jsonl file

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file cannot be parsed as valid JSON
    """
    path = Path(filepath).expanduser()

    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {filepath}")

    try:
        with open(path, encoding="utf-8") as f:
            if path.suffix == ".jsonl":
                return [json.loads(line) for line in f if line.strip()]
            return [json.load(f)]
    except json.JSONDecodeError as e:
        raise ValueError(f"Error parsing JSON file: {e}")
    except OSError as e:
        raise ValueError(f"Error reading JSON file: {e}")


def _element_items(element: JsonValue) -> list[JsonValue]:
    """Expand one JSON element into items: a list becomes its entries, anything else stays one item.

    Args:
        element: Parsed JSON element (dict, list, or scalar)

    Returns:
        List of items for the element
    """
    if isinstance(element, list):
        return element
    return [element]


def _load_json_element(text: str) -> JsonValue:
    """Parse one string as a JSON element.

    Args:
        text: String holding a JSON element (object, array, or scalar)

    Returns:
        Parsed JSON element

    Raises:
        ValueError: If text cannot be parsed as valid JSON
    """
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError) as e:
        raise ValueError(f"Error parsing JSON: {e}")


@annotated(meta={"tool_type": "inserter", "output_type": "any"})
def read_json(filepath: str | Path, list: bool = True) -> list[JsonValue]:
    """Insert items from a JSON or JSONL file.

    Reads the file and inserts one item per JSON element: an object file inserts
    the whole element as a single item, an array file inserts one item per array
    entry, and a .jsonl file inserts one item per line.

    Args:
        filepath: Path to JSON file (str or Path)
            Example: "data.json" or "~/Documents/data.json"
        list: Whether a JSON array is expanded into many items (default: True).
            False keeps every array itself as a single item.

    Returns:
        List of items (dict, list, or scalar each)

    Raises:
        FileNotFoundError: If JSON file doesn't exist
        ValueError: If file cannot be parsed as valid JSON

    Example:
        >>> # JSON file with array (data.json)
        >>> # [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        >>> read_json "data.json"
        # Inserts: {"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}

        >>> # JSON file with object
        >>> # {"users": [{"id": 1, "name": "Alice"}]}
        >>> read_json "data.json"
        # Inserts: {"users": [{"id": 1, "name": "Alice"}]}

        >>> # Same object file, keeping the array inside as one item
        >>> read_json "data.json" list=False
        # Inserts: {"users": [{"id": 1, "name": "Alice"}]}
    """
    elements = _load_json_elements(filepath)
    if not list:
        return elements
    return [item for element in elements for item in _element_items(element)]


@annotated(meta={"tool_type": "inserter", "output_type": "dict", "aliases": ["json_glob"]})
def read_json_chunks(path: str | Path, jq_filter: str = ".") -> list[JsonValue]:
    """Extract items from a JSON or JSONL file using a jq-like filter.

    Reads the file and extracts items matching a jq-like filter pattern.
    Useful for extracting arrays from nested JSON structures. A .jsonl file
    is filtered line by line, and the matches of all lines are concatenated.

    Args:
        path: Path to JSON file (str or Path)
        jq_filter: jq-like filter pattern to extract items (default: ".")
            Use "." to insert the elements the same way read_json does
            Use ".items[]" to extract array elements
            Use ".users[].name" to extract specific fields

    Returns:
        List of items matching the filter pattern

    Raises:
        FileNotFoundError: If JSON file doesn't exist
        ValueError: If file cannot be parsed as valid JSON

    Example:
        >>> # JSON file (data.json)
        >>> # {"users": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]}
        >>> read_json_chunks "data.json" jq_filter=".users[]"
        # Inserts: {"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}

        >>> # Extract just names
        >>> read_json_chunks "data.json" jq_filter=".users[].name"
        # Inserts: "Alice", "Bob"
    """
    if jq_filter == ".":
        return read_json(path)

    return [item for element in _load_json_elements(path) for item in resolve_json_path(element, jq_filter)]


@annotated(meta={"tool_type": "replacer"})
def as_json(items: list[Item], list: bool = True) -> list[JsonValue]:
    """Replace string items with their parsed JSON values.

    Parses every item as JSON. A parsed array becomes many items by default:
    as_json on '[1, 2, 3]' inserts 1, 2, 3, not a single list item.

    Args:
        items: String items to parse as JSON
        list: Whether a parsed JSON array is expanded into many items (default: True).
            False keeps every array itself as a single item.

    Returns:
        List of parsed JSON values (dict, list, or scalar each)

    Raises:
        ValueError: If an item cannot be parsed as valid JSON

    Example:
        >>> # items: ['[1, 2, 3]']
        >>> as_json items
        # Inserts: 1, 2, 3

        >>> # items: ['{"users": [{"id": 1}]}']
        >>> as_json items
        # Inserts: {"users": [{"id": 1}]}

        >>> # Same array, kept as one item
        >>> as_json items list=False
        # Inserts: [1, 2, 3]
    """
    elements = [_load_json_element(item) for item in items]
    if not list:
        return elements
    return [item for element in elements for item in _element_items(element)]


def _pick_fields(item: dict, fields: list[str] | str | None) -> dict:
    """Filter item to the requested fields, keeping the order they are given in.

    Args:
        item: Dict to filter.
        fields: Field names to keep. Elements may carry comma-separated names
            ("title, tags"); None or empty means no filtering.

    Returns:
        Dict with only the requested fields that exist in item.
    """
    if fields is None:
        return item
    if isinstance(fields, str):
        fields = [fields]
    keys = [key.strip() for field in fields for key in field.split(",")]
    keys = [key for key in keys if key]
    if not keys:
        return item
    return {key: item[key] for key in keys if key in item}


@annotated(meta={"tool_type": "render", "aliases": ["json"]})
def render_json(item: dict, *fields: str, indent: str = "") -> str:
    """Render item dict as JSON string.

    Works with any dict - the item is serialized as-is, no domain model
    conversion happens.

    Args:
        item: Dict to render as JSON.
        fields: Fields to show, as separate arguments (query form:
            `:json title tags`, like `:table id entry`). A single argument may
            also be a comma-separated string. No arguments show all fields.
            Fields missing from the item are skipped.
        indent: Indentation string (unused, part of the render signature).

    Returns:
        Pretty-printed JSON string representation of the item.
    """
    return json.dumps(_pick_fields(item, list(fields)), ensure_ascii=False, indent=2, default=str)
