"""Test plugin for tracing functionality.

This plugin provides simple functions with assignments for testing
the trace_func_query with {body} option.
"""

from udan.core_tools_loading.api_annotated import annotated

DOMAIN = "test_tracing"


def simple_calculate() -> int:
    """Simple function with assignments for tracing."""
    a = 1 + 2
    b = a * 3
    _c = "hello " + "world"  # Unused but kept for testing assignment tracing
    d = [1, 2, 3]
    e = len(d)
    return b + e


@annotated(
    meta={
        "tool_type": "inserter",
        "is_nested": False,
        "output_type": "int",
    }
)
def trace_test_calculate() -> list[int]:
    """Test inserter that calls simple_calculate."""
    result = simple_calculate()
    return [result]
