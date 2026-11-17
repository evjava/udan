"""Extender plugin: the kind service and the package's container contribution.

The extender is an operator kind, extracted from the operators engine into this
package. The kind service (ExtenderApplier) carries the application and declares its
KINDS here, where the vocabulary harvests them - a kind service declares its KINDS in
a plugin package's plugins_*.py modules. The core names no extender type.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from udan.core.api_chain_context import ChainContextAPI
from udan.core.api_chain_routing import ChainRoutingAPI, ChainStepServiceAPI
from udan.core.api_constants import ARG_MAX_DEPTH, ARG_ON_DEPTH, ARG_POSITION
from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_forests import Forest, Item, Node
from udan.core.api_operators import OperatorMetadata
from udan.core_tools_loading.api_tool_kinds import ToolKindService
from udan.core_tools_loading.api_tools import KindArg, ToolDescriptor, ToolKind
from udan.decompof import Plugin, provide
from udan.operator.api_operator_engine import OperatorArgs, OperatorsEngineAPI
from udan.operator.utils_operators import apply_at_position, on_depth_targets, positioned_op_args

EXTENDER = ToolKind(
    name="extender",
    metadata_cls=OperatorMetadata,
    level_change="appends",
    item_type_keys=("item_type", "output_type", "output_semantic"),
    required_item_type_keys=("output_type",),
    query_keyword="extend",
    forms_chain=True,
    kind_args=(
        KindArg(
            name=ARG_ON_DEPTH,
            arg_type="depth",
            description="Extend only the nodes at that depth (0 = top level); 'all' extends every node, "
            "'leaf' only the ones without children",
        ),
        KindArg(
            name=ARG_MAX_DEPTH,
            arg_type="integer",
            description="Recursion levels beyond the first extension (0 = extend once, the default)",
        ),
        KindArg(
            name=ARG_POSITION,
            arg_type="path",
            description="Extend only the node at that hierarchical position "
            "(1.2 = children[1].children[2]); the other nodes pass through untouched; "
            "-1 or the empty path switches it off",
        ),
    ),
)
"""Adds children to items; defined by what it creates, so `output_type` is required.

The kind is instantiated here, beside the service that owns it, and reaches the
framework through the declarations every kind makes: the operators engine's dispatch
applies its descriptors through the registered applicator, and the loader resolves the
`extend` query keyword back to this kind instead of comparing kinds.
"""

ExtenderFn = Callable[[Item], Iterable[Item]]
"""The shape an extender function has: the item in, the items to attach as children out."""


def _apply_extender(
    args_dict: dict[str, Any],
    op_fn: Callable,
    ctx: ExecContextAPI,
    attr_ctx: ChainContextAPI,
    children: Iterable[Node],
    depth: int,
    op_args: OperatorArgs,
) -> Iterable[Node]:
    """Apply an extender operator to the nodes it is applied per.

    With position set, only the node at that hierarchical position is extended. With
    an --on-depth level, only the nodes at that depth are; with the selector words,
    every node of the input tree is - "all" extends all of them, "leaf" only the ones
    without children. Nodes the argument does not target pass through untouched,
    descending while the target lies deeper; the selector words target nodes instead
    of levels, so the walk covers the whole tree. Extended items are added after the
    children the node already has, so several extenders stacked on the same nodes all
    contribute children.

    Args:
        args_dict: Resolved arguments for the extender function
        op_fn: The extender function
        ctx: Execution context for dependency injection
        attr_ctx: Attributes context
        children: Nodes to extend
        depth: Current depth in the tree (0 at the operator input)
        op_args: Pre-extracted operator metadata (on_depth, max_depth, position)

    Yields:
        Nodes with the extended items attached as children
    """
    on_depth = op_args.on_depth
    position = op_args.position

    if position is not None:

        def extend_target(node: Node) -> Node:
            return _extend_node(node, args_dict, op_fn, ctx, attr_ctx, depth, op_args)

        yield from apply_at_position(list(children), position, extend_target)
        return

    for child in children:
        if on_depth in ("all", "leaf"):
            # The walk visits every node: the child is extended when it matches, and
            # its pre-existing children are walked either way, for the matches deeper
            # in the tree
            if child.children:
                walked = list(_apply_extender(args_dict, op_fn, ctx, attr_ctx, child.children, depth + 1, op_args))
                child = child.model_copy(update={"children": walked})
            if on_depth_targets(on_depth, depth, child):
                yield _extend_node(child, args_dict, op_fn, ctx, attr_ctx, depth, op_args)
            else:
                yield child
            continue
        if isinstance(on_depth, int) and depth != on_depth:
            if depth < on_depth and child.children:
                child_nodes = list(_apply_extender(args_dict, op_fn, ctx, attr_ctx, child.children, depth + 1, op_args))
                yield child.model_copy(update={"children": child_nodes})
            else:
                yield child
            continue
        yield _extend_node(child, args_dict, op_fn, ctx, attr_ctx, depth, op_args)


def _extend_node(
    node: Node,
    args_dict: dict[str, Any],
    op_fn: Callable,
    ctx: ExecContextAPI,
    attr_ctx: ChainContextAPI,
    depth: int,
    op_args: OperatorArgs,
) -> Node:
    """Extend one node with the extender's items, keeping the children it already has.

    The recursion `max_depth` controls starts from the created items, with the position
    cleared: the walk to the target already happened.

    Args:
        node: The node to extend
        args_dict: Resolved arguments for the extender function
        op_fn: The extender function
        ctx: Execution context for dependency injection
        attr_ctx: Attributes context
        depth: Depth of the node in the tree (0 at the operator input)
        op_args: Pre-extracted operator metadata (on_depth, max_depth, position)

    Returns:
        The node with the extended items attached as children, or the node unchanged
        when the extender produced no items
    """
    items_ext = op_fn(ctx=ctx, item=node.item, **args_dict)
    if not items_ext:
        return node
    child_nodes = [Node.leaf(item) for item in items_ext]
    if depth < op_args.max_depth:
        child_nodes = list(
            _apply_extender(args_dict, op_fn, ctx, attr_ctx, child_nodes, depth + 1, positioned_op_args(op_args))
        )
    child_nodes = [*node.children, *child_nodes]
    return Node(item=node.item, children=child_nodes, origin_chain=list(node.origin_chain))


class ExtenderApplier(ToolKindService, ChainStepServiceAPI):
    """The service that owns the extender kind.

    Two contracts, one object: the chain routing hands it the extender's chain groups
    (apply_chain_step), and the operators engine holds the module's applicator
    (_apply_extender) in the dispatch it was registered into. The instance exists for
    the chain contract; the engine holds only the applicator function, so applying an
    extender descriptor nested inside a run needs nothing from this service.

    An extender adds children to the nodes it is applied per, keeping the children
    those nodes already have: the function receives the item (`item`) and returns the
    items to attach beneath it. The selectors the kind declares choose the targets -
    `--on-depth` a depth level or one of the selector words ("all", "leaf"),
    `--position` the one node at a hierarchical path - and `--max-depth` re-applies
    the extension to the items the extension created.
    """

    KINDS: tuple[ToolKind, ...] = (EXTENDER,)
    """The kind this service owns: the extender."""

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
        """Apply an extender chain group at its chain position; return the next stage.

        The group goes to the engine's own chain step: this service owns the kind, the
        engine owns the walk.

        Args:
            descriptors: Extender descriptors of the chain group, in written order
            stage: The forest the chain groups before this one produced
            chain_context: The per-query context of the walk
            ctx: Execution context for dependency injection and query-time logging
            item_cap: Optional bound on how many items the group may produce

        Returns:
            The forest the group produced
        """
        return self._operator_engine.apply_chain_step(descriptors, stage, chain_context, ctx, item_cap=item_cap)


class ExtenderPlugin(Plugin):
    """The package's container contribution.

    Providing the applier contributes the kind's applicator to the engine's dispatch,
    the way the vocabulary provider contributes the kinds. The routing handler is not
    a decoration: the core builds the routing over its own services and hands it out,
    so the handler joins it in place - attach adds it, detach takes it back off.
    """

    @provide
    def extender_applier(self, operator_engine: OperatorsEngineAPI) -> ExtenderApplier:
        """Create the applier and register the module's applicator into the engine's dispatch."""
        applier = ExtenderApplier(operator_engine=operator_engine)
        operator_engine.register_applicator(EXTENDER, _apply_extender)
        return applier

    def attach(self, routing: ChainRoutingAPI, extender_applier: ExtenderApplier) -> None:
        """Add the kind's handler to the chain routing, in place."""
        routing.add_handler(extender_applier)

    def detach(self, routing: ChainRoutingAPI, extender_applier: ExtenderApplier) -> None:
        """Take the kind's handler back off the chain routing."""
        routing.remove_handler(extender_applier)


DOMAIN = "extender"
PLUGIN = ExtenderPlugin
