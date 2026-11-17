"""Tests for user-facing description refinement.

Parameters that are not user-insertable (DI-provided like ``context: SavedQueriesAPI``,
and framework-provided like ``ctx`` / ``item``) must not
appear in the user-facing description: their ``Args:`` entries are stripped at
metadata load time, cached per module identity.
"""

from udan.core_tools_loading.impl_utils_tools_loader import _strip_hidden_args_from_doc, get_user_description

DOC_WITH_MIXED_ARGS = """List demo items.

Args:
    query: Visible query parameter.
    config: Hidden injected config.
        Continuation line of the hidden entry.

Returns:
    Nothing.
"""

DOC_WITH_ONLY_HIDDEN_ARGS = """Collect tags.

Args:
    context: Auto-injected SavedQueriesAPI.

Returns:
    List of dicts.
"""


def test_strip_hidden_args_removes_hidden_entry_with_continuation():
    result = _strip_hidden_args_from_doc(DOC_WITH_MIXED_ARGS, {"query"})

    expected = "List demo items.\n\nArgs:\n    query: Visible query parameter.\n\nReturns:\n    Nothing.\n"
    assert result == expected


def test_strip_hidden_args_removes_whole_section_when_all_hidden():
    result = _strip_hidden_args_from_doc(DOC_WITH_ONLY_HIDDEN_ARGS, set())

    expected = "Collect tags.\n\nReturns:\n    List of dicts.\n"
    assert result == expected


def test_strip_hidden_args_returns_doc_unchanged_without_args_section():
    doc = "Summary line.\n\nReturns:\n    Nothing.\n"

    assert _strip_hidden_args_from_doc(doc, {"query"}) == doc
    assert _strip_hidden_args_from_doc(doc, set()) == doc


def _demo_fn(query: str | None = None, config: str | None = None) -> list:
    """List demo items.

    Args:
        query: Visible query parameter.
        config: Hidden injected config.
    """
    return []


def test_get_user_description_cached_by_params():
    description = _demo_fn.__doc__ or ""

    first = get_user_description(_demo_fn, description, {"query"})
    second = get_user_description(_demo_fn, description, {"query"})

    # Same fn + same params -> identical cached object, no recomputation
    assert second is first

    # Different user_param_names -> different cache entry, recomputed
    hidden_all = get_user_description(_demo_fn, description, set())
    assert hidden_all is not first
    assert hidden_all == "List demo items."
