"""Set operations for Forest variables.

This module provides set operations (intersect, union, difference) that work
with variables stored in the UdanContext symbol table.

Variables are automatically resolved to lists by the operator engine based on
the function signature's type annotations.
"""

from typing import Any

from udan.core.api_exec_context import ExecContextAPI
from udan.core_tools_loading.api_annotated import annotated

DOMAIN = "set_operations"


@annotated(meta={"tool_type": "inserter", "output_type": "any"})
def intersect(
    var_a: list,
    var_b: list,
    ctx: ExecContextAPI | None = None,
) -> list[Any]:
    """Return the intersection of two variables' forests.

    Returns items that exist in both variable a and variable b.

    Args:
        var_a: List of items from first variable (automatically resolved)
        var_b: List of items from second variable (automatically resolved)
        ctx: Execution context for debug output (injected)

    Returns:
        List of items that are in both forests

    Example:
        a := (numbers 0 20 3)
        b := (numbers 0 20 2)
        intersect a b
        # Output: [0, 6, 12, 18]
    """
    # Convert to sets for intersection, then back to list
    # Sort to maintain deterministic order
    result = sorted(set(var_a) & set(var_b))

    if ctx is not None:
        ctx.debug(f"intersect: {len(var_a)} items × {len(var_b)} items → {len(result)} items")

    return result


@annotated(meta={"tool_type": "inserter", "output_type": "any"})
def union(
    var_a: list,
    var_b: list,
    ctx: ExecContextAPI | None = None,
) -> list[Any]:
    """Return the union of two variables' forests.

    Returns items that exist in either variable a or variable b (or both).

    Args:
        var_a: List of items from first variable (automatically resolved)
        var_b: List of items from second variable (automatically resolved)
        ctx: Execution context for debug output (injected)

    Returns:
        List of items from both forests (no duplicates)

    Example:
        a := (numbers 0 10 3)
        b := (numbers 0 10 5)
        union a b
        # Output: [0, 3, 5, 6, 9]
    """
    # Convert to sets for union, then back to list
    # Sort to maintain deterministic order
    result = sorted(set(var_a) | set(var_b))

    if ctx is not None:
        ctx.debug(f"union: {len(var_a)} items + {len(var_b)} items → {len(result)} items")

    return result


@annotated(meta={"tool_type": "inserter", "output_type": "any"})
def difference(
    var_a: list,
    var_b: list,
    ctx: ExecContextAPI | None = None,
) -> list[Any]:
    """Return the difference of two variables' forests.

    Returns items that exist in variable a but NOT in variable b.
    In set notation: a \\ b

    Args:
        var_a: List of items from first variable (minuend, automatically resolved)
        var_b: List of items from second variable (subtrahend, automatically resolved)
        ctx: Execution context for debug output (injected)

    Returns:
        List of items from var_a that are not in var_b

    Example:
        a := (numbers 0 20 3)
        b := (numbers 0 20 2)
        difference a b
        # Output: [3, 9, 15] (multiples of 3 that are NOT multiples of 2)
    """
    # Convert to sets for difference, then back to list
    # Sort to maintain deterministic order
    result = sorted(set(var_a) - set(var_b))

    if ctx is not None:
        ctx.debug(f"difference: {len(var_a)} items - {len(var_b)} items → {len(result)} items")

    return result


@annotated(meta={"tool_type": "inserter", "output_type": "any"})
def symmetric_difference(
    var_a: list,
    var_b: list,
    ctx: ExecContextAPI | None = None,
) -> list[Any]:
    """Return the symmetric difference of two variables' forests.

    Returns items that exist in either variable a or variable b, but NOT in both.
    In set notation: a △ b or (a \\ b) ∪ (b \\ a)

    Args:
        var_a: List of items from first variable (automatically resolved)
        var_b: List of items from second variable (automatically resolved)
        ctx: Execution context for debug output (injected)

    Returns:
        List of items that are in exactly one of the forests

    Example:
        a := (numbers 0 10 3)
        b := (numbers 0 10 5)
        symmetric_difference a b
        # Output: [3, 5, 9] (items that are multiples of 3 OR 5, but NOT both)
    """
    # Convert to sets for symmetric difference, then back to list
    # Sort to maintain deterministic order
    result = sorted(set(var_a) ^ set(var_b))

    if ctx is not None:
        ctx.debug(f"symmetric_difference: {len(var_a)} items △ {len(var_b)} items → {len(result)} items")

    return result
