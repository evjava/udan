"""The factory of the per-query attributes context.

The walk builds one context per query through the ChainContextFactoryAPI the core
provides; this package's container contribution decorates that factory, so the
walk builds the context that computes: the runtime's own context, over the
runtime's own storage (see impl_attribute_runtime.AttributesContext). A host that
leaves this package out keeps the core factory, whose context stores only.
"""

from __future__ import annotations

from udan.attributes.api_attribute_runtime import AttributeRuntimeAPI
from udan.core.api_chain_context import ChainContextAPI, ChainContextFactoryAPI
from udan.core.api_exec_context import ExecContextAPI
from udan.core_tools_loading.api_tools import ToolDescriptor


class AttributesChainContextFactory(ChainContextFactoryAPI):
    """The factory that answers with the computing context.

    Args:
        attribute_runtime: The runtime the context computes through, whose storage
            the values land in
    """

    def __init__(self, attribute_runtime: AttributeRuntimeAPI) -> None:
        self._attribute_runtime = attribute_runtime

    def create(
        self,
        requested: list[ToolDescriptor] | None = None,
        ctx: ExecContextAPI | None = None,
    ) -> ChainContextAPI:
        """Build the runtime's attributes context for one query.

        Args:
            requested: Attribute descriptors the resolved query requested
            ctx: Execution context of the query

        Returns:
            The per-query attributes context
        """
        if ctx is None:
            raise ValueError("the attributes context requires a query ctx (ExecContextAPI)")
        storage = self._attribute_runtime.attribute_storage
        if storage is None:
            raise ValueError("the attributes context requires attribute storage (AttributeStorageAPI)")
        return self._attribute_runtime.create_attributes_context(
            attribute_storage=storage,
            requested_attributes=requested,
            ctx=ctx,
        )
