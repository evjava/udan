from typing import Annotated

from udan.core.api_attributes import AttributeDescriptor
from udan.core_tools_loading.api_annotated import annotated

DOMAIN = "test_injected_args"


@annotated(meta={"tool_type": "attribute"})
def demo_attr_with_at_d(item: str, at_d: Annotated[AttributeDescriptor, "internal"]) -> str:
    return f"{item} from {at_d.name}"


@annotated(meta={"tool_type": "attribute"})
def demo_attr_with_both(
    item: str,
    ctx: Annotated[object, "internal"],
    at_d: Annotated[AttributeDescriptor, "internal"],
) -> str:
    return f"{item}"


@annotated(meta={"tool_type": "filter"})
def demo_filter_with_at_d(
    item: str,
    at_d: Annotated[AttributeDescriptor, "internal"],
    pattern: str,
) -> bool:
    return pattern in item


@annotated(meta={"tool_type": "filter"})
def demo_filter_withctx(item: str, ctx: Annotated[object, "internal"]) -> bool:
    return True
