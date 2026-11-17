"""Grouper plugin: the kind service and the package's container contribution.

The grouper is an operator kind, extracted from the operators engine into this
package. The kind service (GrouperApplier) carries the application and declares its
KINDS here, where the vocabulary harvests them - a kind service declares its KINDS in
a plugin package's plugins_*.py modules. The core names no grouper type.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from typing import Any

from udan.core.api_attributes import AttributeDescriptor
from udan.core.api_chain_context import ChainContextAPI
from udan.core.api_chain_routing import ChainRoutingAPI, ChainStepServiceAPI
from udan.core.api_constants import ARG_POSITION
from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_forests import Forest, Item, Node
from udan.core.api_operators import OperatorMetadata
from udan.core_tools_loading.api_tool_kinds import ToolKindService
from udan.core_tools_loading.api_tools import KindArg, ToolDescriptor, ToolKind
from udan.core_tools_loading.api_types import Group
from udan.decompof import Plugin, provide
from udan.operator.api_operator_engine import OperatorArgs, OperatorsEngineAPI
from udan.operator.utils_operators import (
    apply_at_position,
    positioned_op_args,
    resolve_per_item_attribute_dependencies,
)

GROUPER = ToolKind(
    name="grouper",
    metadata_cls=OperatorMetadata,
    level_change="wraps",
    item_type_keys=("item_type",),
    requires_item_parameter=True,
    query_keyword="group",
    forms_chain=True,
    kind_args=(
        KindArg(
            name=ARG_POSITION,
            arg_type="path",
            description="Group only the children of the node at that hierarchical position "
            "(1.2 = children[1].children[2]); the other nodes pass through untouched; "
            "-1 or the empty path switches it off",
        ),
    ),
)
"""Groups items by a value it reads per item.

The kind is instantiated here, beside the service that owns it, and reaches the
framework through the declarations every kind makes: the operators engine's dispatch
applies its descriptors through the registered applicator, and the loader resolves the
`group` query keyword back to this kind instead of comparing kinds.
"""

GrouperFn = Callable[[Item], "Group | Any"]
"""The shape a grouper function has: the item in, the group key (or a Group) out."""


def _apply_grouper(
    args_dict: dict[str, Any],
    op_fn: Callable,
    ctx: ExecContextAPI,
    attr_ctx: ChainContextAPI,
    children: Iterable[Node],
    depth: int,
    op_args: OperatorArgs,
) -> Iterable[Node]:
    """Apply a grouper operator to the nodes it is applied per.

    Args:
        args_dict: Resolved arguments for the grouper function
        op_fn: The grouper function
        ctx: Execution context for dependency injection
        attr_ctx: Attributes context, for the per-item @attribute dependencies
        children: Sibling nodes to group
        depth: Current depth in the tree (0 at the operator input)
        op_args: Pre-extracted operator metadata (position, per_item_attrs)

    Yields:
        The Group nodes, one per key, their children the grouped nodes
    """
    # With position set, only the children of the node the path names are re-grouped;
    # the other nodes pass through untouched
    position = op_args.position
    if position is not None:

        def regroup_target(node: Node) -> Node:
            grouped = _apply_grouper(args_dict, op_fn, ctx, attr_ctx, node.children, depth, positioned_op_args(op_args))
            return node.model_copy(update={"children": list(grouped)})

        yield from apply_at_position(list(children), position, regroup_target)
        return

    # Check if we have any Group items in children (for nested grouping)
    has_groups = any(isinstance(child.item, Group) for child in children)

    groups_map = defaultdict(list)
    for child in children:
        # If this is a Group item and we're doing nested grouping
        if isinstance(child.item, Group) and has_groups:
            # Recursively apply grouping to the Group's children
            # The outer Group keeps its original key, but children get re-grouped
            grouped_children = _apply_grouper(args_dict, op_fn, ctx, attr_ctx, child.children, depth, op_args)
            # Yield the original Group with regrouped children
            yield Node(item=child.item, children=list(grouped_children))
        else:
            # Resolve any @attribute dependencies per-item
            item_args = resolve_per_item_attribute_dependencies(
                op_fn, args_dict, attr_ctx, child.item, op_args.per_item_attrs
            )
            # Regular grouping: use grouper function to get the key
            op_res = op_fn(ctx=ctx, item=child.item, **item_args)
            groups_map[op_res].append(child)

    # Extract attribute descriptor if available (for group_by_attribute).
    # Fall back to the "field" arg (for group_by_field) so group titles can
    # show the field name, e.g. "color=red".
    at_d = args_dict.get("attribute")
    if at_d is None:
        group_field = args_dict.get("field")
        if group_field is not None:
            at_d = AttributeDescriptor.create(str(group_field))

    # Order the groups. When the grouper returns a Group with an explicit
    # ``order``, sort by it; otherwise preserve first-seen insertion order.
    group_items = list(groups_map.items())
    if any(isinstance(k, Group) and k.order is not None for k, _ in group_items):

        def _group_order(kv: tuple) -> Any:
            k, _ = kv
            if isinstance(k, Group) and k.order is not None:
                return (0, k.order)
            return (1,)

        group_items.sort(key=_group_order)

    # Only yield new groups for non-Group items
    # Group items were already yielded above with their regrouped children
    for group_key, group in group_items:
        if isinstance(group_key, Group):
            # Grouper already returned a Group: don't rewrap; copy it and
            # attach the attribute descriptor after the grouper ran.
            group_item = Group(
                key=group_key.key,
                key_descriptor=group_key.key_descriptor or at_d,
                order=group_key.order,
            )
        else:
            # Create a Group item containing the key (the grouper result)
            # The grouped items are stored as children of the Group node
            group_item: Group = Group(key=group_key, key_descriptor=at_d)
        yield Node(item=group_item, children=group)


class GrouperApplier(ToolKindService, ChainStepServiceAPI):
    """The service that owns the grouper kind.

    Two contracts, one object: the chain routing hands it the grouper's chain groups
    (apply_chain_step), and the operators engine holds the module's applicator
    (_apply_grouper) in the dispatch it was registered into. The instance exists for
    the chain contract; the engine holds only the applicator function, so applying a
    grouper descriptor nested inside a run needs nothing from this service.

    A grouper wraps the nodes it is applied per into groups: the value its function
    returns per item keys a Group whose children are the nodes that returned it, in
    first-seen order (or the order an explicitly returned Group declares). A Group
    item among the children is re-grouped in place, keeping its key. With
    `--position`, only the children of the node the path names are re-grouped; the
    other nodes pass through untouched.
    """

    KINDS: tuple[ToolKind, ...] = (GROUPER,)
    """The kind this service owns: the grouper."""

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
        """Apply a grouper chain group at its chain position; return the next stage.

        The group goes to the engine's own chain step: this service owns the kind, the
        engine owns the walk.

        Args:
            descriptors: Grouper descriptors of the chain group, in written order
            stage: The forest the chain groups before this one produced
            chain_context: The per-query context of the walk
            ctx: Execution context for dependency injection and query-time logging
            item_cap: Optional bound on how many items the group may produce

        Returns:
            The forest the group produced
        """
        return self._operator_engine.apply_chain_step(descriptors, stage, chain_context, ctx, item_cap=item_cap)


class GrouperPlugin(Plugin):
    """The package's container contribution.

    Providing the applier contributes the kind's applicator to the engine's dispatch,
    the way the vocabulary provider contributes the kinds. The routing handler is not
    a decoration: the core builds the routing over its own services and hands it out,
    so the handler joins it in place - attach adds it, detach takes it back off.
    """

    @provide
    def grouper_applier(self, operator_engine: OperatorsEngineAPI) -> GrouperApplier:
        """Create the applier and register the module's applicator into the engine's dispatch."""
        applier = GrouperApplier(operator_engine=operator_engine)
        operator_engine.register_applicator(GROUPER, _apply_grouper)
        return applier

    def attach(self, routing: ChainRoutingAPI, grouper_applier: GrouperApplier) -> None:
        """Add the kind's handler to the chain routing, in place."""
        routing.add_handler(grouper_applier)

    def detach(self, routing: ChainRoutingAPI, grouper_applier: GrouperApplier) -> None:
        """Take the kind's handler back off the chain routing."""
        routing.remove_handler(grouper_applier)


DOMAIN = "grouper"
PLUGIN = GrouperPlugin
