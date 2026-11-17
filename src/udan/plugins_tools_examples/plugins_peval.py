"""Plugin for Python expression pipe (peval) operator."""

from typing import Any

from udan.core.api_forests import Item
from udan.core_tools_loading.api_annotated import annotated

DOMAIN = "peval"


@annotated(meta={"tool_type": "mapper"})
def peval(item: Item, expr: str) -> Any:
    """Replace each item with the result of a Python expression.

    Evaluates a Python expression for each item, with 'it' as the item variable.
    Similar to pipe (|) in shell, but for Python expressions on each item.

    Args:
        item: Single item to transform (framework applies to each item)
        expr: Python expression to evaluate (use 'it' to reference the item)

    Returns:
        Expression result for the input item

    Examples:
        # Concatenate item with itself
        range 3, peval "str(it) + '.' + str(it)"  -> ["0.0", "1.1", "2.2"]

        # Multiply by 10
        range 3, peval "it * 10"  -> [0, 10, 20]

        # Get string length
        fruits, map_field name, peval "len(it)"
    """
    # Restricted namespace for eval - only safe builtins and 'it'
    safe_globals = {"__builtins__": {"str": str, "int": int, "float": float, "len": len}}
    safe_locals = {"it": item}
    try:
        value = eval(expr, safe_globals, safe_locals)
        return value
    except Exception:
        # On error, return the original item
        return item
