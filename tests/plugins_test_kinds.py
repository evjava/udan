"""A plugin module that defines its own tool kind in a service.

The plugin-facing half of the kind vocabulary mirrors the core: a kind is defined by
the service that owns it, as the service's `KINDS` (the core kind services declare
their kinds the same way). The service is a
`ToolKindService` subclass and `ToolsRegistry.load_plugins` registers
its kinds before this module's tools are loaded, so its functions can declare
a `tool_type` of the module's own.
"""

from udan.core.api_operators import OperatorMetadata
from udan.core_tools_loading.api_annotated import annotated
from udan.core_tools_loading.api_tool_kinds import ToolKindService
from udan.core_tools_loading.api_tools import ToolKind


class CheckKindService(ToolKindService):
    """The service that owns this module's kind: it defines it.

    The rules it sets are the module's own declaration, so everything on the kind is
    proof that the service was harvested: nothing else in the suite declares it.
    `metadata_cls=None` keeps the loader's default rule (OperatorMetadata).
    """

    KINDS: tuple[ToolKind, ...] = (
        ToolKind(
            name="test_validator",
            metadata_cls=OperatorMetadata,
            item_type_keys=("item_type", "output_type"),
            query_keyword="check",
        ),
    )


@annotated(meta={"tool_type": "test_validator", "output_type": "str"})
def check_test_items(item: str, must: bool = True) -> list[str]:
    """Items of the module-declared 'test_validator' kind, with a declared output_type."""
    return [item.upper() if must else item]
