"""Demo plugin with generic example tools for testing the engine.

Fruit-specific tools and data live in plugins_fruits.
"""

import builtins
import sys
from collections.abc import Iterable
from typing import Annotated, Any

from udan.core.api_exceptions import ExceptionWithAdvice
from udan.core_tools_loading.api_annotated import annotated
from udan.core_tools_loading.api_types import Group

DOMAIN = "demo"

TOTAL_ITEMS = 100


@annotated(meta={"tool_type": "inserter", "output_type": "int"})
def range(a: int | str, b: int | str | None = None, c: int | str | None = None) -> list[int]:
    """Generate a sequence of numbers, similar to Python's range().

    Accepts 1, 2, or 3 arguments:
    - range(stop): range(5) generates [0, 1, 2, 3, 4]
    - range(start, stop): range(2, 5) generates [2, 3, 4]
    - range(start, stop, step): range(0, 10, 2) generates [0, 2, 4, 6, 8]

    Args:
        a: First argument (stop if only arg, or start)
        b: Second argument (stop if provided, or None)
        c: Third argument (step if provided, or None)

    Returns:
        List of integers in the specified range
    """
    # Convert string arguments to int (from query parsing)
    if isinstance(a, str):
        a = int(a)
    if isinstance(b, str):
        b = int(b)
    if isinstance(c, str):
        c = int(c)

    if b is None:
        # range(stop)
        return list(builtins.range(a))
    elif c is None:
        # range(start, stop)
        return list(builtins.range(a, b))
    else:
        # range(start, stop, step)
        return list(builtins.range(a, b, c))


@annotated(meta={"tool_type": "extender", "item_type": "int", "output_type": "int"})
def extend_multiply(item: int, mults: Annotated[list[int] | None, "vararg"] = None) -> list:
    """Extend items by multiplying with multiple multipliers.

    For an item N with mults=[M1, M2, ...], creates children N*M1, N*M2, ...

    Args:
        item: The number to multiply
        mults: List of multipliers (defaults to [2] if not provided or empty)

    Returns:
        List of multiplied values, one per multiplier

    Examples:
        - For item 2 with mults=[2]: extends to [4]
        - For item 5 with mults=[2, 3]: extends to [10, 15]
        - For item 3 with mults=[2, 3, 4]: extends to [6, 9, 12]
    """
    if not mults:
        mults = [2]
    # Convert string arguments to int (from query parsing)
    mults_ints = [int(m) if isinstance(m, str) else m for m in mults]
    return [item * m for m in mults_ints]


@annotated(meta={"attribute_type": "simple"})
def is_even(item: int) -> bool | None:
    """Check if a number is even.

    Args:
        item: An integer to check

    Returns:
        True if the number is even, False if odd, None if not an integer

    Examples:
        - is_even(2) -> True
        - is_even(3) -> False
        - is_even(0) -> True
        - is_even("2") -> None
    """
    if not isinstance(item, int):
        return None
    return item % 2 == 0


@annotated(meta={"attribute_type": "simple"})
def is_odd(item: int) -> bool | None:
    """Check if a number is odd.

    Args:
        item: An integer to check

    Returns:
        True if the number is odd, False if even, None if not an integer

    Examples:
        - is_odd(3) -> True
        - is_odd(2) -> False
        - is_odd(0) -> False
        - is_odd("2") -> None
    """
    if not isinstance(item, int):
        return None
    return item % 2 == 1


@annotated(meta={"tool_type": "grouper", "item_type": "int"})
def group_by_modulo(item: int, n: int | str = 2) -> Group:
    """Group numbers by the remainder of division by ``n``.

    Args:
        item: The number to group
        n: The divisor (default 2)

    Returns:
        Group keyed by ``"<item % n>(mod <n>)"``, e.g. ``"0(mod 2)"``

    Examples:
        - range 6, group_by_modulo 2 -> group=0(mod 2) [0, 2, 4], group=1(mod 2) [1, 3, 5]
        - range 6, group_by_modulo 3 -> group=0(mod 3) [0, 3], group=1(mod 3) [1, 4], group=2(mod 3) [2, 5]
    """
    if isinstance(n, str):
        n = int(n)
    return Group(key=f"{item % n}(mod {n})")


@annotated(meta={"attribute_type": "simple"})
def div_3(item: int) -> int | None:
    """Get the remainder when dividing by 3.

    Args:
        item: An integer to check

    Returns:
        The remainder when dividing by 3 (0, 1, or 2), or None if not an integer

    Examples:
        - div_3(3) -> 0
        - div_3(4) -> 1
        - div_3(5) -> 2
        - div_3(6) -> 0
        - div_3("3") -> None
    """
    if not isinstance(item, int):
        return None
    return item % 3


@annotated(meta={"attribute_type": "simple"})
def add_values(
    item: int | float,
    increments: Annotated[list[int | float] | None, "vararg"] = None,
) -> list[int | float] | None:
    """Add values to a number, returning multiple results.

    Takes a numeric item and adds each increment from the list to it, returning
    a list of results. Useful in queries like: range 5, extend_by_attribute (add_values 1 2)

    Args:
        item: The numeric value to add to.
        increments: List of values to add to the item.

    Returns:
        List of item + each increment value.

    Examples:
        - add_values(5, [1, 2]) -> [6, 7]
        - add_values(10, [5]) -> [15]
        - add_values(5, []) -> []
    """
    # Only process numeric items
    if not isinstance(item, (int, float)):
        return None
    if not increments:
        return []
    # Convert string arguments to int (from query parsing)
    increments_converted = [int(inc) if isinstance(inc, str) else inc for inc in increments]
    return [item + inc for inc in increments_converted]


@annotated(meta={"attribute_type": "simple"})
def double(item: Any, value: str | None = None) -> Any:
    """Double the item, or the value of another attribute (pass its name).

    Args:
        item: The numeric item to double
        value: Name of another attribute whose value to double instead
            (e.g. ``double(div_3)``). An attribute reference arrives resolved
            to its value; a bare query literal (``double 2``) cannot resolve
            and is rejected.

    Returns:
        Doubled value, or None if the item is not numeric
    """
    if value is None:
        return item * 2 if isinstance(item, (int, float)) and not isinstance(item, bool) else None
    if isinstance(value, str):
        raise ExceptionWithAdvice(
            f"double expects an attribute name, got unresolvable literal {value!r}. "
            f"Pass an attribute reference like double(div_3), or no argument to double the item."
        )
    return value * 2


@annotated(meta={"tool_type": "inserter", "output_type": "str"})
def menu() -> list[str]:
    """Insert menu items representing days.

    Returns a list of days that can be extended with fruit data.

    Returns:
        List of day identifiers: ["day-1", "day-2", "day-3", "day-4"]

    Examples:
        menu                    -> ["day-1", "day-2", "day-3", "day-4"]
        menu, extend menu_fruits -> days extended with fruit data
    """
    return ["day-1", "day-2", "day-3", "day-4"]


@annotated(meta={"tool_type": "inserter", "output_type": "str"})
def bool_demo(reverse: bool = False, uppercase: bool = False) -> list[str]:
    """Demo generator to test boolean flag arguments.

    This operator generates a list of items and uses boolean flags
    to control transformation behavior.

    Args:
        reverse: If True, reverse the order of items (default False)
        uppercase: If True, convert items to uppercase (default False)

    Returns:
        List of strings with transformations applied

    Examples:
        - bool_demo              -> ["a", "b", "c"]
        - bool_demo --reverse    -> ["c", "b", "a"]
        - bool_demo --uppercase  -> ["A", "B", "C"]
        - bool_demo --reverse --uppercase -> ["C", "B", "A"]
        - bool_demo --noreverse  -> ["a", "b", "c"]
    """
    items = ["a", "b", "c"]

    if uppercase:
        items = [item.upper() for item in items]

    if reverse:
        items = list(reversed(items))

    return items


@annotated(meta={"tool_type": "inserter", "output_type": "str"})
def self_insert(arg: str = "nothing passed") -> list[str]:
    """Insert a single string item equal to the given argument.

    Args:
        arg: The string to insert (defaults to "nothing passed")

    Returns:
        List containing the argument as a single item

    Examples:
        - self_insert abc -> ["abc"]
        - self_insert     -> ["nothing passed"]
    """
    return [arg]


@annotated(meta={"tool_type": "inserter", "output_type": "any"})
def varargs(args: Annotated[list[Any], "vararg"]) -> list:
    """Demo inserter that accepts variable arguments.

    This inserter takes any number of arguments and returns them as a list.
    No other arguments are allowed when using varargs.

    Args:
        args: List of all positional arguments passed to the inserter

    Returns:
        List of the arguments passed to the inserter

    Examples:
        - varargs                -> []
        - varargs 1              -> [1]
        - varargs 1 2 3          -> [1, 2, 3]
        - varargs a b c          -> ["a", "b", "c"]
    """
    return args


@annotated(meta={"tool_type": "inserter", "output_type": "any"})
def varargs_extra(args: Annotated[list[Any], "vararg"], extra: str = "extra") -> list:
    """Demo inserter with varargs plus a named parameter after the vararg.

    Positional arguments are collected into the ``args`` vararg list, while the
    named ``--extra`` parameter is bound separately. The ``extra`` value is
    appended as the last item.

    Args:
        args: List of all positional arguments passed to the inserter
        extra: Named parameter appended as the last item (default "extra")

    Returns:
        List of the positional arguments followed by the ``extra`` value

    Examples:
        - varargs_extra 1 2                  -> [1, 2, "extra"]
        - varargs_extra 1 2 --extra=tail     -> [1, 2, "tail"]
    """
    return [*args, extra]


def _trace(msg: str) -> None:
    """Print a trace line to stderr immediately (unbuffered relative to stdout)."""
    print(f"[lazy-trace] {msg}", file=sys.stderr, flush=True)


@annotated(meta={"tool_type": "inserter", "output_type": "int"})
def range_lazy(items: int = TOTAL_ITEMS, infinite: bool = False) -> Iterable[int]:
    """Lazily yield integers, tracing every item the engine pulls.

    Args:
        items: How many items the source can produce in total
        infinite: Produce items forever (never exhausts)

    Yields:
        Integers 0, 1, 2, ...
    """
    _trace(f"range_lazy: generator CREATED (capacity={items}, infinite={infinite}) - nothing produced yet")
    counter = 0
    while True:
        if not infinite and counter >= items:
            break
        _trace(f"range_lazy: pull #{counter}")
        yield counter
        counter += 1
    if not infinite:
        _trace(f"range_lazy: SOURCE EXHAUSTED after {counter} pulls")


@annotated(meta={"tool_type": "extender", "item_type": "int", "output_type": "int"})
def extend_shift_lazy(item: int) -> Iterable[int]:
    """Lazily extend every integer item with two derived items, tracing each call.

    Args:
        item: The item being extended

    Yields:
        Two integers derived from the item
    """
    _trace(f"extend_shift_lazy: asked to extend item={item}")
    for shift in (0, 1):
        _trace(f"extend_shift_lazy: yield child {item * 10 + shift} for item={item}")
        yield item * 10 + shift


@annotated(meta={"tool_type": "filter", "item_type": "int"})
def filter_even_lazy(item: int) -> bool:
    """Keep even items, tracing every item the engine asks about.

    Args:
        item: The candidate item

    Returns:
        True for even items
    """
    _trace(f"filter_even_lazy: asked about item={item} -> {item % 2 == 0}")
    return item % 2 == 0
