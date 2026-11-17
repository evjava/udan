from typing import Any

from udan.core.api_attributes import AttributeDescriptor
from udan.core_tools_loading.api_annotated import annotated

DOMAIN = "test_interp_complex"


@annotated
def inserter_numbers() -> list[int]:
    """Test inserter that returns numbers 1, 2, 3."""
    return [1, 2, 3]


@annotated(meta={"tool_type": "filter"})
def filter_even(item: Any) -> bool:
    """Filter that keeps only even numbers."""
    return isinstance(item, int) and item % 2 == 0


@annotated(meta={"tool_type": "extender", "output_type": "int"})
def extender_double(item: int) -> list[int]:
    """Extender that doubles the number."""
    if isinstance(item, int):
        return [item * 2]
    return []


@annotated(meta={"tool_type": "replacer"})
def replacer_list() -> list[str]:
    """Replacer that returns a fixed list."""
    return ["a", "b", "c"]


@annotated(meta={"attribute_type": "simple"})
def attribute_square(item: int) -> int:
    """Attribute that squares the number."""
    return item * item


@annotated(meta={"tool_type": "filter", "aliases": ["operator_alias"]})
def operator_with_alias(item: Any, pattern: str = "test") -> bool:
    """Operator with an alias for testing."""
    return pattern in str(item)


@annotated(meta={"tool_type": "extender", "output_type": "any"})
def operator_with_at_d(item: Any, at_d: AttributeDescriptor) -> list[Any]:
    """Test operator that takes an at_d parameter."""
    return [item]


@annotated(
    meta={"tool_type": "inserter"},
    tags={"numbers"},
)
def get_numbers(n: int, lim: int = 3) -> list[str]:
    """Test operator with parameters and tags."""
    return [ii * n for ii in range(lim)]


@annotated
def insert_numbers_extra() -> list[int]:
    """Test operator without metadata."""
    return [0, 1, 2]


@annotated(meta={"tool_type": "inserter"})
def cur() -> list[str]:
    """Inserter named 'cur' for testing exact match."""
    return ["exact_match"]


@annotated(meta={"tool_type": "inserter"})
def current() -> list[str]:
    """Inserter named 'current' - should not match when searching for 'cur'."""
    return ["should_not_match"]


@annotated(meta={"tool_type": "inserter"})
def cursor() -> list[str]:
    """Inserter named 'cursor' - should not match when searching for 'cur'."""
    return ["should_not_match"]


@annotated(meta={"attribute_type": "simple"})
def attribute_with_param(item: int, multiplier: int) -> int:
    """Attribute that multiplies the item by a given multiplier."""
    return item * multiplier


@annotated(meta={"attribute_type": "simple"})
def attribute_tag_checker(item: Any, tag: str) -> bool:
    """Attribute that checks if item has a specific tag.

    Stands in for an attribute an external package declares: 'item' is the
    framework-injected parameter, the rest are user parameters.
    """
    # For testing, assume item is a dict with 'tags' key
    if isinstance(item, dict):
        tags = item.get("tags", [])
        return tag in tags
    return False


@annotated(meta={"attribute_type": "simple", "domain": "external_test"})
def external_attribute_with_param(item: Any, external_param: str) -> bool:
    """Attribute with the injected item and a further user parameter.

    Stands in for an attribute an external package declares: 'item' is the
    framework parameter, 'external_param' the user's.
    """
    # Check some property of the item
    return external_param in str(item)
