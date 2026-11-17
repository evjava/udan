"""Tests for saved query tag normalization helpers."""

from udan.plugins_history.impl_saved_tags import join_tags, split_tags


def test_split_tags_empty():
    """Test that empty input yields no tags."""
    assert split_tags(None) == []
    assert split_tags("") == []
    assert split_tags("   ") == []


def test_split_tags_whitespace_separated():
    """Test that whitespace-separated tags are split."""
    assert split_tags("alice bob") == ["alice", "bob"]


def test_split_tags_comma_separated():
    """Test that comma-separated tags are split."""
    assert split_tags("alice, bob") == ["alice", "bob"]


def test_split_tags_strips_brackets():
    """Test that surrounding render brackets are ignored."""
    assert split_tags("[alice bob]") == ["alice", "bob"]
    assert split_tags("[alice, bob]") == ["alice", "bob"]


def test_split_tags_dedupes_preserving_order():
    """Test that duplicate tags are dropped, first occurrence order kept."""
    assert split_tags("b a b c a") == ["b", "a", "c"]


def test_join_tags_empty():
    """Test that empty input yields the empty string."""
    assert join_tags(None) == ""
    assert join_tags([]) == ""
    assert join_tags("") == ""


def test_join_tags_from_list():
    """Test that a tag list normalizes to a space-separated string."""
    assert join_tags(["alice", "bob"]) == "alice bob"


def test_join_tags_from_string():
    """Test that a raw string normalizes like split_tags."""
    assert join_tags("[alice, bob]") == "alice bob"


def test_join_split_roundtrip():
    """Test that split and join are inverse operations."""
    assert split_tags(join_tags(["b", "a", "b"])) == ["b", "a"]
    assert join_tags(split_tags("[a, b] c")) == "a b c"
