"""Tests for AttributeStorage implementation."""

from udan.attributes.impl_attribute_storage import AttributeStorage
from udan.core.api_attributes import AttributeDescriptor


def test_set_attr_value_hashable_item():
    """Test setting attribute value for hashable item."""
    storage = AttributeStorage()
    at_d = AttributeDescriptor.create("test_attr", args={})
    item = "test_item"

    storage.set_attr_value(at_d, item, "test_value")

    # Value should be stored
    assert storage.get_attr_value(at_d, item) == "test_value"


def test_set_attr_value_unhashable_item():
    """Test setting attribute value for unhashable item (dict)."""
    storage = AttributeStorage()
    at_d = AttributeDescriptor.create("test_attr", args={})
    item = {"key": "value"}  # Unhashable

    storage.set_attr_value(at_d, item, "test_value")

    # Value should be stored
    assert storage.get_attr_value(at_d, item) == "test_value"


def test_set_attr_value_overwrites_existing():
    """Test that set_attr_value overwrites existing value."""
    storage = AttributeStorage()
    at_d = AttributeDescriptor.create("test_attr", args={})
    item = "test_item"

    storage.set_attr_value(at_d, item, "value1")
    storage.set_attr_value(at_d, item, "value2")

    # Should have the latest value
    assert storage.get_attr_value(at_d, item) == "value2"


def test_set_attr_value_multiple_items():
    """Test setting attribute values for multiple items."""
    storage = AttributeStorage()
    at_d = AttributeDescriptor.create("test_attr", args={})
    item1 = "item1"
    item2 = "item2"

    storage.set_attr_value(at_d, item1, "value1")
    storage.set_attr_value(at_d, item2, "value2")

    # Both values should be stored
    assert storage.get_attr_value(at_d, item1) == "value1"
    assert storage.get_attr_value(at_d, item2) == "value2"


def test_set_attr_value_multiple_attributes():
    """Test setting multiple attributes for same item."""
    storage = AttributeStorage()
    at_d1 = AttributeDescriptor.create("attr1", args={})
    at_d2 = AttributeDescriptor.create("attr2", args={})
    item = "test_item"

    storage.set_attr_value(at_d1, item, "value1")
    storage.set_attr_value(at_d2, item, "value2")

    # Both attributes should be stored
    assert storage.get_attr_value(at_d1, item) == "value1"
    assert storage.get_attr_value(at_d2, item) == "value2"


def test_get_attr_value_returns_none_for_unknown_attribute():
    """Test that get_attr_value returns None for unknown attributes."""
    storage = AttributeStorage()
    at_d = AttributeDescriptor.create("test_attr", args={})
    item = "test_item"

    assert storage.get_attr_value(at_d, item) is None


def test_get_attr_value_returns_none_for_unknown_item():
    """Test that get_attr_value returns None for unknown item."""
    storage = AttributeStorage()
    at_d = AttributeDescriptor.create("test_attr", args={})
    item1 = "item1"
    item2 = "item2"

    storage.set_attr_value(at_d, item1, "value1")

    assert storage.get_attr_value(at_d, item2) is None
