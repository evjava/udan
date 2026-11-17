"""Filter plugin: the kind service and the package's container contribution.

The filter is an operator kind, extracted from the operators engine into this
package. The kind service (FilterApplier) carries the application and declares its
KINDS here, where the vocabulary harvests them - a kind service declares its KINDS in
a plugin package's plugins_*.py modules. The core names no filter type.
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
from udan.operator.utils_operators import on_depth_targets, resolve_per_item_attribute_dependencies

FILTER = ToolKind(
    name="filter",
    metadata_cls=OperatorMetadata,
    item_type_keys=("item_type",),
    requires_item_parameter=True,
    query_keyword="filter",
    forms_chain=True,
    kind_args=(
        KindArg(
            name=ARG_ON_DEPTH,
            arg_type="depth",
            description="Filter only the items at that depth (0 = top level); 'all' filters every item, "
            "'leaf' only the ones without children",
        ),
    ),
)
"""Selects a subset of the items it is applied per.

The kind is instantiated here, beside the service that owns it, and reaches the
framework through the declarations every kind makes: the operators engine's dispatch
applies its descriptors through the registered applicator, and the loader resolves the
`filter` query keyword back to this kind instead of comparing kinds.
"""

FilterFn = Callable[[Item], bool]
"""The shape a filter function has: the item in, whether it passes out."""


def _apply_filter(
    args_dict: dict[str, Any],
    op_fn: Callable,
    ctx: ExecContextAPI,
    attr_ctx: ChainContextAPI,
    children: Iterable[Node],
    depth: int,
    op_args: OperatorArgs,
) -> Iterable[Node]:
    """Apply a filter operator to the nodes it is applied per.

    Args:
        args_dict: Resolved arguments for the filter function
        op_fn: The filter function
        ctx: Execution context for dependency injection
        attr_ctx: Attributes context, for the per-item @attribute dependencies
        children: Nodes to filter
        depth: Current depth in the tree (0 at the operator input)
        op_args: Pre-extracted operator metadata (on_depth, per_item_attrs)

    Yields:
        The nodes the filter accepted
    """
    on_depth = op_args.on_depth

    if on_depth is not None:
        # Apply the filter where the selector targets: a depth level, or one of the
        # selector words - "all" (every node) and "leaf" (nodes without children)
        def filter_at_depth(nodes: list[Node], current_depth: int) -> list[Node]:
            """Recursively filter the nodes the selector targets."""
            results = []
            for node in nodes:
                if on_depth_targets(on_depth, current_depth, node):
                    # Resolve @attribute dependencies for this item
                    item_args = resolve_per_item_attribute_dependencies(
                        op_fn, args_dict, attr_ctx, node.item, op_args.per_item_attrs
                    )
                    # A node the filter rejects loses its subtree with it
                    if not op_fn(ctx=ctx, item=node.item, **item_args):
                        continue
                # Off target, or kept - the node stays and its descendants are filtered too
                if node.children:
                    filtered_children = filter_at_depth(node.children, current_depth + 1)
                    results.append(Node(item=node.item, children=filtered_children))
                else:
                    results.append(node)
            return results

        yield from filter_at_depth(list(children), 0)
    else:
        # Original behavior: apply filter to all items
        for child in children:
            # Resolve @attribute dependencies for this item
            item_args = resolve_per_item_attribute_dependencies(
                op_fn, args_dict, attr_ctx, child.item, op_args.per_item_attrs
            )
            if op_fn(ctx=ctx, item=child.item, **item_args):
                yield child


class FilterApplier(ToolKindService, ChainStepServiceAPI):
    """The service that owns the filter kind.

    Two contracts, one object: the chain routing hands it the filter's chain groups
    (apply_chain_step), and the operators engine holds the module's applicator
    (_apply_filter) in the dispatch it was registered into. The instance exists for
    the chain contract; the engine holds only the applicator function, so applying a
    filter descriptor nested inside a run needs nothing from this service.

    A filter keeps the nodes its function accepts: a node the filter rejects loses
    its subtree with it. With `--on-depth`, only the nodes the selector targets are
    tested - a depth level, or one of the selector words ("all" every node, "leaf"
    the ones without children); the other nodes stay and their descendants are
    filtered too.
    """

    KINDS: tuple[ToolKind, ...] = (FILTER,)
    """The kind this service owns: the filter."""

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
        """Apply a filter chain group at its chain position; return the next stage.

        The group goes to the engine's own chain step: this service owns the kind, the
        engine owns the walk.

        Args:
            descriptors: Filter descriptors of the chain group, in written order
            stage: The forest the chain groups before this one produced
            chain_context: The per-query context of the walk
            ctx: Execution context for dependency injection and query-time logging
            item_cap: Optional bound on how many items the group may produce

        Returns:
            The forest the group produced
        """
        return self._operator_engine.apply_chain_step(descriptors, stage, chain_context, ctx, item_cap=item_cap)


class FilterPlugin(Plugin):
    """The package's container contribution.

    Providing the applier contributes the kind's applicator to the engine's dispatch,
    the way the vocabulary provider contributes the kinds. The routing handler is not
    a decoration: the core builds the routing over its own services and hands it out,
    so the handler joins it in place - attach adds it, detach takes it back off.
    """

    @provide
    def filter_applier(self, operator_engine: OperatorsEngineAPI) -> FilterApplier:
        """Create the applier and register the module's applicator into the engine's dispatch."""
        applier = FilterApplier(operator_engine=operator_engine)
        operator_engine.register_applicator(FILTER, _apply_filter)
        return applier

    def attach(self, routing: ChainRoutingAPI, filter_applier: FilterApplier) -> None:
        """Add the kind's handler to the chain routing, in place."""
        routing.add_handler(filter_applier)

    def detach(self, routing: ChainRoutingAPI, filter_applier: FilterApplier) -> None:
        """Take the kind's handler back off the chain routing."""
        routing.remove_handler(filter_applier)


DOMAIN = "filter"
PLUGIN = FilterPlugin
