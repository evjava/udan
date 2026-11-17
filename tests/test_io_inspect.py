"""Tests for io_inspect module."""

import importlib
from inspect import Parameter

import pytest

from udan.core_tools_loading.api_annotated import annotated, get_annotated_functions
from udan.core_tools_loading.io_inspect import (
    _build_json_schema_type,
    _extract_parameters_schema,
    _get_tool_for_function_nodeps,
    get_tool_for_function,
)


@annotated
def get_numbers(
    n: int,
    lim: int = 3,
) -> list[str]:
    """
    descr
    """
    return [ii * n for ii in range(lim)]


@annotated
def insert_numbers() -> list[int]:
    return [0, 1, 2]


def test_get_tool_for_function_nodeps():
    """Test the local implementation."""
    tool = _get_tool_for_function_nodeps(get_numbers, injectable_types=set())
    assert tool.name == "get_numbers"
    assert tool.parameters["properties"]["n"]["type"] == "integer"
    assert tool.parameters["properties"]["lim"]["type"] == "integer"
    assert "lim" not in tool.parameters.get("required", [])


def test_get_tool_for_function_empty_params():
    """Test that functions with no parameters work correctly."""
    tool = get_tool_for_function(insert_numbers, injectable_types=set())
    assert tool.name == "insert_numbers"
    assert tool.parameters["type"] == "object"
    assert tool.parameters["properties"] == {}


def test_get_tool_for_function_nodeps_empty_params():
    """Test that functions with no parameters work correctly with nodeps."""
    tool = _get_tool_for_function_nodeps(insert_numbers, injectable_types=set())
    assert tool.name == "insert_numbers"
    assert tool.parameters["type"] == "object"
    assert tool.parameters["properties"] == {}


@pytest.mark.parametrize(
    "py_type,expected_json_type",
    [
        (str, "string"),
        (int, "integer"),
        (float, "number"),
        (bool, "boolean"),
        (list, "array"),
        (dict, "object"),
    ],
)
def test_build_json_schema_type_basic_types(py_type, expected_json_type):
    """Test JSON schema type mapping for basic Python types."""

    param = Parameter("test", Parameter.POSITIONAL_OR_KEYWORD, annotation=py_type)
    schema = _build_json_schema_type(py_type, param)
    assert schema["type"] == expected_json_type


def test_optional_parameter_handling():
    """Test that optional parameters (with defaults) are not marked as required."""

    @annotated
    def func_with_optional(a: int, b: str = "default") -> None:
        pass

    schema = _extract_parameters_schema(func_with_optional, injectable_types=set())
    assert schema["required"] == ["a"]
    assert "b" in schema["properties"]


# List of udan modules to test for tool extraction
UDAN_MODULES_TO_TEST = [
    "udan.plugins_tools_examples.plugins_builtins",
    "udan.plugins_tools_examples.plugins_builtins_set_operations",
    "udan.plugins_tools_examples.plugins_dot",
    "udan.plugins_tools_examples.plugins_fs",
    "udan.plugins_tools_examples.plugins_markdown",
    "udan.plugins_tools_examples.plugins_org",
    "udan.plugins_tools_examples.plugins_peval",
    "udan.plugins_tools_examples.plugins_csv",
    "udan.plugins_tools_examples.plugins_shell",
    "udan.plugins_tools_examples.plugins_web",
]


def test_union_parameter_handling():
    """Test JSON schema generation for union types (non-Optional and Optional)."""

    param = Parameter("test", Parameter.POSITIONAL_OR_KEYWORD)

    # Non-Optional union: bool | int
    schema = _build_json_schema_type(bool | int, param)
    assert schema == {"anyOf": [{"type": "boolean"}, {"type": "integer"}]}

    # Optional single type: str | None
    schema = _build_json_schema_type(str | None, param)
    assert schema == {"anyOf": [{"type": "string"}, {"type": "null"}]}

    # Optional multi-type union: str | int | None
    schema = _build_json_schema_type(str | int | None, param)
    assert schema == {"anyOf": [{"type": "string"}, {"type": "integer"}, {"type": "null"}]}


@pytest.mark.parametrize("module_name", UDAN_MODULES_TO_TEST)
def test_all_modules_tool_extraction(module_name):
    """Test that get_tool_for_function works for all annotated functions of udan modules.

    The extraction is the one any plugin load performs: the metadata feeds
    the registry, and the consumers of that registry read these functions as
    its tools. A function whose metadata cannot be extracted fails here, per
    module, with the function name.
    """

    module = importlib.import_module(module_name)
    annotated_functions = get_annotated_functions(module)

    failures = []
    for fn in annotated_functions:
        try:
            tool = get_tool_for_function(fn)
            assert tool is not None
            assert tool.name
            assert tool.parameters is not None
        except AssertionError as e:
            failures.append((fn.__name__, str(e)))
        except Exception as e:
            failures.append((fn.__name__, f"Unexpected error: {e}"))

    if failures:
        failure_msg = f"\n{module_name}:\n"
        for fn_name, error in failures:
            failure_msg += f"  - {fn_name}: {error}\n"
        pytest.fail(failure_msg)
