"""Aggregate attributes (Approach A: attribute_type='aggregate').

Aggregate attributes compute a single value from all items in scope.
They extend the attribute system with a new attribute_type='aggregate'.

Query syntax:  fruits, count
               fruits, fruit_cost, sum fruit_cost
               fruits, fruit_cost, min fruit_cost
               fruits, fruit_cost, max fruit_cost

Unlike simple/composite attributes (per-item), aggregate attributes:
- Receive all items as input (via 'items' parameter)
- Return a single value (count, sum, avg, etc.)
- Are stored in attribute_storage on the root node item, not per-item
"""

import math
from collections.abc import Callable
from enum import Enum
from typing import Any

from udan.attributes.api_attribute_contexts import AttributesContextAPI
from udan.core.api_attributes import ATTRIBUTE_TYPE_AGGREGATE, AttributeDescriptor
from udan.core.api_exceptions import OverrideForestException
from udan.core.api_forests import ForestBuilder, Item
from udan.core_tools_loading.api_annotated import annotated

DOMAIN = "aggregates"

AGG_META = {"attribute_type": ATTRIBUTE_TYPE_AGGREGATE}


class _ReduceOp(Enum):
    SUM = "sum"
    MIN = "min"
    MAX = "max"


def _attribute_column_value(attr_ctx: AttributesContextAPI, attr_name: str, item: Item) -> Any:
    """Read a named attribute column value for one item.

    get_attr_value handles both cases: storage hit (the value was materialized for
    this item) and lazy computation through the registered attribute - this covers
    named cattr columns referenced in a fresh query. Circular references are
    detected inside the attribute runtime.
    """
    return attr_ctx.get_attr_value(AttributeDescriptor.create(attr_name, args={}), item)


def _collect_numeric_values(
    items: list[Item], attr_name: str, attr_ctx: AttributesContextAPI | None = None
) -> list[float]:
    """Extract non-None numeric values for attr_name.

    Dict items are read from their fields (existing behaviour). Items without
    that field fall back to the attribute system when a context is available:
    stored values first, then lazy evaluation of the registered attribute (named
    cattr columns).
    """
    values: list[float] = []
    for item in items:
        v = item.get(attr_name) if isinstance(item, dict) else None
        # Fall back to the attribute system only for names that actually are
        # registered attributes (plain dict fields are not)
        if v is None and attr_ctx is not None and attr_ctx.registry.get_metadata(attr_name) is not None:
            v = _attribute_column_value(attr_ctx, attr_name, item)
        if v is not None:
            try:
                values.append(float(v))
            except ValueError, TypeError:
                pass
    return values


def _find_numeric_fields(items: list[Item]) -> list[str]:
    """Find dict keys that hold numeric values across items."""
    fields: dict[str, bool] = {}
    for item in items:
        if isinstance(item, dict):
            for key, val in item.items():
                if val is not None and key not in fields:
                    try:
                        float(val)
                        fields[key] = True
                    except ValueError, TypeError:
                        fields[key] = False
    return sorted(k for k, v in fields.items() if v)


def _raise_missing_attr(op_name: str, items: list[Item]) -> None:
    """Raise OverrideForestException listing aggregatable attributes as nested forest."""
    numeric_fields = _find_numeric_fields(items)
    builder = ForestBuilder()
    builder.add(f"'{op_name}' requires an attribute name:", depth=0)
    for field in numeric_fields:
        builder.add(field, depth=1)
    if not numeric_fields:
        builder.add("(no numeric fields found in items)", depth=1)
    raise OverrideForestException(builder.build_forest())


def _make_reducer(op: _ReduceOp) -> Callable[[list[float]], float]:
    """Return a reduction function for the given operation."""

    def _reduce_sum(values: list[float]) -> float:
        return math.fsum(values)

    def _reduce_min(values: list[float]) -> float:
        result = values[0]
        for v in values[1:]:
            if v < result:  # noqa: PLR1730
                result = v
        return result

    def _reduce_max(values: list[float]) -> float:
        result = values[0]
        for v in values[1:]:
            if v > result:  # noqa: PLR1730
                result = v
        return result

    return {_ReduceOp.SUM: _reduce_sum, _ReduceOp.MIN: _reduce_min, _ReduceOp.MAX: _reduce_max}[op]


def _make_numeric_aggregate(op: _ReduceOp, default: float, int_if_exact: bool = False, attr_required: bool = False):
    """Factory for numeric aggregate functions (sum, min, max)."""

    def aggregate(items: list[Item], attr_name: str = "", attr_ctx: AttributesContextAPI | None = None) -> float | int:
        if not attr_name:
            if attr_required:
                raise ValueError(f"'{op.value}' requires an attribute name (e.g. {op.value} calories)")
            return default
        values = _collect_numeric_values(items, attr_name, attr_ctx)
        if not values:
            return default
        result = _make_reducer(op)(values)
        if int_if_exact and result == int(result):
            return int(result)
        return result

    return aggregate


@annotated(meta=AGG_META)
def count(items: list[Item]) -> int:
    """Count all items in the forest.

    Query: fruits, count
    """
    return len(items)


@annotated(meta=AGG_META)
def sum(items: list[Item], attr_name: str = "", attr_ctx: AttributesContextAPI | None = None) -> int | float:
    """Sum a named attribute across all dict items.

    Query: fruits, fruit_cost, sum fruit_cost

    attr_name is required — use 'count' if you want the number of items.
    Items without the named field fall back to attribute values (named cattr
    columns included).
    """
    if not attr_name:
        _raise_missing_attr("sum", items)
    return _make_numeric_aggregate(_ReduceOp.SUM, default=0, int_if_exact=True)(items, attr_name, attr_ctx)


@annotated(meta=AGG_META)
def min(items: list[Item], attr_name: str = "", attr_ctx: AttributesContextAPI | None = None) -> float:
    """Minimum value of a named attribute across all dict items.

    Query: fruits, fruit_cost, min fruit_cost
    """
    return _make_numeric_aggregate(_ReduceOp.MIN, default=0.0)(items, attr_name, attr_ctx)


@annotated(meta=AGG_META)
def max(items: list[Item], attr_name: str = "", attr_ctx: AttributesContextAPI | None = None) -> float:
    """Maximum value of a named attribute across all dict items.

    Query: fruits, fruit_cost, max fruit_cost
    """
    return _make_numeric_aggregate(_ReduceOp.MAX, default=0.0)(items, attr_name, attr_ctx)
