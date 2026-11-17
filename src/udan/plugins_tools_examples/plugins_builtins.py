import re
from collections.abc import Iterable
from typing import Annotated, Any, Literal, TypedDict

from udan.core.api_exceptions import ExceptionWithAdvice
from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_forests import Item
from udan.core.utils_binding import convert_value
from udan.core_tools_loading.api_annotated import annotated
from udan.core_tools_loading.api_tools import ToolMetadata
from udan.core_tools_loading.api_tools_registry import ToolsRegistryAPI

DOMAIN = "builtins"

# Constants
DEFAULT_LIMIT = 10
_DO_ON_LEVEL_MIN_ARGS = 2  # Minimum args for do_on_level (level and operator_name)
_DO_ON_LEVEL_ARGS_OFFSET = 2  # Offset to get operator args after level and operator_name


class PluginInfo(TypedDict):
    """Type for plugin information returned by plugins inserter."""

    name: str
    domain: str
    count: int


@annotated(meta={"tool_type": "replacer", "aliases": ["uniq"]})
def unique(items: list[Any]) -> list[Any]:
    """Remove duplicate items.

    Keeps only the first occurrence of each unique item.
    For integers and strings, uses direct equality.
    For other types, converts to string for comparison.
    """
    seen = set()
    result = []
    for item in items:
        # Use item itself as key for integers, str for others
        key = item if isinstance(item, int) else str(item)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


@annotated(meta={"tool_type": "replacer"})
def limit(items: list[Any], limit: int = DEFAULT_LIMIT, offset: int = 0) -> list[Any]:
    """Limit the number of items to the first n items, with optional offset.

    Args:
        items: List of items to limit
        limit: Maximum number of items to return (default: 10). Use -1 for unlimited.
        offset: Number of items to skip from the start (default: 0)

    Returns:
        Up to `limit` items starting from `offset`
    """
    if limit < 0:
        # -1 or any negative value means unlimited
        return items[offset:]
    return items[offset : offset + limit]


@annotated(meta={"tool_type": "replacer"})
def map_field(items: list[Any], field: str) -> list[Any]:
    """Replace each item with one of its native object fields.

    Extracts fields from objects using their native attributes or dict keys.
    Use this to extract object properties like .name from Path objects.

    Args:
        items: List of items to transform
        field: Field name to extract from each item

    Returns:
        List of field values, one per input item

    Examples:
        # Extract .name from Path objects
        ls_files tests, map_field name

        # Extract dict keys
        fruits, map_field color
    """
    result = []
    for item in items:
        if isinstance(item, dict):
            result.append(item.get(field))
        else:
            result.append(getattr(item, field, None))
    return result


@annotated(meta={"tool_type": "mapper", "item_type": "any", "output_type": "str"})
def as_str(item: Item) -> str:
    """Convert each item to its string representation.

    Applies str() to every item in the tree, so a structure of dicts, models or
    numbers becomes a structure whose elements are str. Useful before grouping or
    sorting items by their string form.

    Args:
        item: The item to stringify

    Returns:
        str() of the input item

    Examples:
        # Stringify fruit dicts
        fruits, as_str

        # Nested tree, all levels stringified
        range 3, multiply 2, as_str
    """
    return str(item)


# $field substitution in extend_by_inserter passthrough arguments: "$name" reads a
# dict key or object attribute of the item being extended, "$$" is a literal $
_ITEM_FIELD_RE = re.compile(r"\$(\$|[A-Za-z_][A-Za-z0-9_]*)")

_NO_FIELD = object()  # sentinel: getattr result that means the attribute is missing


def _substitute_item_fields(value: str, item: Item, inserter_name: str) -> str:
    """Substitute $field tokens in a passthrough argument with the item's values.

    Args:
        value: Argument string possibly containing $field tokens
        item: The item being extended
        inserter_name: Name of the inner inserter, for the error message

    Returns:
        String with every $field replaced by str() of the item's field value;
        $$ becomes a literal $ and $item the stringified item itself

    Raises:
        ExceptionWithAdvice: If a referenced field is missing on the item
    """

    def _field_value(token: str) -> str:
        if token == "$":
            return "$"
        if token == "item":
            return str(item)
        if isinstance(item, dict):
            if token in item:
                return str(item[token])
        else:
            attr_value = getattr(item, token, _NO_FIELD)
            if attr_value is not _NO_FIELD:
                return str(attr_value)
        raise ExceptionWithAdvice(
            f"extend_by_inserter: '${token}' names no field of the item ({item!r}); "
            f"arguments of '{inserter_name}' can only reference fields the item has"
        )

    return _ITEM_FIELD_RE.sub(lambda match: _field_value(match.group(1)), value)


def _bind_inserter_args(entries: list[Any], inner_m: ToolMetadata, item: Item) -> dict[str, Any]:
    """Bind passthrough entries to the inner inserter's parameters.

    An entry containing '=' binds the named parameter (dashes to underscores,
    $field tokens substituted first); an entry without '=' feeds the inner
    inserter's first unbound positional parameter, with $field tokens
    substituted the same way. Values are typed with the inner inserter's own
    parameter schema, exactly like --key=value binding.

    Args:
        entries: Passthrough entries following the inserter name
        inner_m: Metadata of the inner inserter
        item: The item being extended ($field substitution source)

    Returns:
        Bound arguments for the inner inserter call

    Raises:
        ExceptionWithAdvice: If an entry names an unknown parameter, a required
            parameter is left unbound, or a positional entry has no parameter left
    """
    props = (inner_m.parameters or {}).get("properties", {})
    bound: dict[str, Any] = {}
    positional: list[Any] = []

    for entry in entries:
        if isinstance(entry, str) and "=" in entry:
            key, _, raw_value = entry.partition("=")
            key = key.strip().replace("-", "_")
            if key not in props:
                raise ExceptionWithAdvice(
                    f"extend_by_inserter: '{inner_m.name}' has no parameter '{key}' "
                    f"(its parameters: {', '.join(props) or 'none'})"
                )
            value = _substitute_item_fields(raw_value, item, inner_m.name)
            bound[key] = convert_value(props, key, value)
        elif isinstance(entry, str):
            positional.append(_substitute_item_fields(entry, item, inner_m.name))
        else:
            positional.append(entry)

    if positional:
        for prop_name in props:
            if prop_name in bound:
                continue
            if not positional:
                break
            bound[prop_name] = convert_value(props, prop_name, positional.pop(0))
        if positional:
            raise ExceptionWithAdvice(
                f"extend_by_inserter: '{inner_m.name}' has no parameter left for "
                f"{positional} (its parameters: {', '.join(props) or 'none'})"
            )

    required = (inner_m.parameters or {}).get("required", [])
    for prop_name in required:
        if prop_name not in bound:
            raise ExceptionWithAdvice(f"extend_by_inserter: '{inner_m.name}' needs '{prop_name}' bound per item")
    return bound


@annotated(meta={"tool_type": "extender", "item_type": "any", "output_type": "any"})
def extend_by_inserter(
    item: Item,
    args: Annotated[list[Any], "vararg"],
    registry: ToolsRegistryAPI | None = None,
    ctx: ExecContextAPI | None = None,
) -> Iterable[Any]:
    """Extend each item with the output of an inserter called for that item.

    The inserter runs once per item and its items become that item's children.
    This is the generic "inserter as extender": the inserter is reused verbatim,
    with its arguments derived from the item instead of a duplicated extender.

    The first argument names the inserter (a qualified name like git.insert_diff).
    The remaining arguments are passed through to it:
    - 'key=value' binds its named parameter; $field tokens in the value are
      replaced by the item's field values before the call ($$ is a literal $,
      $item the stringified item)
    - a value without '=' feeds its first unbound positional parameter, $field
      tokens substituted the same way

    Values are typed with the inserter's own parameter schema.

    Args:
        item: The item being extended
        args: Inserter name followed by its passthrough arguments
        registry: Tools registry (injected)
        ctx: Execution context (injected)

    Returns:
        Iterable of the inserter's items for this item

    Examples:
        menu, extend_by_inserter fruits
        fruits, extend_by_inserter 'insert_fruits' 'pattern=berry'
        git.commits ., extend_by_inserter 'insert_diff' 'commit_arg=$commit_hash^..$commit_hash' 'directory=$repo_path'
    """
    if registry is None or ctx is None:
        raise ExceptionWithAdvice(
            "extend_by_inserter needs the query machinery (registry, exec context); use it in a query chain"
        )
    entries = list(args)
    if not entries:
        raise ExceptionWithAdvice(
            "extend_by_inserter needs an inserter name: "
            "extend_by_inserter 'git.insert_diff' 'commit_arg=$commit_hash^..$commit_hash'"
        )

    name, *passthrough = entries
    if not isinstance(name, str) or not name.strip():
        raise ExceptionWithAdvice(
            f"extend_by_inserter: inserter name must be a non-empty string, got {name!r}; "
            f"example: extend_by_inserter 'git.insert_diff' 'commit_arg=$commit_hash^..$commit_hash'"
        )

    # Resolve the name, accepting a domain-qualified form ('git.insert_diff' -> bare 'insert_diff'
    # registered in the 'git' domain); the registry is an injected parameter of this tool,
    # so the lookup happens here rather than in a helper taking the service as an argument
    metadata = registry.get_metadata(name)
    key = name
    if metadata is None and "." in name:
        domain, _, bare_name = name.rpartition(".")
        candidate = registry.get_metadata(bare_name)
        if candidate is not None and candidate.meta.get("domain", "") == domain:
            metadata, key = candidate, bare_name
    if metadata is None:
        raise ExceptionWithAdvice(
            f"extend_by_inserter: no tool '{name}' is registered; "
            f"use an inserter name (a qualified one like 'git.insert_diff')"
        )
    # the inserter kind is a plugin kind, so the guard matches the kind by name
    if metadata.tool_type != "inserter":
        raise ExceptionWithAdvice(
            f"extend_by_inserter: '{name}' is a {metadata.tool_type}, not an inserter; "
            f"extend_by_inserter re-runs an inserter once per item"
        )
    inner_fn = registry.get_function(key)
    if inner_fn is None:
        raise ExceptionWithAdvice(f"extend_by_inserter: inserter '{name}' has no registered function")

    call_kwargs = _bind_inserter_args(passthrough, metadata, item)
    inserted = inner_fn(ctx=ctx, **call_kwargs)
    if inserted is None:
        return
    yield from inserted


@annotated(meta={"tool_type": "replacer", "is_nested": True})
def sgrep(pattern: str, nodes: list[Any]) -> list[tuple[int, Any]]:
    """Search items in nested tree.

    This operator extracts items from a specific depth level in a nested
    tree structure by parsing 'depth=X' from the pattern parameter.

    Args:
        pattern: Pattern string in format 'depth=X' where X is the depth level
        nodes: List of Node objects with nested children (used for tree traversal)

    Returns:
        List of (depth, item) tuples for items at the specified depth

    Examples:
        After `menu, extend_menu_fruits`:
        - sgrep depth=0 returns [(0, "day-1"), (0, "day-2"), (0, "day-3"), (0, "day-4")]
        - sgrep depth=1 returns [(1, {"name": "apple", "quantity": 1}), (1, {"name": "orange", "quantity": 1}), ...]

    Note:
        This operator expects Node objects with a `children` attribute containing
        nested items, forming a tree structure.
    """
    # Parse depth from pattern string (format: "depth=X")
    depth_match = re.search(r"depth=(\d+)", pattern)
    if not depth_match:
        # Default to depth 0 if pattern doesn't match
        depth = 0
    else:
        depth = int(depth_match.group(1))

    results = []

    def traverse_nodes(node_list: list[Any], current_depth: int):
        """Recursively traverse nodes and collect items at target depth."""
        for node in node_list:
            # Check if this is a Node-like object
            if hasattr(node, "item") and hasattr(node, "children"):
                # This is a Node object
                if current_depth == depth:
                    results.append((current_depth, node.item))

                # Recurse into children
                if node.children:
                    traverse_nodes(node.children, current_depth + 1)
            # This is a plain item, not a Node
            elif current_depth == depth:
                results.append((current_depth, node))

    traverse_nodes(nodes, 0)
    return results


@annotated(meta={"tool_type": "sorter", "item_type": "any"})
def sort_by_natural_order(item: Item) -> int | str:
    return item if isinstance(item, int) else str(item)


@annotated(meta={"tool_type": "sorter", "item_type": "any"})
def sort_by_field(item: Item, field: str, desc: bool = False) -> Any:
    """Sort items by a field.

    Works on dict items (field = key) and on object items (field = attribute),
    e.g. fruits (dicts) and vegetables (pydantic models).

    Args:
        item: Item to extract field from
        field: Field name to sort by; a leading '-' reverses the order
              (e.g. `sort_by_field -calories` is descending)
        desc: Sort in descending order (default False). Note: This is handled by
              the sorting logic, not this function. The parameter exists for
              CLI argument parsing.

    Returns:
        Field value from the item (for dict or object)

    Note:
        This sorter also checks attribute values if the field is not found
        on the item itself. Attributes are calculated on-demand when needed.
    """
    # desc parameter is used by apply_sorter, not here
    if isinstance(item, dict):
        return item.get(field)
    else:
        return getattr(item, field, None)


@annotated(meta={"tool_type": "grouper", "item_type": "any"})
def group_by_field(item: Item, field: str) -> Any:
    """Group items by a field.

    Works on dict items (field = key) and on object items (field = attribute).

    Args:
        item: Item to extract field from
        field: Field name to group by

    Returns:
        Field value from the item (for dict or object)
    """
    if isinstance(item, dict):
        return item.get(field)
    else:
        return getattr(item, field, None)


@annotated(meta={"tool_type": "filter", "item_type": "any", "aliases": ["grep"]})
def has_pattern(item: Item, pattern: str) -> bool:
    """Check if pattern matches the item.

    For dicts, checks if pattern is in any of the dict's values.
    For other types, checks if pattern is in the string representation.
    """
    if isinstance(item, dict):
        # For dicts, check all values
        return any(pattern in str(v) for v in item.values())
    else:
        return pattern in str(item)


@annotated(meta={"tool_type": "filter", "item_type": "any", "aliases": ["grepv"]})
def has_not_pattern(item: Item, pattern: str) -> bool:
    """Check if pattern does NOT match the item (inverse of grep).

    For dicts, checks if pattern is NOT in any of the dict's values.
    For other types, checks if pattern is NOT in the string representation.

    This is equivalent to grep -v - it removes items matching the pattern.
    """
    if isinstance(item, dict):
        # For dicts, check all values
        return not any(pattern in str(v) for v in item.values())
    else:
        return pattern not in str(item)


@annotated(meta={"tool_type": "filter", "item_type": "any"})
def greps(item: Item, patterns: Annotated[list[str], "vararg"]) -> bool:
    """Check if item matches multiple pattern conditions with AND logic.

    Each pattern argument is interpreted as:
    - If pattern starts with '-': item must NOT contain the pattern (grepv)
    - Otherwise: item must contain the pattern (grep)

    ALL conditions must be satisfied for the item to pass through.

    Args:
        item: The item to check (dict or other type)
        patterns: List of pattern strings to check (vararg)

    Returns:
        True if item satisfies all pattern conditions, False otherwise

    Examples:
        fruits, greps alice bob -john
        # Returns items that have 'alice' AND have 'bob' AND do NOT have 'john'

        fruits, greps berry -blue
        # Returns items that have 'berry' but do NOT have 'blue'
    """
    for pattern in patterns:
        if pattern.startswith("-"):
            # Negative condition: pattern must NOT match
            neg_pattern = pattern[1:]  # Remove the '-' prefix
            if isinstance(item, dict):
                if any(neg_pattern in str(v) for v in item.values()):
                    return False
            elif neg_pattern in str(item):
                return False
        # Positive condition: pattern must match
        elif isinstance(item, dict):
            if not any(pattern in str(v) for v in item.values()):
                return False
        elif pattern not in str(item):
            return False
    return True


@annotated(meta={"tool_type": "grouper", "item_type": "any"})
def group_by_intervals(item: Item, args: Annotated[list, "vararg"]) -> str | None:
    """Group items into interval-based labels based on a field value.

    This grouper takes a field name and interval boundaries, then returns
    a string label indicating which interval the field value falls into.
    Works on dict items (field = key) and on object items (field = attribute).

    Args:
        item: The item to check (dict or object with attributes)
        args: List containing [field_name, boundary1, boundary2, ...]
              - field_name: Name of the field to check (e.g., "calories")
              - boundaries: Numeric interval boundaries (e.g., [10, 60] creates intervals: <10, [10,60), >=60)

    Returns:
        String label in format "(..low)", "[low..high)", or "[high..)" indicating the interval,
        or None if the field value is not numeric or not found

    Examples:
        >>> group_by_intervals({"calories": 5}, ["calories", 10, 60])
        "(..10)"
        >>> group_by_intervals({"calories": 15}, ["calories", 10, 60])
        "[10..60)"
        >>> group_by_intervals({"calories": 80}, ["calories", 10, 60])
        "[60..)"
        >>> group_by_intervals({"calories": None}, ["calories", 10, 60])
        None
    """
    if not args:
        return None

    # First argument is the field name
    field = args[0]
    if not isinstance(field, str):
        return None

    # Remaining arguments are interval boundaries
    intervals = args[1:]
    if not intervals:
        return None

    value = _get_field_value(item, field)
    if value is None:
        return None

    # Check if the value is numeric (int or float)
    if not isinstance(value, (int, float)):
        return None

    # Sort intervals to ensure proper ordering
    # Convert to numbers, preferring int over float when possible
    def to_number(x: Any) -> int | float:
        """Convert value to int or float, preferring int when possible."""
        if isinstance(x, int):
            return x
        if isinstance(x, float):
            return x
        # Try converting string to int first, then float
        try:
            return int(x)
        except ValueError, TypeError:
            return float(x)

    sorted_intervals = sorted([to_number(x) for x in intervals])

    # Find which interval the value falls into
    # Format: (..first), [first..second), ..., [last..)
    for i, boundary in enumerate(sorted_intervals):
        if value < boundary:
            # Before the first boundary
            if i == 0:
                return f"(..{boundary})"
            else:
                # Between two boundaries
                prev = sorted_intervals[i - 1]
                return f"[{prev}..{boundary})"

    # After the last boundary
    last = sorted_intervals[-1]
    return f"[{last}..)"


def _convert_string_to_numeric(value: str, field_value: Any) -> Any:
    """Convert string value to numeric type matching field_value.

    Args:
        value: String value to convert
        field_value: Field value to match type with

    Returns:
        Converted numeric value or original string if conversion fails
    """
    if not isinstance(value, str) or not isinstance(field_value, (int, float)):
        return value
    try:
        if "." in value:
            return float(value)
        else:
            return int(value)
    except ValueError:
        return value


def _get_field_value(item: Item, key: str) -> Any:
    """Extract field value from dict or object.

    Args:
        item: Dict item or object with attributes
        key: Field name to extract

    Returns:
        Field value or None if not found
    """
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def _check_identity_operator(field_value: Any, operator: str, value: Any) -> bool | None:
    """Handle identity operators (is, is not).

    Args:
        field_value: Value to check
        operator: "is" or "is not"
        value: Value to compare against

    Returns:
        True/False if handled, None if not an identity operator
    """
    if operator not in ("is", "is not"):
        return None

    # Convert string "None" to Python None
    if isinstance(value, str) and value == "None":
        value = None

    if operator == "is":
        return field_value is value
    else:
        return field_value is not value


def _get_comparison_function(operator: str) -> Any | None:
    """Get comparison function for operator.

    Args:
        operator: Comparison operator string

    Returns:
        Comparison function or None if operator not found
    """
    comparisons = {
        "=": lambda a, b: a == b,
        "!=": lambda a, b: a != b,
        "<": lambda a, b: a < b,
        "<=": lambda a, b: a <= b,
        ">": lambda a, b: a > b,
        ">=": lambda a, b: a >= b,
        "contains": lambda a, b: b in str(a),
        "startswith": lambda a, b: str(a).startswith(str(b)),
        "endswith": lambda a, b: str(a).endswith(str(b)),
        "in": lambda a, b: a in b,
        "not_in": lambda a, b: a not in b,
    }
    return comparisons.get(operator)


@annotated(meta={"tool_type": "filter", "item_type": "any"})
def filter_field(
    item: Item,
    key: str,
    operator: Literal[
        "=", "!=", "<", "<=", ">", ">=", "==", "contains", "startswith", "endswith", "in", "not_in", "is", "is not"
    ],
    value: Any,
) -> bool:
    """Filter items by comparing a specific field's value.

    Provides direct field-based filtering without needing to define attributes
    first. More convenient than filter_by_attribute for simple filtering
    operations. Works on dict items (key = dict key) and on object items
    (key = attribute).

    Args:
        item: Item to filter (dict or object with attributes)
        key: Field name to extract from the item
        operator: Comparison operator:
                - Equality: "=", "==", "!=", "in", "not_in"
                - Identity: "is", "is not" (for None checks)
                - Ordering: "<", "<=", ">", ">=" (for numeric/string comparison)
                - String matching: "contains", "startswith", "endswith"
        value: Value to compare against

    Returns:
        True if the item passes the filter, False otherwise

    Examples:
        # Filter help_list to show only inserters
        help_list, filter_field type==inserter

        # Filter items where count > 5
        items, filter_field count>5

        # Filter by string field
        items, filter_field namestartswith==user

        # Filter for None values
        items, filter_field description is None
        items, filter_field description 'is not' None
    """
    field_value = _get_field_value(item, key)

    # Handle identity operators (is, is not) for None values
    identity_result = _check_identity_operator(field_value, operator, value)
    if identity_result is not None:
        return identity_result

    # Handle None values for other operators
    if field_value is None:
        return False

    # Normalize operator for equality checks
    if operator == "==":
        operator = "="

    # Convert value to match field_value type for numeric comparisons
    numeric_operators = ("<", "<=", ">", ">=", "=", "!=")
    if operator in numeric_operators:
        value = _convert_string_to_numeric(value, field_value)

    # Get and execute comparison function
    compare_func = _get_comparison_function(operator)
    if compare_func is None:
        return False

    try:
        return compare_func(field_value, value)
    except TypeError, AttributeError:
        return False


@annotated(meta={"tool_type": "inserter", "output_type": "str"})
def raiser() -> list[str]:
    """Insert nothing and raise an exception for testing purposes.

    This inserter always raises a RuntimeError with a descriptive message.
    Useful for testing error handling and tracing.

    Raises:
        RuntimeError: Always raised with a test message
    """
    raise RuntimeError("Test exception from raiser inserter")


@annotated(meta={"tool_type": "inserter", "output_type": "plugin_info"})
def plugins(pattern: str = "", registry: ToolsRegistryAPI | None = None) -> list[PluginInfo]:
    """Insert list of available plugins with their metadata.

    Each plugin dictionary contains:
    - name: Plugin name (e.g., "builtins", "git", "python")
    - domain: Plugin domain if set (e.g., "builtins", "demo", "git")
    - count: Number of tools provided by the plugin

    Args:
        registry: Tools registry (injected dependency)
        pattern: Filter plugins by name pattern (e.g., "git" for git-related plugins)

    Returns:
        List of dictionaries with plugin information

    Example:
        >>> plugins
        - {name: 'builtins', domain: 'builtins', count: 42}
        - {name: 'demo', domain: 'demo', count: 8}
        - {name: 'git', domain: 'git', count: 5}

        >>> plugins git
        - {name: 'git', domain: 'git', count: 5}
    """
    if registry is None:
        return []

    # Get all tools from registry
    tools = registry.get_tools()

    # Group by domain
    plugins_data: dict[str, PluginInfo] = {}

    for name in tools:
        metadata = registry.get_metadata(name)
        if metadata is None:
            continue

        # Skip aliases (only count canonical names)
        if name != metadata.name:
            continue

        domain = metadata.meta.get("domain", "builtins")

        # Initialize plugin entry if not exists
        if domain not in plugins_data:
            plugins_data[domain] = {
                "name": domain,
                "domain": domain,
                "count": 0,
            }

        plugins_data[domain]["count"] += 1

    # Convert to list
    results = list(plugins_data.values())

    # Filter by pattern if provided
    if pattern:
        results = [p for p in results if pattern.lower() in p["name"].lower()]

    # Sort by name for consistent output
    results.sort(key=lambda p: p["name"])
    return results


@annotated(meta={"tool_type": "replacer", "is_nested": True})
def flatten(nodes: list[Any]) -> list[tuple[int, Any]]:
    """Flatten nested tree structure so all items appear at depth 0.

    Converts a nested parent-child tree into a flat list where children
    become siblings at the same level. All depth information is removed.

    Args:
        nodes: List of Node objects with nested children (tree structure)

    Returns:
        List of (depth, item) tuples with all items at depth 0

    Examples:
        # Flatten nested structure
        range 3, multiply 2, flatten

        # After multiply 2 creates:
        #   0
        #    0
        #   1
        #    2
        #   2
        #    4
        # flatten produces all items at depth 0:
        #   0
        #   0
        #   1
        #   2
        #   2
        #   4
    """
    results = []

    def traverse(node_list: list[Any]):
        """Recursively traverse nodes and collect all items at depth 0."""
        for node in node_list:
            if hasattr(node, "item") and hasattr(node, "children"):
                # Add item at depth 0
                results.append((0, node.item))

                # Recurse into children
                if node.children:
                    traverse(node.children)

    traverse(nodes)
    return results


@annotated(meta={"tool_type": "replacer", "is_nested": True, "aliases": ["chains", "zip_children"]})
def flat_children(nodes: list[Any]) -> Iterable[tuple[int, Any]]:
    """Flatten parent-child nested structures into flat (parent, child) tuples.

    Each parent at depth 0 is paired with each of its children at depth 1.
    The output is a flat list where all tuples are at depth 0.

    Args:
        nodes: List of Node objects with nested children (tree structure)

    Yields:
        (depth, tuple) tuples with all parent-child pairs at depth 0

    Examples:
        range 3, multiply 2, flat_children
        # Output: [(0, (0, 0)), (0, (1, 2)), (0, (2, 4))]

        range 1 3, multiply 2 3, flat_children
        # Output: [(0, (1, 2)), (0, (1, 3)), (0, (2, 4)), (0, (2, 6))]
    """
    for node in nodes:
        if hasattr(node, "item") and hasattr(node, "children"):
            parent = node.item

            # Pair parent with each child
            if node.children:
                for child_node in node.children:
                    if hasattr(child_node, "item"):
                        pair = (parent, child_node.item)
                        yield (0, pair)
