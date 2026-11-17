"""Test module for verifying lazy attribute evaluation.

Provides a tracking attribute that records which items it was called with,
so tests can verify attributes are only computed for items that survive filtering.
"""

from typing import Any

from udan.core_tools_loading.api_annotated import annotated

DOMAIN = "test_lazy_attrs"

# Shared call log: maps item -> number of times the attribute was computed
call_log: dict[Any, int] = {}


@annotated(meta={"tool_type": "filter"})
def is_odd(item: int) -> bool:
    """Filter: keep only odd numbers."""
    return item % 2 == 1


@annotated(meta={"tool_type": "filter"})
def is_even(item: int) -> bool:
    """Filter: keep only even numbers."""
    return item % 2 == 0


@annotated(meta={"attribute_type": "simple"})
def tracked_twice(item: int) -> int:
    """Attribute that tracks which items it was called on and returns item * 2."""
    call_log[item] = call_log.get(item, 0) + 1
    return item * 2


@annotated(meta={"attribute_type": "simple"})
def tracked_even(item: int) -> bool:
    """Boolean attribute that tracks its calls: which items were even."""
    call_log[item] = call_log.get(item, 0) + 1
    return item % 2 == 0


def reset_call_log() -> None:
    """Reset the call log before each test."""
    call_log.clear()
