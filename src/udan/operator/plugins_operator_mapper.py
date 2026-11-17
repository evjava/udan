"""Mapper plugin: the kind service and the package's container contribution.

The mapper is an operator kind, extracted from the operators engine into this
package. The kind service (MapperApplier) carries the application and declares its
KINDS here, where the vocabulary harvests them - a kind service declares its KINDS in
a plugin package's plugins_*.py modules. The core names no mapper type.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from udan.core.api_chain_context import ChainContextAPI
from udan.core.api_chain_routing import ChainRoutingAPI, ChainStepServiceAPI
from udan.core.api_constants import ARG_ON_DEPTH
from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_forests import Forest, Item, Node
from udan.core.api_operators import OperatorMetadata
from udan.core_tools_loading.api_tool_kinds import ToolKindService
from udan.core_tools_loading.api_tools import KindArg, ToolDescriptor, ToolKind
from udan.decompof import Plugin, provide
from udan.operator.api_operator_engine import OperatorArgs, OperatorsEngineAPI
from udan.operator.utils_operators import on_depth_targets

MAPPER = ToolKind(
    name="mapper",
    metadata_cls=OperatorMetadata,
    item_type_keys=("item_type", "output_type", "output_semantic"),
    rewrites_items=True,
    forms_chain=True,
    kind_args=(
        KindArg(
            name=ARG_ON_DEPTH,
            arg_type="depth",
            description="Map only the items at that depth (0 = top level); 'all' maps every item, "
            "'leaf' only the ones without children",
        ),
    ),
)
"""Transforms each item into another. No query keyword of its own today.

The kind is instantiated here, beside the service that owns it, and reaches the
framework through the declarations every kind makes: the operators engine's dispatch
applies its descriptors through the registered applicator, and the type descriptor
reads `rewrites_items` the way it reads every kind's declarations.
"""

MapperFn = Callable[[Item], Item]
"""The shape a mapper function has: the item in, its replacement out."""


def _apply_mapper(
    args_dict: dict[str, Any],
    op_fn: Callable,
    ctx: ExecContextAPI,
    attr_ctx: ChainContextAPI,
    children: Iterable[Node],
    depth: int,
    op_args: OperatorArgs,
) -> Iterable[Node]:
    """Apply a mapper operator to the nodes it is applied per.

    The mapper function is applied to items in the nested tree structure. If on_depth
    is specified, only applies where it targets: a depth level, or one of the selector
    words - "all" (every item, the same as unspecified) and "leaf" (items without
    children). Otherwise, applies recursively to all items.

    Args:
        args_dict: Resolved arguments for the mapper function
        op_fn: The mapper function
        ctx: Execution context for dependency injection
        attr_ctx: Attributes context (unused: a mapper reads no attributes)
        children: Nodes whose items to map
        depth: Current depth in the tree (0 at the operator input)
        op_args: Pre-extracted operator metadata (on_depth)

    Yields:
        The nodes with their items mapped
    """
    on_depth = op_args.on_depth

    def map_recursive(nodes: list[Node], current_depth: int = 0) -> list[Node]:
        """Recursively apply mapper to items in the tree."""
        results = []
        for node in nodes:
            # Apply mapper to this node's item when the selector targets it
            if on_depth_targets(on_depth, current_depth, node):
                mapped_item = op_fn(ctx=ctx, item=node.item, **args_dict)
            else:
                mapped_item = node.item

            # Recursively map children if they exist
            if node.children:
                mapped_children = map_recursive(node.children, current_depth + 1)
                results.append(Node(item=mapped_item, children=mapped_children))
            else:
                results.append(Node(item=mapped_item))
        return results

    yield from map_recursive(list(children), depth)


class MapperApplier(ToolKindService, ChainStepServiceAPI):
    """The service that owns the mapper kind.

    Two contracts, one object: the chain routing hands it the mapper's chain groups
    (apply_chain_step), and the operators engine holds the module's applicator
    (_apply_mapper) in the dispatch it was registered into. The instance exists for
    the chain contract; the engine holds only the applicator function, so applying a
    mapper descriptor nested inside a run needs nothing from this service.

    A mapper rewrites each item in place, keeping the tree shape: the node keeps its
    children, its item becomes what the mapper returned. With `--on-depth`, only the
    nodes the selector targets are mapped - a depth level, or one of the selector
    words ("all" every node, the same as unspecified, "leaf" the ones without
    children); the other nodes keep their items.
    """

    KINDS: tuple[ToolKind, ...] = (MAPPER,)
    """The kind this service owns: the mapper."""

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
        """Apply a mapper chain group at its chain position; return the next stage.

        The group goes to the engine's own chain step: this service owns the kind, the
        engine owns the walk.

        Args:
            descriptors: Mapper descriptors of the chain group, in written order
            stage: The forest the chain groups before this one produced
            chain_context: The per-query context of the walk
            ctx: Execution context for dependency injection and query-time logging
            item_cap: Optional bound on how many items the group may produce

        Returns:
            The forest the group produced
        """
        return self._operator_engine.apply_chain_step(descriptors, stage, chain_context, ctx, item_cap=item_cap)


class MapperPlugin(Plugin):
    """The package's container contribution.

    Providing the applier contributes the kind's applicator to the engine's dispatch,
    the way the vocabulary provider contributes the kinds. The routing handler is not
    a decoration: the core builds the routing over its own services and hands it out,
    so the handler joins it in place - attach adds it, detach takes it back off.
    """

    @provide
    def mapper_applier(self, operator_engine: OperatorsEngineAPI) -> MapperApplier:
        """Create the applier and register the module's applicator into the engine's dispatch."""
        applier = MapperApplier(operator_engine=operator_engine)
        operator_engine.register_applicator(MAPPER, _apply_mapper)
        return applier

    def attach(self, routing: ChainRoutingAPI, mapper_applier: MapperApplier) -> None:
        """Add the kind's handler to the chain routing, in place."""
        routing.add_handler(mapper_applier)

    def detach(self, routing: ChainRoutingAPI, mapper_applier: MapperApplier) -> None:
        """Take the kind's handler back off the chain routing."""
        routing.remove_handler(mapper_applier)


DOMAIN = "mapper"
PLUGIN = MapperPlugin
