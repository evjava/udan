"""Public attribute API: the attribute kind and its vocabulary.

Attributes are the default kind of the language: a function computing a value for
an item. Everything the framework reads about the kind is declared here, as data
on the kind (its metadata class, the meta keys it promotes, the signature law) -
so the loader, the registry and the engines run the kind without naming it, and
the package that implements the kind (udan.attributes, part of udan) is read
through these contracts. The kind service that fills the vocabulary is always
composed, so the attribute domain cannot be switched off through the module list;
a tool whose kind no loaded package owns still resolves to a bare kind that
declares no rules.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from udan.core.api_constants import FRAMEWORK_PARAMS_ALL
from udan.core_tools_loading.api_tools import (
    ArgsInput,
    ToolDescriptor,
    ToolKind,
    ToolMetadata,
)

if TYPE_CHECKING:
    from udan.attributes.api_attribute_contexts import AttributesContextAPI
    from udan.core.api_forests import Node

AttributeValue = Any

# Attribute Metadata Keys
# =======================

# Metadata key for marking system attributes.
# System attributes are set by the framework (e.g., during pre-render phase)
# and are not calculated by normal attribute calculation.
#
# Example:
#   @annotated(meta={"tool_type": "attribute", SYSTEM: True})
#   def render(item: Item, depth: int = 0) -> str:
#       ...
SYSTEM: str = "system"

# Attribute Types
# ===============

# Values of AttributeMetadata.attribute_type: what shape of computation the
# attribute is.

ATTRIBUTE_TYPE_SIMPLE: str = "simple"
"""A per-item function of the item and its declared arguments."""

ATTRIBUTE_TYPE_COMPOSITE: str = "composite"
"""An attribute computed from other attributes' values."""

# Value for AttributeMetadata.attribute_type marking an aggregate attribute.
# Aggregate attributes compute a single value from all items in scope
# (e.g., count, sum, min, max) rather than per-item values.
#
# Example:
#   @annotated(meta={"attribute_type": ATTRIBUTE_TYPE_AGGREGATE})
#   def count(items: list[Item]) -> int:
#       return len(items)
ATTRIBUTE_TYPE_AGGREGATE: str = "aggregate"

# Value for AttributeMetadata.attribute_type marking a value-shaped attribute.
# Value attributes are generic value->value functions (e.g. text -> tags): they
# take no `item` parameter and compute from their arguments alone. This makes
# them valid composition targets: `extract_tags(summarizer)` feeds the
# summarizer output as the fn's value parameter, while values are still
# stored per item (column semantics).
#
# Example:
#   @annotated(meta={"attribute_type": ATTRIBUTE_TYPE_VALUE})
#   def extract_tags(text: str) -> list[str]:
#       return text.split()
ATTRIBUTE_TYPE_VALUE: str = "value"

# Value for AttributeMetadata.attribute_type marking a column-definition attribute.
# A chain item of such an attribute does not produce a value of its own: it
# defines a column. Query resolution asks the attribute's function to register
# the column (once per query) and the resolved descriptor is the column itself,
# so the native attribute path calculates and renders it under its own name.
#
# Example:
#   @annotated(meta={"attribute_type": ATTRIBUTE_TYPE_COLUMN})
#   def formula_column(expr: str, name: str | None = None, ...) -> str:
#       ...register the column under `name` (or the formula)...
#       return column_name
ATTRIBUTE_TYPE_COLUMN: str = "column"

# Framework Parameters
# ====================

# For attributes, only "item" is framework-injected (not ctx, items, or nodes).
# This is because attributes compute metadata for a single item at a time.
FRAMEWORK_PARAMS_ATTR: set[str] = set(FRAMEWORK_PARAMS_ALL) & {"item"}


class AttributeMetadata(ToolMetadata):
    """Metadata for attribute tools.

    Extends ToolMetadata with attribute-specific properties
    including caching support and attribute type.
    """

    # going to support propagator/aggregator/etc. in the future
    # The flavor of the attribute: what shape of computation it is (the
    # ATTRIBUTE_TYPE_* values). "simple" is the undeclared default.
    attribute_type: str = ATTRIBUTE_TYPE_SIMPLE
    # Caching support
    cache_attribute: str | None = None  # Name of attribute to use as cache key
    # Precalculated flag - this attribute's values are set during tool application
    # and should be retrieved from storage rather than calculated
    precalculated: bool = False  # Whether values are pre-calculated by tools


class AttributeDescriptor(ToolDescriptor):
    """Descriptor for attribute functions.

    Extends ToolDescriptor with attribute-specific functionality
    including validation and cache key generation.
    """

    @classmethod
    def create(
        cls,
        name: str,
        args: ArgsInput = None,
        *,
        tool_args: ArgsInput = None,
        metadata: ToolMetadata | None = None,
    ):
        """Create an AttributeDescriptor with validation.

        Args:
            name: Attribute name
            args: Arguments for the attribute
            tool_args: Tool arguments
            metadata: Optional metadata for validation

        Returns:
            AttributeDescriptor instance

        Raises:
            ValueError: If metadata is provided but doesn't have 'item' parameter
        """
        # Validate that metadata has 'item' parameter (when properties are properly populated)
        # Aggregate attributes have 'items' instead of `item`; value attributes are
        # generic value->value functions and column definitions run once per query,
        # so those take no `item`
        if metadata is not None:
            params = metadata.parameters
            if "properties" in params and len(params["properties"]) > 0:
                is_item_free = isinstance(metadata, AttributeMetadata) and metadata.attribute_type in (
                    ATTRIBUTE_TYPE_AGGREGATE,
                    ATTRIBUTE_TYPE_VALUE,
                    ATTRIBUTE_TYPE_COLUMN,
                )
                if not is_item_free and "item" not in params["properties"]:
                    raise ValueError(
                        f"Attribute '{name}' must have 'item' parameter in schema. "
                        f"Properties: {list(params['properties'].keys())}"
                    )

        # Create instance
        return super().create(name, args, tool_args=tool_args)

    def __str__(self):
        args = "{" + str(dict(self.args)) + "}"
        return f"AttrD[{self.name}]{args}"

    def cache_key(self) -> str:
        """Serialize descriptor to a string key for caching.

        Returns a unique string representation including name and args.
        The args are sorted to ensure consistent serialization.

        Returns:
            String key in format: "name:args_sorted"
        """
        # Sort args for consistent serialization
        args_sorted = tuple(sorted(self.args)) if self.args else ()
        args_str = str(dict(args_sorted)) if args_sorted else ""
        return f"{self.name}:{args_str}"

    def __hash__(self) -> int:
        """Hash based on cache_key for dictionary key usage."""
        return hash(self.cache_key())

    def __eq__(self, other) -> bool:
        """Equality based on cache_key for dictionary key usage."""
        if not isinstance(other, AttributeDescriptor):
            return False
        return self.cache_key() == other.cache_key()


ATTRIBUTE = ToolKind(
    name="attribute",
    filter_group="attribute",
    item_type_keys=("item_type",),
    forms_chain=True,
    is_default=True,
    keeps_item_parameter=True,
    metadata_cls=AttributeMetadata,
    metadata_meta_keys=("attribute_type", "cache_attribute", "precalculated"),
    metadata_variant_key="attribute_type",
    metadata_item_free_values=(ATTRIBUTE_TYPE_AGGREGATE, ATTRIBUTE_TYPE_VALUE, ATTRIBUTE_TYPE_COLUMN),
)
"""The default kind: a function computing a value for an item."""


def is_aggregate_attribute(registry: Any, key: str) -> bool:
    """Does this attribute compute one value over all items instead of per item?

    The predicate the chain sequencing needs: an aggregate is computed over the
    items that exist at its chain position, so it is the attribute family the
    walk applies as its own stage. It lives beside the kind's vocabulary, not on
    the registry, because "aggregate" is a word of the attribute domain.

    Args:
        registry: Tools registry the attribute resolves from
        key: Attribute name or alias

    Returns:
        True when the attribute is registered with the aggregate attribute_type
    """
    metadata = registry.get_metadata(key)
    return bool(isinstance(metadata, AttributeMetadata) and metadata.attribute_type == ATTRIBUTE_TYPE_AGGREGATE)


class Attribute(ABC):
    """Base class for all attributes.

    Provides the common interface for attribute calculation.
    """

    @abstractmethod
    def calculate(self, context: AttributesContextAPI, children: Iterable[Node]) -> None:
        """Calculate attribute values for items.

        Args:
            context: Forest context with attribute storage (access context.ctx for UdanContext)
            children: Nodes to calculate attributes for
        """
        ...
