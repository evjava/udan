"""Tests for incomplete operator names in queries: what a bare word answers.

The expansion of a whole-query word (`gi`, `git.`) is the question sugar's
rewrite (tests/udan/plugins_help_sugar); these tests pin what the queries
answer through the pipeline: the listing, and the words that are not questions.
"""

import pytest

from tests.conftest import load_enabled_plugins, make_qp
from udan.core.config import UdanConfig
from udan.core.impl_ioc import create_udan_container
from udan.core.impl_udan_context import UdanContext


@pytest.fixture
def ctx_with_operators():
    """Context with all tools plugins loaded (the boot's plugin half)."""
    container = create_udan_container(UdanConfig())
    ctx_obj = container.get(UdanContext)
    ctx_obj.container = container
    load_enabled_plugins(ctx_obj)
    ctx_obj.container = container
    return ctx_obj


def test_short_word_lists_matches(ctx_with_operators):
    """A short word typed alone asks for the tools containing it."""
    qp = make_qp(ctx_with_operators)
    _, _, _, out, _ = qp.execute_query_split_debug("gi")

    assert "git.git_diff_file_size" in out
    assert "fs.git_tree" in out


def test_domain_dot_lists_the_domain(ctx_with_operators):
    """`git.` asks for the git domain's tools."""
    qp = make_qp(ctx_with_operators)
    _, _, _, out_dot, _ = qp.execute_query_split_debug("git.")
    _, _, _, out_question, _ = qp.execute_query_split_debug("? git.")

    assert out_dot == out_question
    assert "git.insert_diff" in out_dot


def test_short_word_narrower_than_domain_listing(ctx_with_operators):
    """`git.` lists the git domain alone; the full listing is bigger."""
    qp = make_qp(ctx_with_operators)
    _, _, _, out_dot, _ = qp.execute_query_split_debug("git.")
    _, _, _, out_all, _ = qp.execute_query_split_debug("?")

    assert 0 < len(out_dot.splitlines()) < len(out_all.splitlines())


def test_exact_operator_is_not_a_question(ctx_with_operators):
    """`range` is an exact key: it runs as the tool it is, not as a question."""
    qp = make_qp(ctx_with_operators)
    _, _, _, out_range, _ = qp.execute_query_split_debug("range 3")
    _, _, _, out_question, _ = qp.execute_query_split_debug("? range")

    assert "0" in out_range
    assert out_range != out_question


def test_long_word_is_judged_by_the_resolver(ctx_with_operators):
    """A 6-char unknown word is data or a query: no listing explosion, a clean miss."""
    qp = make_qp(ctx_with_operators)
    _, _, _, out, _ = qp.execute_query_split_debug("zzzzzz")

    assert "raiser" not in out  # a 6-char word does not question-list its matches


def test_number_literal_stays_data(ctx_with_operators):
    """A bare number is literal data, not a question about matching tools."""
    qp = make_qp(ctx_with_operators)
    forest, _, _, out, _ = qp.execute_query_split_debug("123")

    assert "123" in out
    assert "domain=" not in out
