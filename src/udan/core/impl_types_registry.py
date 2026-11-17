"""Type registry for checking and classifying items.

This module provides the TypesRegistry class which implements the TypesRegistryAPI.
It classifies a forest item as data or as a chain item (a tool descriptor of
any kind) - the one distinction every reader shares. Which kinds of chain item there
are is the kinds' business, not this registry's.
"""

from udan.core.api_types_registry import TypesRegistryAPI
from udan.core_tools_loading.api_tools import ToolDescriptor

# Type alias for readability
Item = object


def _is_chain_item(item: Item) -> bool:
    """Check if an item is a tool descriptor: a chain item, not data.

    Args:
        item: Item to check

    Returns:
        True if the item is a tool descriptor of any kind
    """
    return isinstance(item, ToolDescriptor)


class TypesRegistry(TypesRegistryAPI):
    """Registry for type checking and classification.

    This class provides methods for checking if items are specific types.
    It implements the TypesRegistryAPI interface.
    """

    def is_chain_item(self, item: object) -> bool:
        """Check if an item is a tool descriptor: a chain item, not data.

        Args:
            item: Item to classify

        Returns:
            True if the item is a tool descriptor of any kind
        """
        return _is_chain_item(item)
