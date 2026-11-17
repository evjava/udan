"""API types tied to the tool wire format.

Every type here names a tool descriptor in one of its fields, so the module
lives beside the descriptor model. The descriptor-free data types live in the udan
core (Item in udan.core.api_forests) or beside the consumers (Edge, JsonValue); the
item-type vocabulary (ITEM_TYPE_GROUP, the accepted-type families) is
udan.core.api_item_types - only the marker the loader itself reads lives here.
"""

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict

from udan.core_tools_loading.api_tools import ToolDescriptor

# JSON-serializable value: the type of data produced by YAML/JSON parsers.
# A dict with string keys, lists, strings, numbers, bools, or None — recursively.
type JsonValue = dict[str, "JsonValue"] | list["JsonValue"] | str | int | float | bool | None

ITEM_TYPE_ANY = "any"
"""The item-type contract that is no contract: what the loader derives for an
untyped `item` parameter and reads for an undeclared `item_type`. The rest of the
vocabulary - the level types and the families that accept each other's items - is
the core's, udan.core.api_item_types."""


@dataclass(frozen=True)
class Group:
    """A level container holding a grouping key.

    A Group object contains the grouping key the items were grouped by. The actual
    grouped items are stored as children of the Group node in the forest, not in
    the Group object itself.
    """

    key: Any  # The grouping key (result of the grouper function)
    key_descriptor: ToolDescriptor | None = None  # The descriptor the grouping ran over (if any)
    order: Any = None  # Optional ordering key used to sort groups relative to each other

    def __str__(self) -> str:
        """String representation showing group key."""
        return f"group={self.key}"


class TypeDescriptor(BaseModel):
    """Item type at one level of a forest.

    Describes what kind of item lives at one depth of a Forest: the declared
    item type name, an optional domain meaning, and the descriptors requested
    against this level. Levels are built by the query resolver while it folds
    the tool chain (see ForestTypeDescriptor).
    """

    model_config = ConfigDict(frozen=True)

    name: str  # item type at this level: "dict", "int", "group"
    semantic: str | None = None  # domain meaning: "fruit", "number"; empty until declared by plugins
    requested: list[ToolDescriptor] = []  # descriptors requested against this level

    def with_requested(self, desc: ToolDescriptor) -> TypeDescriptor:
        """Return a copy of this level with one more requested descriptor."""
        return self.model_copy(update={"requested": [*self.requested, desc]})

    def __str__(self) -> str:
        """Short representation: "dict", "dict/fruit", "dict/fruit{fruit_cost, pfc}"."""
        base = self.name if self.semantic is None else f"{self.name}/{self.semantic}"
        if not self.requested:
            return base
        requested = ", ".join(desc.name for desc in self.requested)
        return f"{base}{{{requested}}}"

    __repr__ = __str__


class Edge(BaseModel):
    """Directed edge between two nodes, with optional metadata.

    Carries the endpoints as data so producers of graphs (e.g. extend_package_imports)
    and renderers of graphs (e.g. as_dot) share one structure instead of exchanging
    formatted strings.
    """

    model_config = ConfigDict(frozen=True)

    source: str
    target: str
    metadata: str | None = None  # what the edge goes through (module path, symbol, ...)

    def __str__(self) -> str:
        """Readable form: "a -> b", with the metadata in parentheses when present."""
        if self.metadata is None:
            return f"{self.source} -> {self.target}"
        return f"{self.source} -> {self.target} ({self.metadata})"

    __repr__ = __str__
