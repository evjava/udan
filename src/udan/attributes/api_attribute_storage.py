"""Public API for attribute storage.

This module defines the public API interface for attribute storage.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from udan.core.api_attributes import AttributeDescriptor, AttributeValue
    from udan.core.api_forests import Item


class AttributeStorageAPI:
    """API interface for attribute storage.

    This class defines the public API for storing and retrieving attribute values.
    The storage handles both hashable and unhashable items efficiently.
    """

    attributes: dict[AttributeDescriptor, dict[Item, AttributeValue]]

    def set_attr_value(self, at_d: AttributeDescriptor, item: Item, value: AttributeValue) -> None:
        """Store an attribute value for an item.

        Args:
            at_d: Attribute descriptor
            item: Item to store value for
            value: Attribute value to store
        """
        raise NotImplementedError

    def get_attr_value(self, at_d: AttributeDescriptor, item: Item) -> AttributeValue | None:
        """Get an attribute value for an item.

        Args:
            at_d: Attribute descriptor
            item: Item to get value for

        Returns:
            Attribute value or None if not found
        """
        raise NotImplementedError

    def get_attr_value_from_dict(self, at_d: AttributeDescriptor, item: Item) -> AttributeValue | None:
        """Get attribute value from the attributes dict (for external access).

        This method is used by rendering code to access attribute values.
        It handles both hashable and unhashable items.

        Args:
            at_d: Attribute descriptor
            item: Item to look up

        Returns:
            Attribute value or None if not found
        """
        raise NotImplementedError

    def has_attribute_descriptor(self, at_d: AttributeDescriptor) -> bool:
        """Check if any values exist for an attribute descriptor.

        Args:
            at_d: Attribute descriptor to check

        Returns:
            True if any values exist for this descriptor
        """
        raise NotImplementedError

    def delete_attr_values(self, at_d: AttributeDescriptor) -> None:
        """Remove all stored values for an attribute descriptor.

        Used when an attribute definition is replaced (e.g. a named cattr column
        redefined by a later query): the values of the old definition must not
        be served for the new one.

        Args:
            at_d: Attribute descriptor whose values to drop
        """
        raise NotImplementedError
