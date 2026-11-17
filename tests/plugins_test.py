from typing import Any

from udan.core_tools_loading.api_annotated import annotated
from udan.core_tools_loading.api_types import Group

DOMAIN = "test"


class Item:
    def __init__(self, name: str, value: int):
        self.name = name
        self.value = value


@annotated(meta={"attribute_type": "simple"})
def modulo(item: int, k: int) -> str:
    return str(item % k)


@annotated(meta={"attribute_type": "simple"})
def modulo_2(item: int) -> str:
    return str(item % 2)


@annotated(meta={"tool_type": "inserter"})
def insert_test_numbers() -> list[int]:
    return [0, 1, 2]


@annotated(meta={"tool_type": "filter"})
def filter_keep_div(item: Any, div: int) -> bool:
    return isinstance(item, int) and item % div == 0


@annotated(meta={"attribute_type": "simple"})
def is_odd(item: int) -> bool:
    return item % 2 == 1


@annotated(meta={"attribute_type": "simple"})
def is_even(item: int) -> bool:
    return item % 2 == 0


@annotated(meta={"attribute_type": "simple"})
def text_label(item: int) -> str:
    return f"aa-{item}-bb"


@annotated(meta={"attribute_type": "value"})
def extract_tags(text: str) -> list[str]:
    """Value-shaped attribute: text -> tags. No `item` parameter, so it can only
    compute from its arguments -- a valid composition target."""
    return [w for w in text.split("-") if w]


@annotated(meta={"attribute_type": "value"})
def count_tags(tags: list) -> int:
    """Value-shaped attribute over a list value: tail of a composition chain."""
    return len(tags)


@annotated(meta={"attribute_type": "simple", "dependencies": {"n1_flag": "n1"}})
def uses_n1_flag(item: int, n1_flag: bool | None = None) -> bool:
    """Depends on the named cattr column 'n1' (queries define it with --name=n1).

    Used to verify that named cattr columns can serve as dependency targets for
    regular registered attributes.
    """
    return bool(n1_flag)


@annotated(meta={"attribute_type": "simple", "dependencies": ["mutual_b"]})
def mutual_a(item: int, mutual_b: int | None = None) -> int:
    """Mutual dependency cycle half: depends on mutual_b, which depends back."""
    return (mutual_b or 0) + 1


@annotated(meta={"attribute_type": "simple", "dependencies": ["mutual_a"]})
def mutual_b(item: int, mutual_a: int | None = None) -> int:
    """Mutual dependency cycle half: depends on mutual_a, which depends back."""
    return (mutual_a or 0) + 1


@annotated(meta={"tool_type": "inserter", "is_nested": True})
def insert_nested_123() -> list[tuple[int, int]]:
    return [(0, 1), (1, 2), (2, 3)]


@annotated(meta={"tool_type": "inserter", "is_nested": True})
def insert_nested_multiple() -> list[tuple[int, str]]:
    return [(0, "a"), (0, "b"), (1, "c")]


@annotated(meta={"tool_type": "inserter", "is_nested": True})
def insert_nested_complex() -> list[tuple[int, str]]:
    return [
        (0, "root1"),
        (1, "child1"),
        (2, "grandchild1"),
        (1, "child2"),
        (0, "root2"),
        (1, "child3"),
    ]


@annotated
def insert_simple_values() -> list[dict]:
    return [
        {"id": "a", "value": 3},
        {"id": "b", "value": 1},
        {"id": "c", "value": None},
        {"id": "d", "value": 2},
    ]


@annotated
def insert_test_numbers_1_to_4() -> list[int]:
    return [1, 2, 3, 4]


@annotated
def insert_single_number() -> list[int]:
    return [4]


@annotated(meta={"tool_type": "extender", "output_type": "int"})
def extend_div2(item: int) -> list:
    if not isinstance(item, int):
        return []
    if item == 1:
        return []
    if item % 2 == 1:
        return []
    return [item // 2]


@annotated
def group_by_parity(item) -> str:
    if isinstance(item, int):
        return "even" if item % 2 == 0 else "odd"
    return "other"


@annotated(meta={"tool_type": "grouper"})
def group_by_parity_ordered(item) -> Group:
    """Return a Group with an explicit order (odd before even)."""
    if isinstance(item, int):
        if item % 2 == 0:
            return Group(key="even", order=2)
        return Group(key="odd", order=1)
    return Group(key="other", order=3)


@annotated(meta={"tool_type": "grouper"})
def group_by_parity_plain_group(item) -> Group:
    """Return a plain Group (no order) to test non-rewrapping behavior."""
    if isinstance(item, int):
        if item % 2 == 0:
            return Group(key="even")
        return Group(key="odd")
    return Group(key="other")


@annotated
def insert_dicts() -> list[dict]:
    return [
        {"name": "charlie", "value": 3},
        {"name": "alice", "value": 1},
        {"name": "bob", "value": 2},
    ]


@annotated
def insert_items() -> list[Item]:
    return [
        Item(name="charlie", value=3),
        Item(name="alice", value=1),
        Item(name="bob", value=2),
    ]


@annotated
def insert_duplicates() -> list:
    return [1, 2, 1, 3, 2, 4, 3, 5]


@annotated
def insert_duplicate_strings() -> list:
    return ["apple", "banana", "apple", "cherry", "banana", "date"]


@annotated
def insert_duplicate_dicts() -> list:
    return [
        {"name": "alice", "value": 1},
        {"name": "bob", "value": 2},
        {"name": "alice", "value": 1},
        {"name": "charlie", "value": 3},
        {"name": "bob", "value": 2},
    ]


@annotated
def filter_greater_than(item: Any, threshold: int) -> bool:
    return isinstance(item, int) and item > threshold


@annotated
def insert_items_with_none_scores() -> list[dict]:
    return [
        {"name": "alice", "score": 10},
        {"name": "bob", "score": None},
        {"name": "charlie", "score": 5},
        {"name": "dave", "score": None},
        {"name": "eve", "score": 15},
    ]


@annotated
def get_numbers(n: int, lim: int = 3) -> list[str]:
    return [ii * n for ii in range(lim)]


@annotated
def insert_numbers() -> list[int]:
    return [0, 1, 2]


@annotated(meta={"tool_type": "inserter"})
def some_test_inserter(value: int = 42) -> list[int]:
    return [value]
