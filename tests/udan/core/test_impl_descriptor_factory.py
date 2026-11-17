"""Descriptor factory framework arguments, the vararg items schema, and the missing-at_d question."""

import pytest

from udan.core.api_attributes import ATTRIBUTE, AttributeMetadata
from udan.core.api_constants import ARG_MAX_DEPTH, ARG_ON_DEPTH, ARG_POSITION
from udan.core.api_query_processor import QueryMiss
from udan.core.impl_debug_logger import DebugLogger
from udan.core.impl_descriptor_factory import (
    DescriptorFactory,
    _framework_depth_arg,
    _framework_int_arg,
    _framework_position_arg,
    _operator_sp_args,
    _vararg_items_schema,
)
from udan.core.impl_exec_context import ExecContext
from udan.core.impl_symbols_env import SymbolsEnv


@pytest.mark.parametrize(
    "value, expected",
    [
        ("0", 0),
        ("3", 3),
        ("all", "all"),
        ("leaf", "leaf"),
    ],
)
def test_framework_depth_arg(value, expected):
    """--on-depth accepts a depth level and the two selector words."""
    assert _framework_depth_arg("--on-depth", value) == expected


@pytest.mark.parametrize("value", ["5x", "ALL", "Leaf", ""])
def test_framework_depth_arg_rejects_other_values(value):
    """Anything that is neither a level nor a selector word names the accepted values."""
    with pytest.raises(TypeError, match="must be an integer, 'all' or 'leaf'"):
        _framework_depth_arg("--on-depth", value)


def test_framework_int_arg_stays_integer_only():
    """--max-depth counts recursion levels: it has no selector words."""
    assert _framework_int_arg("--max-depth", "3") == 3
    with pytest.raises(TypeError, match="--max-depth must be an integer"):
        _framework_int_arg("--max-depth", "all")


def test_framework_position_arg_single_index():
    assert _framework_position_arg("--position", "1") == (1,)


def test_framework_position_arg_hierarchical_path():
    assert _framework_position_arg("--position", "2.1") == (2, 1)
    assert _framework_position_arg("--position", "0.0.3") == (0, 0, 3)


def test_framework_position_arg_switched_off_comes_back_empty():
    """An empty value and -1 are the off-switches: no position, everywhere."""
    assert _framework_position_arg("--position", "") == ()
    assert _framework_position_arg("--position", "-1") == ()


def test_framework_position_arg_rejects_non_integers():
    with pytest.raises(TypeError, match="dot-separated path of integers"):
        _framework_position_arg("--position", "2.x")


def test_framework_position_arg_rejects_negative_index():
    with pytest.raises(TypeError, match="non-negative"):
        _framework_position_arg("--position", "1.-2")


def test_framework_position_arg_rejects_empty_component():
    with pytest.raises(TypeError, match="dot-separated path of integers"):
        _framework_position_arg("--position", "1.")


def test_operator_sp_args_carries_position():
    tool_args = _operator_sp_args(None, None, (2, 1))

    assert tool_args == {ARG_POSITION: (2, 1)}


def test_operator_sp_args_carries_all_framework_args():
    tool_args = _operator_sp_args(1, 2, (2, 1))

    assert tool_args == {ARG_ON_DEPTH: 1, ARG_MAX_DEPTH: 2, ARG_POSITION: (2, 1)}


def test_operator_sp_args_carries_depth_selectors():
    """The selector words ride the tool_args bag like a level does."""
    assert _operator_sp_args("all", 2, None) == {ARG_ON_DEPTH: "all", ARG_MAX_DEPTH: 2}
    assert _operator_sp_args("leaf", None, None) == {ARG_ON_DEPTH: "leaf"}


def test_operator_sp_args_drops_switched_off_position():
    """A switched-off position stores nothing: the descriptor has no --position at all."""
    assert _operator_sp_args(None, None, ()) is None


def test_operator_sp_args_empty_without_framework_args():
    assert _operator_sp_args(None, None, None) is None


def test_vararg_items_schema_from_array():
    assert _vararg_items_schema({"type": "array", "items": {"type": "string"}}) == {"type": "string"}
    assert _vararg_items_schema({"type": "array", "items": {"type": "integer"}}) == {"type": "integer"}


def test_vararg_items_schema_from_optional_array():
    """A `list[int] | None` vararg carries the element schema inside the array member."""
    assert _vararg_items_schema({"anyOf": [{"type": "array", "items": {"type": "integer"}}, {"type": "null"}]}) == {
        "type": "integer"
    }


def test_vararg_items_schema_empty_without_an_array():
    assert _vararg_items_schema({"type": "string"}) == {}
    assert _vararg_items_schema({}) == {}


def test_missing_at_d_raises_a_miss():
    """A required at_d that no argument fills is a miss, not a binding error.

    It rides past the binding to the walk's swap point, where the registered
    answerers decide what the query continues with. The demo attribute tools
    that need it are tests-only, so the schema here is hand-built: the same
    shape the loader produces for a tool with a required user-facing at_d.
    """
    metadata = AttributeMetadata(
        name="demo_attr_with_at_d",
        fn_path="tests.plugins_test_injected_args_demo:demo_attr_with_at_d",
        parameters={
            "type": "object",
            "properties": {"item": {"type": "string"}, "at_d": {"type": "object"}},
            "required": ["at_d"],
        },
        output_schema={"type": "string"},
        tool_type=ATTRIBUTE,
    )
    factory = DescriptorFactory(SymbolsEnv(vars_path="", logger=DebugLogger(log_time=False)), {})
    ctx = ExecContext(logger=DebugLogger(log_time=False))

    with pytest.raises(QueryMiss) as exc_info:
        factory.create_descriptor_from_args(
            "demo_attr_with_at_d",
            metadata,
            [],
            at_ds=[],
            render=[],
            last_operator=[],
            interpret_fn=lambda *args, **kwargs: None,
            ctx=ctx,
        )

    assert exc_info.value.pattern == ""
    assert exc_info.value.tool_type == "attribute"
