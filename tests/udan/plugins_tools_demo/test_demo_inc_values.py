"""Test add_values attribute for adding values to a number."""

import inspect

from udan.plugins_tools_demo.plugins_demo import add_values


def test_add_values_direct_function():
    """Test add_values as a Python function (not in a query)."""

    # Test basic usage
    result = add_values(5, [10])
    assert result == [15]

    # Test multiple increments
    result = add_values(5, [1, 2])
    assert result == [6, 7]

    # Test with empty list
    result = add_values(5, [])
    assert result == []

    # Test with negative numbers
    result = add_values(10, [-5])
    assert result == [5]

    # Test with floats
    result = add_values(5.5, [1.5])
    assert result == [7.0]

    # Test with multiple values
    result = add_values(0, [1, 2, 3])
    assert result == [1, 2, 3]


def test_add_values_function_signature():
    """Test add_values has correct function signature."""

    sig = inspect.signature(add_values)
    assert "item" in sig.parameters
    assert "increments" in sig.parameters
    assert sig.parameters["increments"].default is None


def test_add_values_returns_list():
    """Test add_values always returns a list."""

    # Single increment
    result = add_values(5, [3])
    assert isinstance(result, list)
    assert result == [8]

    # Multiple increments
    result = add_values(5, [1, 2, 3])
    assert isinstance(result, list)
    assert result == [6, 7, 8]

    # Empty list returns empty list
    result = add_values(5, [])
    assert isinstance(result, list)
    assert result == []


def test_add_values_zero_and_empty_list():
    """Test add_values handles edge cases."""

    # Empty list should return empty list
    result = add_values(5, [])
    assert result == []

    # Zero increment
    result = add_values(5, [0])
    assert result == [5]

    # Multiple zeros
    result = add_values(5, [0, 0, 0])
    assert result == [5, 5, 5]


def test_add_values_large_numbers():
    """Test add_values with large numbers."""

    # Large increments
    result = add_values(1000, [10000, 50000])
    assert result == [11000, 51000]

    # Negative to positive
    result = add_values(-100, [150])
    assert result == [50]
