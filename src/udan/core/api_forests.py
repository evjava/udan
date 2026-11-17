from collections.abc import Iterable
from types import SimpleNamespace
from typing import Any, Self

from pydantic import BaseModel, Field, model_validator

from udan.core.api_type_system import ForestTypeDescriptor

Depth = int

# The value carried by one forest node: whatever the tools produce. It lives
# here, beside the forest that stores it, not in the tools package.
Item = Any


class Forest(BaseModel):
    """Forest data structure with parallel depth and item arrays."""

    depths: list[Depth]
    items: list[Item]
    # Item types per forest level, folded from the tool chain at query
    # resolution (see ForestTypeDescriptor). Empty depths mean "unknown /
    # hand-built"; the field itself is never None.
    types: ForestTypeDescriptor = Field(default_factory=ForestTypeDescriptor)

    def as_pairs(self) -> Iterable[tuple[Depth, Item]]:
        """Iterate over depth-item pairs."""
        return zip(self.depths, self.items)

    @classmethod
    def from_items(cls, items):
        return cls(items=items, depths=[0] * len(items))

    @classmethod
    def from_pairs(cls, pairs: Iterable[tuple[Depth, Item]]) -> Self:
        """Create a Forest from depth-item pairs.

        Args:
            pairs: Iterable of (depth, item) tuples

        Returns:
            A Forest with depths and items extracted from pairs
        """
        pairs_list = list(pairs)
        if not pairs_list:
            return cls(depths=[], items=[])
        depths = [depth for depth, _ in pairs_list]
        items = [item for _, item in pairs_list]
        return cls(depths=depths, items=items)

    def __len__(self):
        return len(self.depths)

    def convert_to_node(self) -> Node:
        """Convert the forest to a node tree (see _convert_forest_to_node)."""
        return _convert_forest_to_node(self)

    @model_validator(mode="after")
    def check_same_lengths(self) -> Self:
        if len(self.depths) != len(self.items):
            raise ValueError(f"len(depths) -> {len(self.depths)} != {len(self.items)} <- items")
        return self


class Node(BaseModel):
    """Tree node with item and children."""

    item: Item
    children: list[Node] = Field(default_factory=list)
    # Item types per level of the forest this tree maps to, folded from the
    # tool chain at query resolution (see ForestTypeDescriptor). Level 0 is
    # the node's children: _convert_node_to_forest skips the node itself, so the
    # descriptor is the same on both sides of a conversion. Empty depths mean
    # "unknown / hand-built"; the field itself is never None.
    types: ForestTypeDescriptor = Field(default_factory=ForestTypeDescriptor)
    # Provenance: which chain step created the node, and the file it came from
    source_operator: str | None = None  # Which chain step created this node
    source_path: str | None = None  # Original file path
    # Origin chain: list of descriptors of the chain steps that created/affected this node
    # Stored as Any: a level's descriptor type lives with the chain that built it
    origin_chain: list[Any] = Field(default_factory=list)

    @classmethod
    def leaf(cls, item: Item) -> Node:
        """Create a leaf node (no children)."""
        return cls(item=item)

    @classmethod
    def create(cls, item: Item, children: list[Node] | None = None) -> Node:
        return cls(item=item, children=children or [])

    def walk(self, walker):
        """Walk the tree with a walker object."""
        walker.pre(self)
        walker.inc()
        for child in self.children:
            child.walk(walker)
        walker.dec()

    def convert_to_forest(self) -> Forest:
        """Convert the node tree to a forest (see _convert_node_to_forest)."""
        return _convert_node_to_forest(self)

    def __repr__(self) -> str:
        children_pretty = ", ".join(map(repr, self.children))
        ch_pretty = f", ch=[{children_pretty}]" if children_pretty else ""
        return f"N(item={self.item}{ch_pretty})"


def _convert_forest_to_node(forest: Forest) -> Node:
    """Convert forest format to node tree format.

    The forest's types travel with the tree: the root node carries
    ``forest.types`` (see Node.types), so the descriptor survives the
    conversion instead of being re-attached by callers.
    """
    if not forest.items:
        return Node(item="forest", children=[], types=forest.types)

    root = Node(item="forest", children=[], types=forest.types)
    stack: list[tuple[int, Node]] = [(-1, root)]

    for depth, item in forest.as_pairs():
        node = Node(item=item, children=[])
        while stack and stack[-1][0] >= depth:
            stack.pop()
        if stack:
            stack[-1][1].children.append(node)
        elif root is None:
            root = node
        else:
            raise ValueError("Forest contains multiple top-level nodes; cannot convert to a single tree")
        stack.append((depth, node))

    return root


def _convert_node_to_forest(node: Node) -> Forest:
    """Convert node tree format to forest format.

    The node's types travel with the forest (see Node.types): level 0 of the
    descriptor is this node's children, which is depth 0 of the forest.
    """
    depths, items = [], []
    cur_depth = [-1]

    def walker_pre(node: Node):
        if cur_depth[0] == -1:
            return
        depths.append(cur_depth[0])
        items.append(node.item)

    def walker_inc():
        cur_depth[0] += 1

    def walker_dec():
        cur_depth[0] -= 1

    walker = SimpleNamespace(
        pre=walker_pre,
        inc=walker_inc,
        dec=walker_dec,
    )
    node.walk(walker)
    return Forest(depths=depths, items=items, types=node.types)


class ForestBuilder:
    """Builder for creating forests incrementally."""

    def __init__(self) -> None:
        self.depths: list[Depth] = []
        self.items: list[Item] = []

    def add(self, item: Item, depth: Depth = 0):
        """Add an item with given depth."""
        self.depths.append(depth)
        self.items.append(item)

    def build_forest(self) -> Forest:
        """Build the forest."""
        return Forest(depths=self.depths, items=self.items)


# Module-level constants for empty forests
EMPTY_FOREST = Forest.from_items([])
