from udan.core_tools_loading.api_annotated import annotated

DOMAIN = "test_interp_binding"


@annotated(meta={"tool_type": "inserter"})
def insert_range(min_value: int = 0, max_value: int = 10, step: int = 1) -> list[int]:
    """Insert a range of integers.

    Args:
        min_value: Starting value (default: 0)
        max_value: Ending value (exclusive) (default: 10)
        step: Step size (default: 1)

    Returns:
        List of integers from min_value to max_value (exclusive) with given step
    """
    return list(range(min_value, max_value, step))


@annotated(meta={"tool_type": "inserter"})
def insert_with_framework_params(
    ctx,  # Framework-injected parameter
    value: int,  # User parameter
) -> list[int]:
    """Test tool that has framework parameters.

    Framework parameters (ctx, item, items, nodes) should be automatically
    injected and excluded from positional binding.
    """
    return [value, value + 1, value + 2]


@annotated(meta={"tool_type": "filter"})
def filter_with_item_and_param(
    item,  # Framework-injected parameter
    threshold: int,  # User parameter
) -> bool:
    """Test filter that has both item framework parameter and user parameter.

    Positional arguments should bind to 'threshold', not 'item'.
    """
    return item > threshold
