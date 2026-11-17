"""Tests for the miss answerer: the query that answers a lookup that found nothing."""

from udan.core.api_forests import Node
from udan.core.api_query_processor import QueryMiss
from udan.plugins_help_sugar.impl_miss_answers import QuestionMissAnswerer


def test_answer_miss_narrows_by_pattern_and_kind():
    """The question carries the miss's fragment as the pattern and its kind as the filter."""
    miss = QueryMiss(
        pattern="nonexistent_render",
        tool_type="render",
        reason="unknown render 'nonexistent_render' - listing renders",
    )

    assert QuestionMissAnswerer().answer_miss(miss) == Node.create(
        "?", [Node.leaf("--tool_type=render"), Node.leaf("--pattern=nonexistent_render")]
    )


def test_answer_miss_writes_no_empty_filters():
    """An unfiltered field stays out of the query: nothing narrows by nothing."""
    miss = QueryMiss(pattern="", tool_type="", reason="required 'at_d' is missing")

    assert QuestionMissAnswerer().answer_miss(miss) == Node.create("?", [])
