"""Public API for the per-query chain context.

The chain walk hands every chain-step service one context per query: the registry
the handlers resolve through, the walk depth, and the store of the values a chain
sets for items as it runs (an operator's origin chain, the values tools
mark as precalculated). Computing a value the store does not hold is the value
domain's own work - the context that computes arrives through the same seam, from
the package that owns the computation: its container contribution decorates the
ChainContextFactoryAPI the core builds (see impl_ioc), and the walk builds each
query's context through the decorated factory.

Read blind of domains, the interface is the walk's own vocabulary: descriptors,
items, values. A package that owns a value domain extends it with the typed
surface its tools use, and hands that in through the factory.
"""

from __future__ import annotations

from typing import Any

from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_forests import Forest, Item
from udan.core_tools_loading.api_tools import ToolDescriptor
from udan.core_tools_loading.api_tools_registry import ToolsRegistryAPI


class ChainContextAPI:
    """The per-query context the chain walk hands the chain-step services.

    Attributes:
        registry: Tools registry the handlers resolve through
        depth: Current depth in the tree during chain application
        ctx: Execution context of the query (query-time logging, symbols)
    """

    registry: ToolsRegistryAPI
    depth: int
    ctx: ExecContextAPI

    def set_value(self, desc: ToolDescriptor, item: Item, value: Any) -> None:
        """Store a value for an item under a descriptor.

        Args:
            desc: The descriptor the value belongs to
            item: Item to store the value for
            value: The value to store
        """
        raise NotImplementedError

    def get_requested(self) -> list[ToolDescriptor]:
        """The descriptors the query requested, in the order they were discovered.

        Returns:
            List of descriptors requested for calculation
        """
        raise NotImplementedError

    def get_stored_value(self, desc: ToolDescriptor, item: Item) -> Any | None:
        """Get a stored value without triggering computation.

        This reads the store only: None means "not stored", which distinguishes a
        value computed as None from one nobody stored. Used for checking cache
        keys, resolving dependencies between descriptors, and reading
        pre-calculated values.

        Args:
            desc: Descriptor to look up
            item: Item to look up

        Returns:
            The stored value, or None when nothing stored one
        """
        raise NotImplementedError

    def get_value(self, desc: ToolDescriptor, item: Item) -> Any:
        """Get a value for an item, computing it on demand if needed.

        Unlike get_stored_value, this triggers computation when the value is not
        yet stored - which only the context a value-domain package hands in can do.

        Args:
            desc: Descriptor to get the value of
            item: Item to get the value for

        Returns:
            The value
        """
        raise NotImplementedError

    def apply_values(self, forest: Forest, requested: list[ToolDescriptor], ctx: ExecContextAPI) -> None:
        """Apply the values of the descriptors the walk did not apply at a chain position.

        The whole-forest pass after the walk: chain application covers the
        descriptors it saw at top-level positions, the rest - nested deeper and
        the ones discovered during application - is applied over the final forest.

        Args:
            forest: The final forest the values belong to
            requested: Descriptors the walk did not apply
            ctx: Execution context for query-time logging
        """
        raise NotImplementedError


class ChainContextFactoryAPI:
    """The factory of the per-query chain context.

    The core builds one factory that answers with a store-only context; a package
    that owns a value domain decorates it, so the walk builds its contexts through
    the factory that computes. A host that leaves the package out keeps the core
    factory: storing works, computing fails with the advice that says what is
    missing. The factory is built over the container's registry, so the contexts
    it answers carry the registry the handlers resolve through.
    """

    def create(
        self,
        requested: list[ToolDescriptor] | None = None,
        ctx: ExecContextAPI | None = None,
    ) -> ChainContextAPI:
        """Build the context of one query.

        Args:
            requested: Descriptors the resolved query requested
            ctx: Execution context of the query

        Returns:
            The per-query chain context
        """
        raise NotImplementedError
