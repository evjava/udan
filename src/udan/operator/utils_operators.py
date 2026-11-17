"""The machinery the operator applicators share.

The applicator contract's behavior side: every applicator - the engine's own, and
the ones the kind services contribute for their kinds - reads the selector values
pre-extracted into OperatorArgs (on_depth, position, max_depth) through the helpers
here, so the depth arithmetic, the selector words and the position-path reading stay
one algorithm no matter which kind's applicator walks the tree. The per-item
attribute resolution the applicators with @attribute dependencies share lives here
too, so the kinds that read attributes resolve them the same way.

The module lives in this package with the engine it serves: the applicators it is for
belong to the operator family, and the kind packages whose applicators read it import
it from here.
"""

from __future__ import annotations

from collections.abc import Callable
from inspect import signature
from typing import Any

from udan.core.api_chain_context import ChainContextAPI
from udan.core.api_constants import DepthSelector
from udan.core.api_forests import Item, Node
from udan.operator.api_operator_engine import OperatorArgs


def on_depth_targets(on_depth: DepthSelector | None, depth: int, node: Node) -> bool:
    """Does this --on-depth selector target this node?

    An integer matches the nodes at that depth level only. The two selector words
    match by the node instead of by the level: "all" matches every node of the
    input tree, "leaf" matches the nodes without children - which is a property of
    the node, so the walk has to visit every node and test each one, the way it
    does for an unset selector.

    Args:
        on_depth: The selector from --on-depth, None when not specified
        depth: Depth of the node in the tree (0 at the operator input)
        node: The node the question is about

    Returns:
        True when the node is a target of the operator
    """
    if on_depth is None or on_depth == "all":
        return True
    if on_depth == "leaf":
        return not node.children
    return depth == on_depth


def positioned_op_args(op_args: OperatorArgs) -> OperatorArgs:
    """The same operator args with the position cleared.

    An applicator that already walked to its target position passes these to the
    recursions it triggers from there (max_depth for an extender, nested groups for
    a grouper), so the walk does not restart from the top of the subtree.
    """
    return op_args.model_copy(update={"position": None})


def apply_at_position(
    nodes: list[Node], position: tuple[int, ...], apply_at_target: Callable[[Node], Node]
) -> list[Node]:
    """Apply `apply_at_target` to the one node `position` names; the other nodes pass through.

    The path is hierarchical sibling indexes: "1.2" is children[1].children[2], so with
    every level a flat list it is just an index. A component past the end of its sibling
    list matches nothing and every node passes through, the way --on-depth past the last
    level extends nothing.

    Args:
        nodes: Sibling nodes the first path component indexes into
        position: Path of sibling indexes to the target node
        apply_at_target: Called with the target node, returns its replacement

    Returns:
        The sibling list with the target node replaced
    """
    head, rest = position[0], position[1:]
    results: list[Node] = []
    for index, node in enumerate(nodes):
        if index != head:
            results.append(node)
        elif rest:
            new_children = apply_at_position(node.children, rest, apply_at_target)
            results.append(node.model_copy(update={"children": new_children}))
        else:
            results.append(apply_at_target(node))
    return results


def resolve_per_item_attribute_dependencies(
    op_fn: Callable,
    args_dict: dict[str, Any],
    attr_ctx: ChainContextAPI,
    item: Item,
    per_item_attrs: dict[str, Any],
) -> dict[str, Any]:
    """Resolve per-item attribute dependencies.

    For operators with @attribute marker in dependencies, this resolves
    the attribute value for each item during operator application.

    Args:
        op_fn: The operator function
        args_dict: Resolved arguments from resolve_depends
        attr_ctx: Attributes context
        item: Current item to resolve attribute for
        per_item_attrs: Dict of param_name -> AttributeDescriptor to resolve per-item

    Returns:
        Copy of args_dict with resolved per-item attribute values
    """
    if not per_item_attrs:
        return args_dict

    sig = signature(op_fn)
    item_args = dict(args_dict)
    for param_name, attr_d in per_item_attrs.items():
        if param_name in sig.parameters:
            attr_value = attr_ctx.get_value(attr_d, item)
            item_args[param_name] = attr_value
    return item_args
