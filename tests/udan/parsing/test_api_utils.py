"""Tests for core_utils module."""

from udan.core_tools_loading.utils_str import flatten, normalize_fexpr, split_and_normalize, split_by
from udan.parsing.api_query_parser import remove_prefix_if_needed


def test_flatten_nested_lists():
    result = flatten([[1, 2], [3, 4], [5]])
    assert result == [1, 2, 3, 4, 5]


def test_flatten_empty_lists():
    result = flatten([[], []])
    assert result == []


def test_flatten_single_list():
    result = flatten([[1, 2, 3]])
    assert result == [1, 2, 3]


def test_flatten_strings():
    result = flatten([["a", "b"], ["c"]])
    assert result == ["a", "b", "c"]


def test_normalize_fexpr_lowercases():
    result = normalize_fexpr("HELLO")
    assert result == "hello"


def test_normalize_fexpr_strips_whitespace():
    result = normalize_fexpr("  hello  ")
    assert result == "hello"


def test_normalize_fexpr_combines_operations():
    result = normalize_fexpr("  HELLO WORLD  ")
    assert result == "hello world"


def test_split_by_with_separator():
    result = split_by("a,b,c", ",")
    assert result == ["a", "b", "c"]


def test_split_by_empty_string():
    result = split_by("", ",")
    assert result == []


def test_split_by_no_separator():
    result = split_by("abc", ",")
    assert result == ["abc"]


def test_split_by_with_none():
    result = split_by(None, ",")
    assert result == []


def test_split_and_normalize_splits_and_normalizes():
    result = split_and_normalize("  A,B , C  ")
    assert result == ["a", "b", "c"]


def test_split_and_normalize_handles_empty_string():
    result = split_and_normalize("")
    assert result == []


def test_split_and_normalize_handles_whitespace_only():
    result = split_and_normalize("   ")
    assert result == []


def test_split_and_normalize_handles_single_item():
    result = split_and_normalize("  HELLO  ")
    assert result == ["hello"]


def test_remove_prefix_if_needed_removes_prefix():
    result = remove_prefix_if_needed("prefix_value", "prefix_")
    assert result == "value"


def test_remove_prefix_if_needed_no_prefix_match():
    result = remove_prefix_if_needed("value", "prefix_")
    assert result == "value"


def test_remove_prefix_if_needed_exact_prefix_match_returns_empty():
    result = remove_prefix_if_needed("prefix_", "prefix_")
    assert result == ""


def test_remove_prefix_if_needed_empty_string():
    result = remove_prefix_if_needed("", "prefix_")
    assert result == ""


def test_remove_prefix_if_needed_prefix_same_as_string():
    result = remove_prefix_if_needed("same", "same")
    assert result == ""
