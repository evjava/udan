"""Inserter plugin: the kind service and the package's container contribution.

The inserter is an operator kind, extracted from the operators engine into this
package. The kind service (InserterApplier) carries the application and declares its
KINDS here, where the vocabulary harvests them - a kind service declares its KINDS in
a plugin package's plugins_*.py modules. The core names no inserter type.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from udan.core.api_chain_context import ChainContextAPI
from udan.core.api_chain_routing import ChainRoutingAPI, ChainStepServiceAPI
from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_forests import Forest, Node
from udan.core.api_operators import OperatorMetadata
from udan.core_tools_loading.api_tool_kinds import ToolKindService
from udan.core_tools_loading.api_tools import ToolDescriptor, ToolKind
from udan.decompof import Plugin, provide
from udan.operator.api_operator_engine import OperatorArgs, OperatorsEngineAPI

INSERTER = ToolKind(
    name="inserter",
    metadata_cls=OperatorMetadata,
    level_change="replaces",
    item_type_keys=("output_type", "output_semantic"),
    derives_item_type=False,
    query_keyword="insert",
    forms_chain=True,
)
"""Creates items: consumes none, so it can only open a chain.

The kind is instantiated here, beside the service that owns it, and reaches the
framework through the declarations every kind makes: the operators engine's dispatch
applies its descriptors through the registered applicator, and the loader resolves the
`insert` query keyword back to this kind instead of comparing kinds.
"""


def _apply_inserter(
    args_dict: dict[str, Any],
    op_fn: Callable,
    ctx: ExecContextAPI,
    attr_ctx: ChainContextAPI,
    children: Iterable[Node],
    depth: int,
    op_args: OperatorArgs,
) -> Iterable[Node]:
    """Apply an inserter operator to the nodes it is applied per; the engine's dispatch calls it.

    Args:
        args_dict: Resolved arguments for the inserter function
        op_fn: The inserter function
        ctx: Execution context for dependency injection
        attr_ctx: Attributes context (unused: an inserter reads no attributes)
        children: The nodes the inserter passes through (it consumes none)
        depth: Current depth in the tree (unused: an inserter opens the chain)
        op_args: Pre-extracted operator metadata (is_nested selects the form)

    Yields:
        The passed-through nodes, then the items the inserter created
    """
    yield from children

    items_to_insert = op_fn(ctx=ctx, **args_dict)

    if op_args.is_nested:
        # Nested insertion: Iterable[tuple[int, Item]] -> Forest -> the top-level nodes
        forest = Forest.from_pairs(items_to_insert)
        if not forest.depths:
            return
        root = forest.convert_to_node()
        yield from root.children
    else:
        # Flat insertion: Iterable[Item] -> leaves
        for item in items_to_insert:
            yield Node.leaf(item)


class InserterApplier(ToolKindService, ChainStepServiceAPI):
    """The service that owns the inserter kind.

    Two contracts, one object: the chain routing hands it the inserter's chain groups
    (apply_chain_step), and the operators engine holds the module's applicator
    (_apply_inserter) in the dispatch it was registered into. The instance exists for
    the chain contract; the engine holds only the applicator function, so applying an
    inserter descriptor nested inside a run needs nothing from this service.

    An inserter creates items and consumes none, so it can only open a chain: the
    items it returns become the stage the rest of the chain runs over. The flat form
    returns the items, which become leaves; the nested form (`is_nested: True`)
    returns depth-item pairs, which the framework converts into the tree the chain
    starts from.
    """

    KINDS: tuple[ToolKind, ...] = (INSERTER,)
    """The kind this service owns: the inserter."""

    def __init__(self, operator_engine: OperatorsEngineAPI) -> None:
        """Create the applier over the engine whose walk applies its chain groups.

        Args:
            operator_engine: The operators engine, owning the walk this service
                delegates its chain groups to
        """
        self._operator_engine = operator_engine

    def apply_chain_step(
        self,
        descriptors: list[ToolDescriptor],
        stage: Forest,
        chain_context: ChainContextAPI,
        ctx: ExecContextAPI,
        item_cap: int | None = None,
    ) -> Forest:
        """Apply an inserter chain group at its chain position; return the next stage.

        The group goes to the engine's own chain step: this service owns the kind, the
        engine owns the walk.

        Args:
            descriptors: Inserter descriptors of the chain group, in written order
            stage: The forest the chain groups before this one produced
            chain_context: The per-query context of the walk
            ctx: Execution context for dependency injection and query-time logging
            item_cap: Optional bound on how many items the group may produce

        Returns:
            The forest the group produced
        """
        return self._operator_engine.apply_chain_step(descriptors, stage, chain_context, ctx, item_cap=item_cap)


class InserterPlugin(Plugin):
    """The package's container contribution.

    Providing the applier contributes the kind's applicator to the engine's dispatch,
    the way the vocabulary provider contributes the kinds. The routing handler is not
    a decoration: the core builds the routing over its own services and hands it out,
    so the handler joins it in place - attach adds it, detach takes it back off.
    """

    @provide
    def inserter_applier(self, operator_engine: OperatorsEngineAPI) -> InserterApplier:
        """Create the applier and register the module's applicator into the engine's dispatch."""
        applier = InserterApplier(operator_engine=operator_engine)
        operator_engine.register_applicator(INSERTER, _apply_inserter)
        return applier

    def attach(self, routing: ChainRoutingAPI, inserter_applier: InserterApplier) -> None:
        """Add the kind's handler to the chain routing, in place."""
        routing.add_handler(inserter_applier)

    def detach(self, routing: ChainRoutingAPI, inserter_applier: InserterApplier) -> None:
        """Take the kind's handler back off the chain routing."""
        routing.remove_handler(inserter_applier)


DOMAIN = "inserter"
PLUGIN = InserterPlugin
