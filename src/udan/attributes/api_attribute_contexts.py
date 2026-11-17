"""Public API for the attributes context.

The per-query context the walk hands the chain handlers, seen from the attribute
domain: the core contract (udan.core.api_chain_context.ChainContextAPI) is the walk's
own vocabulary - descriptors, items, values - and this interface adds the typed
surface attribute tools use. The implementation that computes is built by this
package's runtime (impl_attribute_contexts); the store-only context the core
answers through the core contract alone.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from udan.core.api_chain_context import ChainContextAPI
from udan.core_tools_loading.api_tools_registry import ToolsRegistryAPI

if TYPE_CHECKING:
    from udan.attributes.api_attribute_runtime import AttributeRuntimeAPI
    from udan.core.api_attributes import AttributeDescriptor, AttributeValue
    from udan.core.api_forests import Item


class AttributesContextAPI(ChainContextAPI):
    """API interface for attributes context.

    This class defines the public API for the context passed to tools
    during expansion. Provides access to attribute runtime, registry, and
    attribute storage.

    Attributes:
        attribute_runtime: Attribute runtime for resolving attributes
        registry: Tools registry for looking up tools
        depth: Current depth in the tree during tool expansion
    """

    attribute_runtime: AttributeRuntimeAPI
    registry: ToolsRegistryAPI
    depth: int

    def set_attr_value(self, at_d: AttributeDescriptor, item: Item, value: AttributeValue) -> None:
        """Store an attribute value for an item.

        Args:
            at_d: Attribute descriptor
            item: Item to store value for
            value: Attribute value to store
        """
        raise NotImplementedError

    def get_requested_attributes(self) -> list[AttributeDescriptor]:
        """Get the list of requested attribute descriptors.

        Returns:
            List of attribute descriptors requested for calculation.
        """
        raise NotImplementedError

    def get_attr_value_from_storage(self, at_d: AttributeDescriptor, item: Item) -> AttributeValue | None:
        """Get attribute value from storage without triggering calculation.

        This method directly accesses the storage to check if a value exists
        without calculating it. Returns None if the value is not in storage
        (distinguishes "not calculated" from "calculated as None").

        This is used internally by the attribute system for:
        - Checking cache keys before calculation
        - Resolving attribute dependencies
        - Checking for pre-calculated values

        Args:
            at_d: Attribute descriptor to look up
            item: Item to look up

        Returns:
            Attribute value from storage, or None if not found
        """
        raise NotImplementedError

    def get_attr_value(self, at_d: AttributeDescriptor, item: Item) -> AttributeValue:
        """Get attribute value for an item, computing it on demand if needed.

        Unlike get_attr_value_from_storage which only checks pre-calculated values,
        this method triggers attribute calculation when the value is not yet
        in storage.

        Args:
            at_d: Attribute descriptor
            item: Item to get attribute value for

        Returns:
            Attribute value
        """
        raise NotImplementedError
