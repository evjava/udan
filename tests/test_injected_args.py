"""Test that injected framework parameters are properly handled.

This test verifies that parameters injected by the framework are removed from
user-facing parameter schemas.

Injected parameters:
- 'ctx': UdanContext, injected for inserters, filters, groupers, replacers
- 'item': Current item, injected for filters, extenders, groupers, sorters, mappers
- 'items': List of items, injected for non-nested replacers
- 'nodes': List of nodes, injected for nested replacers

The 'at_d' parameter is NOT injected - it's a user-facing parameter for operators
like group_by_attribute and filter_by_attribute where users specify which attribute to use.
"""

import tests.plugins_test_injected_args_demo
from udan.core_tools_loading.impl_utils_tools_loader import (
    convert_tool_to_metadata,
    extract_injected_args,
    patch_operator_parameters,
)
from udan.core_tools_loading.io_inspect import get_tool_for_function

demo_attr_with_at_d = tests.plugins_test_injected_args_demo.demo_attr_with_at_d
demo_attr_with_both = tests.plugins_test_injected_args_demo.demo_attr_with_both
demo_filter_with_at_d = tests.plugins_test_injected_args_demo.demo_filter_with_at_d
demo_filter_withctx = tests.plugins_test_injected_args_demo.demo_filter_withctx


def test_extract_injected_args_identifies_ctx_and_item():
    """Test that extract_injected_args identifies ctx and item as injected for filters."""
    injected = extract_injected_args(demo_filter_withctx)

    assert "ctx" in injected, "ctx should be identified as injected"
    assert "item" in injected, "item should be identified as injected for filter operators"
    assert "at_d" not in injected, "at_d should not be injected (it's user-facing)"


def test_extract_injected_args_identifies_item_for_filters():
    """Test that extract_injected_args identifies item as injected for filter operators."""

    def regular_func(item: str, param: int) -> str:
        return item

    # For filter operators, 'item' is injected
    injected = extract_injected_args(regular_func)

    # item IS injected for filter operators
    assert "item" in injected, f"'item' should be injected for filter operators, got {injected}"
    assert "param" not in injected, f"'param' should not be injected, got {injected}"


def test_patch_operator_parameters_keeps_at_d():
    """Test that patch_operator_parameters keeps at_d in schema."""
    tool = get_tool_for_function(demo_attr_with_at_d)
    parameters = tool.model_dump()["parameters"]

    # Patch parameters (as attribute)
    patched = patch_operator_parameters(parameters, keeps_item_parameter=True)

    # at_d should be KEPT in properties (it's user-facing)
    assert "at_d" in patched["properties"], "at_d should be kept in user-facing schema"

    # item should remain (it's an attribute)
    assert "item" in patched["properties"], "item should remain in attribute schema"


def test_patch_operator_parameters_keeps_at_d_for_operator():
    """Test that patch_operator_parameters keeps at_d in operator schema."""
    tool = get_tool_for_function(demo_filter_with_at_d)
    parameters = tool.model_dump()["parameters"]

    # Patch parameters (as operator - not attribute)
    patched = patch_operator_parameters(parameters, keeps_item_parameter=False)

    # For operators, at_d should be KEPT (it's a user-specified parameter)
    assert "at_d" in patched["properties"], "at_d should be kept in operator schema"
    assert "item" not in patched["properties"], "item should be removed from operator schema"

    # user parameter should remain
    assert "pattern" in patched["properties"], "pattern should remain in operator schema"


def test_patch_operator_parameters_removes_ctx():
    """Test that patch_operator_parameters removes ctx from schema."""
    tool = get_tool_for_function(demo_filter_withctx)
    parameters = tool.model_dump()["parameters"]

    # Patch parameters (as operator)
    patched = patch_operator_parameters(parameters, keeps_item_parameter=False)

    # ctx should be removed from properties (it's injected)
    assert "ctx" not in patched["properties"], "ctx should be removed from user-facing schema"
    assert "item" not in patched["properties"], "item should be removed from operator schema"


def test_convert_tool_to_metadata_builds_metadata():
    """Test that convert_tool_to_metadata builds metadata for a filter."""
    tool = get_tool_for_function(demo_filter_withctx)
    tool_dict = tool.model_dump()

    metadata = convert_tool_to_metadata(demo_filter_withctx, tool_dict, domain=None)

    assert metadata is not None, "Metadata should be created"


def test_user_facing_schema_excludes_injected():
    """Integration test: user-facing schema should exclude injected parameters.

    This is the main test that verifies the complete behavior:
    1. ctx is available to the function implementation
    2. ctx is NOT shown in user-facing parameter schema
    3. at_d IS shown in user-facing parameter schema (it's user-facing)
    """
    tool = get_tool_for_function(demo_filter_with_at_d)
    tool_dict = tool.model_dump()

    metadata = convert_tool_to_metadata(demo_filter_with_at_d, tool_dict, domain=None)

    # Get user-facing parameters
    user_params = metadata.parameters["properties"]

    # User-facing schema SHOULD include at_d (it's user-facing)
    assert "at_d" in user_params, f"User-facing schema should include 'at_d', got {list(user_params.keys())}"

    # User-facing schema SHOULD include pattern (user parameter)
    assert "pattern" in user_params, "User-facing schema should include 'pattern'"

    # User-facing schema should NOT include item (implicit for operators)
    assert "item" not in user_params, "User-facing schema should not include 'item'"
