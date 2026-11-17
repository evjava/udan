"""Lazy tools that count how many items they produce.

Used to verify that the operator engine stops pulling lazy sources (db
cursors, files) once the auto-limit item cap is reached, instead of
materializing everything and truncating afterwards. Counters are module
globals: reset them at test start with reset_pulled_count().
"""

from collections.abc import Iterable

from udan.core_tools_loading.api_annotated import annotated

TOTAL_ITEMS = 100
SOURCE_BOUND_ITEMS = 200
SOURCE_BOUND_ERROR = "lazy source pulled past its bound"
pulled_count = 0
extended_count = 0


def reset_pulled_count() -> None:
    """Reset the pull counters (call at test start)."""
    global pulled_count, extended_count
    pulled_count = 0
    extended_count = 0


@annotated(meta={"tool_type": "inserter"})
def insert_lazy_counting() -> Iterable[int]:
    """Lazily yield TOTAL_ITEMS integers, counting each pulled item."""
    global pulled_count
    for i in range(TOTAL_ITEMS):
        pulled_count += 1
        yield i


@annotated(meta={"tool_type": "inserter"})
def insert_lazy_infinite() -> Iterable[int]:
    """Lazily yield integers, counting each pulled item, until the source's own bound.

    The bound is an exception, not a count: a query that drains the source fails
    with SOURCE_BOUND_ERROR in well under a second, where a counted bound of a
    million items spent that second materializing items the result drops anyway.
    """
    global pulled_count
    for i in range(SOURCE_BOUND_ITEMS):
        pulled_count += 1
        yield i
    raise RuntimeError(SOURCE_BOUND_ERROR)


@annotated(meta={"tool_type": "extender", "output_type": "int"})
def extend_lazy_counting(item: int) -> Iterable[int]:
    """Lazily extend each item with two children, counting each extended item."""
    global extended_count
    extended_count += 1
    yield item * 10
    yield item * 10 + 1
