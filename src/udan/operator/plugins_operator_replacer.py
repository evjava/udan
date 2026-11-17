"""Replacer plugin: the kind service and the package's container contribution.

The replacer is an operator kind, extracted from the operators engine into this
package. The kind service (ReplacerApplier) carries the application and declares its
KINDS here, where the vocabulary harvests them - a kind service declares its KINDS in
a plugin package's plugins_*.py modules. The core names no replacer type.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from inspect import signature
from typing import Any

from udan.core.api_chain_context import ChainContextAPI
from udan.core.api_chain_routing import ChainRoutingAPI, ChainStepServiceAPI
from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_forests import Forest, Item, Node
from udan.core.api_operators import OperatorMetadata
from udan.core_tools_loading.api_tool_kinds import ToolKindService
from udan.core_tools_loading.api_tools import ToolDescriptor, ToolKind
from udan.decompof import Plugin, provide
from udan.operator.api_operator_engine import OperatorArgs, OperatorsEngineAPI

REPLACER = ToolKind(
    name="replacer",
    metadata_cls=OperatorMetadata,
    item_type_keys=("item_type", "output_type", "output_semantic"),
    query_keyword="replace",
    forms_chain=True,
    injected_args=("items", "nodes"),
    rewrites_items=True,
    declares_output=True,
)
"""Replaces items with new ones, per level or nested.

The kind is instantiated here, beside the service that owns it, and reaches the
framework through the declarations every kind makes: the operators engine's dispatch
applies its descriptors through the registered applicator, the descriptor factory reads
`injected_args` instead of comparing kinds, and the type descriptor and the render
picker read `rewrites_items` and `declares_output`.
"""

ReplacerFn = Callable[[list[Item]], list[Item]]
"""The shape a flat replacer function has: the level's items in, the new items out."""


def _apply_replacer(
    args_dict: dict[str, Any],
    op_fn: Callable,
    ctx: ExecContextAPI,
    attr_ctx: ChainContextAPI,
    children: Iterable[Node],
    depth: int,
    op_args: OperatorArgs,
) -> Iterable[Node]:
    """Apply a replacer operator to the nodes it is applied per.

    Args:
        args_dict: Resolved arguments for the replacer function
        op_fn: The replacer function
        ctx: Execution context for dependency injection
        attr_ctx: Attributes context (unused: a replacer reads no attributes)
        children: Nodes to replace
        depth: Current depth in the tree (unused: the flat form restarts per level)
        op_args: Pre-extracted operator metadata (is_nested selects the form)

    Yields:
        The nodes with the replacer applied
    """
    if op_args.is_nested:
        sig = signature(op_fn)
        if "nodes" in sig.parameters:
            args_dict["nodes"] = list(children)
        op_res = op_fn(ctx=ctx, **args_dict)
        # Nested: result is Iterable[tuple[int, Item]] -> Forest -> nodes
        forest = Forest.from_pairs(op_res)
        if not forest.depths:
            return
        yield from forest.convert_to_node().children
    else:
        # Flat: apply op_fn at each depth level, preserving tree structure
        def replace_recursive(nodes: list[Node]) -> list[Node]:
            batch_args = dict(args_dict)
            batch_args["items"] = [node.item for node in nodes]
            new_items = list(op_fn(ctx=ctx, **batch_args))

            results = []
            for i, new_item in enumerate(new_items):
                node = nodes[i] if i < len(nodes) else None
                if node and node.children:
                    results.append(Node(item=new_item, children=replace_recursive(node.children)))
                else:
                    results.append(Node(item=new_item))
            return results

        yield from replace_recursive(list(children))


class ReplacerApplier(ToolKindService, ChainStepServiceAPI):
    """The service that owns the replacer kind.

    Two contracts, one object: the chain routing hands it the replacer's chain groups
    (apply_chain_step), and the operators engine holds the module's applicator
    (_apply_replacer) in the dispatch it was registered into. The instance exists for
    the chain contract; the engine holds only the applicator function, so applying a
    replacer descriptor nested inside a run needs nothing from this service.

    A replacer replaces the items it is applied per with the ones its function
    returns. The flat form works level by level - the function receives the level's
    items (`items`) and returns the new items, and the tree keeps its shape. The
    nested form (`is_nested: True`) runs once over the whole subtree - the function
    receives the nodes (`nodes`) and returns depth-item pairs, which the framework
    converts back into nodes.
    """

    KINDS: tuple[ToolKind, ...] = (REPLACER,)
    """The kind this service owns: the replacer."""

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
        """Apply a replacer chain group at its chain position; return the next stage.

        The group goes to the engine's own chain step: this service owns the kind, the
        engine owns the walk.

        Args:
            descriptors: Replacer descriptors of the chain group, in written order
            stage: The forest the chain groups before this one produced
            chain_context: The per-query context of the walk
            ctx: Execution context for dependency injection and query-time logging
            item_cap: Optional bound on how many items the group may produce

        Returns:
            The forest the group produced
        """
        return self._operator_engine.apply_chain_step(descriptors, stage, chain_context, ctx, item_cap=item_cap)


class ReplacerPlugin(Plugin):
    """The package's container contribution.

    Providing the applier contributes the kind's applicator to the engine's dispatch,
    the way the vocabulary provider contributes the kinds. The routing handler is not
    a decoration: the core builds the routing over its own services and hands it out,
    so the handler joins it in place - attach adds it, detach takes it back off.
    """

    @provide
    def replacer_applier(self, operator_engine: OperatorsEngineAPI) -> ReplacerApplier:
        """Create the applier and register the module's applicator into the engine's dispatch."""
        applier = ReplacerApplier(operator_engine=operator_engine)
        operator_engine.register_applicator(REPLACER, _apply_replacer)
        return applier

    def attach(self, routing: ChainRoutingAPI, replacer_applier: ReplacerApplier) -> None:
        """Add the kind's handler to the chain routing, in place."""
        routing.add_handler(replacer_applier)

    def detach(self, routing: ChainRoutingAPI, replacer_applier: ReplacerApplier) -> None:
        """Take the kind's handler back off the chain routing."""
        routing.remove_handler(replacer_applier)


DOMAIN = "replacer"
PLUGIN = ReplacerPlugin
