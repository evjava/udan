"""Tests for the query parser extras: transformers registered on the parser.

A parser extra rewrites the query text before the parser's main work (the
parse). It is just a transformer - registered, applied in registration order,
unregistered - so every test's query only succeeds while its extra is
registered, and the rewritten values double as proof of the application point.
(The processor's half of the extras is gone: the question sugar wraps the
running resolver through the plugin's decorator instead -
tests/udan/plugins_help_sugar.)
"""

import pytest

import udan.attributes.plugins_operators_attribute
import udan.plugins_tools_core.plugins_system
import udan.plugins_tools_examples.plugins_builtins
import udan.renders.plugins_renders
from tests.conftest import make_qp
from udan.parsing.api_query_parser import QueryParserAPI, QueryParserExtraAPI
from udan.plugins_history import plugins_history
from udan.plugins_tools_demo import plugins_demo, plugins_fruits


class _TrioTextExtra(QueryParserExtraAPI):
    """Rewrites the word ``trio`` into the ``3`` it means, in the query text."""

    def transform_query_text(self, query_text: str) -> str:
        return query_text.replace("trio", "3")


class _OrderFirstExtra(QueryParserExtraAPI):
    """Rewrites ``ord`` into ``mid``: the first extra of the ordering pair."""

    def transform_query_text(self, query_text: str) -> str:
        return query_text.replace("ord", "mid")


class _OrderSecondExtra(QueryParserExtraAPI):
    """Rewrites ``mid`` into ``7``: the second extra of the ordering pair."""

    def transform_query_text(self, query_text: str) -> str:
        return query_text.replace("mid", "7")


class _QmarkTextExtra(QueryParserExtraAPI):
    """Rewrites ``dep?`` into ``range 5, :list``: the `?` is the extra's own sugar."""

    def transform_query_text(self, query_text: str) -> str:
        return query_text.replace("dep?", "range 5, :list")


@pytest.fixture
def ctx_with_extras(make_ctx):
    """Context with the canonical plugin set; extras register inside the tests."""
    return make_ctx(
        plugins_demo,
        plugins_fruits,
        udan.plugins_tools_examples.plugins_builtins,
        udan.plugins_tools_core.plugins_system,
        plugins_history,
        udan.attributes.plugins_operators_attribute,
        udan.renders.plugins_renders,
    )


def test_parser_extra_transforms_text_before_parse(ctx_with_extras):
    """A registered parser extra rewrites the text the parser parses."""
    parser = ctx_with_extras.container.get(QueryParserAPI)
    qp = make_qp(ctx_with_extras)
    extra = _TrioTextExtra()
    parser.register_parser_extra(extra)

    _, _, _, out = qp.execute_query("range trio, :list")
    assert out == "[0, 1, 2]"

    parser.unregister_parser_extra(extra)
    forest, _, _, _ = qp.execute_query("range trio, :list")
    assert forest is None


def test_parser_extras_apply_in_registration_order(ctx_with_extras):
    """The first registered extra's output is the second one's input."""
    parser = ctx_with_extras.container.get(QueryParserAPI)
    qp = make_qp(ctx_with_extras)
    parser.register_parser_extra(_OrderFirstExtra())
    parser.register_parser_extra(_OrderSecondExtra())

    _, _, _, out = qp.execute_query("range ord, :list")

    assert out == "[0, 1, 2, 3, 4, 5, 6]"


def test_parser_extra_runs_before_udan_heuristics(ctx_with_extras):
    """`dep?` reaches the extra raw: udan never moves its question mark first."""
    parser = ctx_with_extras.container.get(QueryParserAPI)
    qp = make_qp(ctx_with_extras)
    parser.register_parser_extra(_QmarkTextExtra())

    _, _, _, out = qp.execute_query("dep?")

    assert out == "[0, 1, 2, 3, 4]"
