"""Sorter plugin: the kind service and the package's container contribution.

The sorter is an operator kind, extracted from the operators engine into this
package. The kind service (SorterApplier) carries the application and declares its
KINDS here, where the vocabulary harvests them - a kind service declares its KINDS in
a plugin package's plugins_*.py modules. The core names no sorter type.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from udan.core.api_attributes import AttributeDescriptor, AttributeMetadata
from udan.core.api_chain_context import ChainContextAPI
from udan.core.api_chain_routing import ChainRoutingAPI, ChainStepServiceAPI
from udan.core.api_constants import ARG_DESC
from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_forests import Forest, Item, Node
from udan.core.api_operators import OperatorMetadata
from udan.core_tools_loading.api_tool_kinds import ToolKindService
from udan.core_tools_loading.api_tools import ToolDescriptor, ToolKind
from udan.decompof import Plugin, provide
from udan.operator.api_operator_engine import OperatorArgs, OperatorsEngineAPI

SORTER = ToolKind(
    name="sorter",
    metadata_cls=OperatorMetadata,
    item_type_keys=("item_type",),
    query_keyword="sort",
    forms_chain=True,
)
"""Reorders items.

The kind is instantiated here, beside the service that owns it, and reaches the
framework through the declarations every kind makes: the operators engine's dispatch
applies its descriptors through the registered applicator, and the loader resolves the
`sort` query keyword back to this kind instead of comparing kinds.
"""

Orderable = int | str
"""What an ordering is keyed by: a sorter returns a value the sort can compare."""

SorterFn = Callable[[Item], Orderable]
"""The shape a sorter function has: the item in, the value to order it by out."""


def _sort_field_attribute_descriptor(attr_ctx: ChainContextAPI, field_name: str) -> AttributeDescriptor | None:
    """Return a descriptor for the attribute named by a sort field, or None if it is not an attribute.

    Composite names ("attr.field") resolve by their base attribute.

    Args:
        attr_ctx: Attributes context providing the tools registry
        field_name: Sort field name, e.g. "size" or "pfc.carbs"

    Returns:
        AttributeDescriptor for the field, or None when no attribute is registered under that name
    """
    base_name = field_name.split(".", 1)[0]
    metadata = attr_ctx.registry.get_metadata(base_name)
    if not isinstance(metadata, AttributeMetadata):
        return None
    return AttributeDescriptor.create(field_name)


def _apply_sorter(
    args_dict: dict[str, Any],
    op_fn: Callable,
    ctx: ExecContextAPI,
    attr_ctx: ChainContextAPI,
    children: Iterable[Node],
    depth: int,
    op_args: OperatorArgs,
) -> Iterable[Node]:
    """Apply a sorter operator to the nodes it is applied per.

    Args:
        args_dict: Resolved arguments for the sorter function
        op_fn: The sorter function
        ctx: Execution context for dependency injection
        attr_ctx: Attributes context, for the on-demand calculation of an
            attribute the sort field names
        children: Sibling nodes to order
        depth: Current depth in the tree (unused: a sorter orders the level it
            is applied per, the walk descends on its own)
        op_args: Pre-extracted operator metadata (unused: a sorter has no
            per-node selector of its own)

    Returns:
        The nodes in the new order, subtrees intact
    """
    fn_args = dict(args_dict)
    desc = fn_args.pop(ARG_DESC, False)
    field_name = fn_args.get("field")
    # `-field` is sugar for reversed order (e.g. `sort_by_field -calories`)
    if isinstance(field_name, str) and field_name.startswith("-"):
        field_name = field_name[1:]
        fn_args["field"] = field_name
        desc = not desc

    def resolve_value(node: Node) -> Any:
        """Get sort value for a node: op_fn result, falling back to on-demand attribute calculation."""
        value = op_fn(ctx=ctx, item=node.item, **fn_args)
        if value is None and field_name:
            # The field can name a registered attribute (e.g. `sort_by_field size` among
            # `size_human` columns): compute that exact attribute instead of guessing
            # from unrelated requested attributes
            at_d = _sort_field_attribute_descriptor(attr_ctx, field_name)
            if at_d is not None:
                return attr_ctx.get_value(at_d, node.item)
            # Otherwise the field can live inside a dict-valued requested attribute
            # (e.g. a dict-valued attribute holding the sort field as a key)
            for at_d in attr_ctx.get_requested():
                at_val = attr_ctx.get_value(at_d, node.item)
                if isinstance(at_val, dict):
                    extracted = at_val.get(field_name)
                    if extracted is not None:
                        return extracted
        return value

    keyed = [(resolve_value(node), node) for node in children]
    present = sorted(
        ((value, node) for value, node in keyed if value is not None),
        key=lambda pair: pair[0],
        reverse=desc,
    )
    # None sorts last regardless of direction
    absent = [node for value, node in keyed if value is None]
    return [node for _, node in present] + absent


class SorterApplier(ToolKindService, ChainStepServiceAPI):
    """The service that owns the sorter kind.

    Two contracts, one object: the chain routing hands it the sorter's chain groups
    (apply_chain_step), and the operators engine holds the module's applicator
    (_apply_sorter) in the dispatch it was registered into. The instance exists for
    the chain contract; the engine holds only the applicator function, so applying a
    sorter descriptor nested inside a run needs nothing from this service.

    A sorter reorders the sibling nodes it is applied per: the nodes keep their
    subtrees and their items, and only the order of the level changes. A node whose
    value is absent sorts last, whichever direction the order goes.
    """

    KINDS: tuple[ToolKind, ...] = (SORTER,)
    """The kind this service owns: the sorter."""

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
        """Apply a sorter chain group at its chain position; return the next stage.

        The group goes to the engine's own chain step: this service owns the kind, the
        engine owns the walk.

        Args:
            descriptors: Sorter descriptors of the chain group, in written order
            stage: The forest the chain groups before this one produced
            chain_context: The per-query context of the walk
            ctx: Execution context for dependency injection and query-time logging
            item_cap: Optional bound on how many items the group may produce

        Returns:
            The forest the group produced
        """
        return self._operator_engine.apply_chain_step(descriptors, stage, chain_context, ctx, item_cap=item_cap)


class SorterPlugin(Plugin):
    """The package's container contribution.

    Providing the applier contributes the kind's applicator to the engine's dispatch,
    the way the vocabulary provider contributes the kinds. The routing handler is not
    a decoration: the core builds the routing over its own services and hands it out,
    so the handler joins it in place - attach adds it, detach takes it back off.
    """

    @provide
    def sorter_applier(self, operator_engine: OperatorsEngineAPI) -> SorterApplier:
        """Create the applier and register the module's applicator into the engine's dispatch."""
        applier = SorterApplier(operator_engine=operator_engine)
        operator_engine.register_applicator(SORTER, _apply_sorter)
        return applier

    def attach(self, routing: ChainRoutingAPI, sorter_applier: SorterApplier) -> None:
        """Add the kind's handler to the chain routing, in place."""
        routing.add_handler(sorter_applier)

    def detach(self, routing: ChainRoutingAPI, sorter_applier: SorterApplier) -> None:
        """Take the kind's handler back off the chain routing."""
        routing.remove_handler(sorter_applier)


DOMAIN = "sorter"
PLUGIN = SorterPlugin
