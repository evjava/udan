"""Public API for chain routing: which service applies which kind inside a query chain.

A resolved query is a chain of tools in written order - the chain-forming kinds
and attributes - over data items. Which service applies which kind is ownership the kind
services already declare (their `KINDS`, see ToolKindService); the routing is
that declaration made dispatchable: kind name -> the service that applies the kind at
its chain position (impl_chain_routing builds the table and checks its invariant).

The table is extensible: a plugin package whose kinds form the chain contributes its
handler by decorating ChainRoutingAPI (its own container provider wraps the routing
the core built) or, at attach, by adding it in place (add_handler), and the
composition root validates the completed table, so a wiring gap fails the build
instead of the query.
"""

from __future__ import annotations

from collections.abc import Mapping

from udan.core.api_chain_context import ChainContextAPI
from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_forests import Forest
from udan.core_tools_loading.api_tool_kinds import ToolKindService
from udan.core_tools_loading.api_tools import ToolDescriptor


class ChainStepServiceAPI:
    """A service that can apply chain-forming tools at their chain position.

    Implementing it is the only new contract a chain-forming kind asks of its service
    (see ToolKind.forms_chain): the orchestrator's walk groups the resolved
    chain by handler and hands each group over, so a service owns the semantics of its
    own kinds - a transforming service produces the next stage, a computing one stores
    values and passes the stage through.
    """

    def apply_chain_step(
        self,
        descriptors: list[ToolDescriptor],
        stage: Forest,
        chain_context: ChainContextAPI,
        ctx: ExecContextAPI,
        item_cap: int | None = None,
    ) -> Forest:
        """Apply the descriptors over the stage in written order; return the next stage.

        Args:
            descriptors: Chain descriptors of this service's kinds, in written order
            stage: The forest the chain groups before this one produced
            chain_context: The per-query context of the walk
            ctx: Execution context for dependency injection and query-time logging
            item_cap: Optional bound on how many items the group may produce;
                meaningful only to a streaming service

        Returns:
            The forest the group produced
        """
        raise NotImplementedError


class ChainRoutingAPI(Mapping):
    """Kind name -> the service that applies that kind inside a chain.

    Reading it is the mapping protocol over the handled kind names: `"attribute" in
    routing`, `routing["attribute"]`, iteration over the names.
    """

    def with_handler(self, service: ToolKindService) -> ChainRoutingAPI:
        """The routing with one more handler: the extension a plugin's decoration performs.

        Args:
            service: The handler for the kinds its `KINDS` declare

        Returns:
            The routing with the service's kinds added to its table

        Raises:
            ValueError: If the service cannot apply a chain step, or claims a kind
                another handler already claims
        """
        raise NotImplementedError

    def add_handler(self, service: ToolKindService) -> None:
        """Add the handler for the service's kinds, in place: the attach a plugin's verb performs.

        A decoration (`with_handler`) wraps the routing the container builds, so it
        runs at container build; a handler that joins through a plugin's attach arrives
        after the routing was already handed out, so it goes into the table every
        holder shares.

        Args:
            service: The handler for the kinds its `KINDS` declare

        Raises:
            ValueError: If the service cannot apply a chain step, or claims a kind
                another handler already claims
        """
        raise NotImplementedError

    def remove_handler(self, service: ToolKindService) -> None:
        """Take a handler back off the table, in place: the detach to add_handler's attach.

        Args:
            service: The handler whose kinds come off the table
        """
        raise NotImplementedError

    def with_override_handler(self, service: ChainStepServiceAPI) -> ChainRoutingAPI:
        """The routing with the handler that applies an output-overriding chain whole.

        Args:
            service: The service the routing hands an overriding forest to

        Returns:
            The routing with that handler set
        """
        raise NotImplementedError

    def apply_override(
        self,
        forest: Forest,
        chain_context: ChainContextAPI,
        ctx: ExecContextAPI,
        item_cap: int | None = None,
    ) -> None:
        """Apply a chain that overrides the output, whole: nothing else may run.

        The handler that owns the override is handed the resolved forest as it
        stands, and answers by raising OverrideForestException with the forest the
        output should be - the caller never sees a return.

        Args:
            forest: The resolved forest, unapplied
            chain_context: The per-query context of the walk
            ctx: Execution context for dependency injection and query-time logging
            item_cap: Optional bound on how many items the override may produce

        Raises:
            OverrideForestException: Always - the override is the answer
            ValueError: If no handler owns the override (its package is not enabled)
        """
        raise NotImplementedError

    def validate(self) -> None:
        """Fail when a chain-forming kind of the vocabulary has no handler.

        The completeness half of the invariant. It cannot run at construction - a
        routing may be extended by plugin decorations still pending - so it runs at
        the composition root, once the routing is complete: a wiring gap fails the
        build instead of the query.

        Raises:
            ValueError: If a chain-forming kind of the vocabulary is unhandled
        """
        raise NotImplementedError

    def handler_for(self, descriptor: ToolDescriptor) -> ChainStepServiceAPI | None:
        """The service that applies this descriptor's kind, resolved through the registry.

        Args:
            descriptor: A chain descriptor from the resolved forest

        Returns:
            The handler of the descriptor's kind, or None when the kind does not
            form the chain (the node is data from the walk's point of view)

        Raises:
            ValueError: If the kind forms the chain but no service handles it
        """
        raise NotImplementedError
