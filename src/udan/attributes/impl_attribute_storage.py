"""Storage for attribute values."""

from __future__ import annotations

from udan.attributes.api_attribute_storage import AttributeStorageAPI
from udan.core.api_attributes import AttributeDescriptor, AttributeValue
from udan.core.api_forests import Item


class AttributeStorage(AttributeStorageAPI):
    """Storage for attribute values.

    This is the implementation of AttributeStorageAPI.
    The API documentation is in the AttributeStorageAPI class in api.py.
    """

    def __init__(
        self,
        attributes: dict[AttributeDescriptor, dict[Item, AttributeValue]] | None = None,
        unhashable: dict[AttributeDescriptor, dict[int, tuple[Item, AttributeValue]]] | None = None,
    ) -> None:
        self.attributes: dict[AttributeDescriptor, dict[Item, AttributeValue]] = (
            attributes if attributes is not None else {}
        )
        # Separate storage for unhashable items (uses id as key)
        self._unhashable: dict[AttributeDescriptor, dict[int, tuple[Item, AttributeValue]]] = (
            unhashable if unhashable is not None else {}
        )

    def set_attr_value(self, at_d: AttributeDescriptor, item: Item, value: AttributeValue) -> None:
        """Store an attribute value for an item."""
        try:
            # Try to use item directly as key
            hash(item)
            if at_d not in self.attributes:
                self.attributes[at_d] = {}
            self.attributes[at_d][item] = value
        except TypeError:
            # Item is unhashable (e.g., dict), use id as key
            if at_d not in self._unhashable:
                self._unhashable[at_d] = {}
            self._unhashable[at_d][id(item)] = (item, value)

    def get_attr_value(self, at_d: AttributeDescriptor, item: Item) -> AttributeValue | None:
        """Get an attribute value for an item."""
        try:
            # Try to look up by item directly
            hash(item)
            if at_d not in self.attributes:
                return None
            return self.attributes[at_d].get(item)
        except TypeError:
            # Item is unhashable, look up by id
            if at_d not in self._unhashable:
                return None
            result = self._unhashable[at_d].get(id(item))
            return result[1] if result else None

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
        # First try regular attributes (hashable items)
        if at_d in self.attributes:
            try:
                return self.attributes[at_d].get(item)
            except TypeError:
                pass  # Item is unhashable, fall through to unhashable storage

        # Try unhashable storage
        if at_d in self._unhashable:
            result = self._unhashable[at_d].get(id(item))
            return result[1] if result else None

        return None

    def has_attribute_descriptor(self, at_d: AttributeDescriptor) -> bool:
        """Check if any values exist for an attribute descriptor."""
        return at_d in self.attributes or at_d in self._unhashable

    def delete_attr_values(self, at_d: AttributeDescriptor) -> None:
        """Remove all stored values for an attribute descriptor."""
        self.attributes.pop(at_d, None)
        self._unhashable.pop(at_d, None)
