"""Tool metadata extraction for tools.

This module extracts tool metadata from annotated functions directly, which keeps
loading fast and the metadata generation under udan's control.
"""

from importlib import import_module
from inspect import Parameter, signature
from typing import Annotated, Any, Union, get_args, get_origin, get_type_hints

from udan.core_tools_loading.api_annotated import get_annotated_kwargs, get_dependency_providers, is_annotated
from udan.core_tools_loading.api_tools import ToolMetadata

# Default set of injectable types (empty by default)
# Dependencies should be defined explicitly via @annotated_dependency
# and set via _set_injectable_types() or set_injectable_types_from_modules()
_DEFAULT_INJECTABLE_TYPES: set[type] = set()


def extract_injectable_types_from_modules(module_names: list[str]) -> set[type]:
    """Extract injectable types from @annotated_dependency providers in modules.

    This function scans the specified modules for functions decorated with
    @annotated_dependency and returns the set of types they provide.

    Args:
        module_names: List of module names to scan for providers

    Returns:
        Set of types that can be injected
    """
    injectable_types: set[type] = set()

    for module_name in module_names:
        try:
            module = import_module(module_name)
            for provider in get_dependency_providers(module):
                hints = get_type_hints(provider)
                return_type = hints.get("return")
                if return_type:
                    injectable_types.add(return_type)
        except ImportError:
            # Module not found, skip it
            pass

    return injectable_types


def get_tool_for_function(fn, injectable_types: set[type] | None = None) -> ToolMetadata:
    """Get tool metadata for a function.

    This is the main entry point for tool metadata extraction.

    Args:
        fn: Annotated function to extract tool metadata from
        injectable_types: Set of types that should be considered injectable
            and excluded from the schema. If None, uses _DEFAULT_INJECTABLE_TYPES.

    Returns:
        Tool metadata for the function
    """
    if injectable_types is None:
        injectable_types = _DEFAULT_INJECTABLE_TYPES

    return _get_tool_for_function_nodeps(fn, injectable_types)


def _is_param_injected(param_type: type, injectable_types: set[type]) -> bool:
    """Check if a parameter should be injected (excluded from schema).

    Args:
        param_type: Parameter type annotation
        injectable_types: Set of types that should be considered injectable

    Returns:
        True if parameter should be injected and excluded from schema
    """
    # Check if this type is in the injectable set
    if param_type in injectable_types:
        return True

    # Check for Union types that might contain injectable types
    if get_origin(param_type) is Union:
        union_args = get_args(param_type)
        for arg in union_args:
            if arg in injectable_types:
                return True

    return False


def _get_tool_for_function_nodeps(fn, injectable_types: set[type]) -> ToolMetadata:
    """Get tool metadata from the function itself.

    This implementation extracts tool metadata directly from the function's
    annotations and metadata, without a third-party tool library.

    Args:
        fn: Annotated function to extract tool metadata from
        injectable_types: Set of types that should be considered injectable

    Returns:
        Tool metadata for the function
    """
    if not is_annotated(fn):
        raise ValueError(f"Function {fn.__name__} is not annotated")
    annotated_kwargs = get_annotated_kwargs(fn)

    # Extract basic metadata
    name = annotated_kwargs.get("name", fn.__name__)
    description = annotated_kwargs.get("description", fn.__doc__ or "")
    tags = list(annotated_kwargs.get("tags", []))
    meta = dict(annotated_kwargs.get("meta", {}))

    # Extract parameters from function signature
    parameters = _extract_parameters_schema(fn, injectable_types)

    # Output schema - the local extraction does not infer one
    output_schema: dict[str, Any] = {}

    return ToolMetadata(
        name=name,
        description=description,
        tags=tags,
        meta=meta,
        parameters=parameters,
        output_schema=output_schema,
        fn_path=f"{fn.__module__}.{fn.__name__}",
    )


def _extract_parameters_schema(fn, injectable_types: set[type]) -> dict[str, Any]:
    """Extract JSON schema for function parameters.

    This analyzes the function signature and type hints to build
    a JSON schema for the tool's parameters.

    Injectable parameters (from injectable_types) are automatically
    excluded from the schema.

    Args:
        fn: Function to extract parameters from
        injectable_types: Set of types that should be considered injectable

    Returns:
        JSON schema dict for parameters
    """
    sig = signature(fn)
    hints = get_type_hints(fn)

    properties: dict[str, dict[str, Any]] = {}
    required: list[str] = []

    for param_name, param in sig.parameters.items():
        # Skip 'self' parameter for methods
        if param_name == "self":
            continue

        # Get parameter type - use hints for resolved types, param.annotation for Annotated
        param_type = hints.get(param_name, param.annotation)

        # Skip injected parameters
        if _is_param_injected(param_type, injectable_types):
            continue

        # Use param.annotation directly to preserve Annotated metadata
        # get_type_hints() strips the Annotated wrapper
        param_type_raw = param.annotation

        # Build parameter schema
        param_schema = _build_json_schema_type(param_type_raw, param)

        # Add default value if present
        if param.default != Parameter.empty:
            param_schema["default"] = param.default

        # Note: Don't add description if empty

        properties[param_name] = param_schema

        # Track required parameters
        if param.default == Parameter.empty:
            required.append(param_name)

    # Build the full parameters schema
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }

    if required:
        parameters_schema["required"] = required

    return parameters_schema


def _build_json_schema_type(py_type, param: Parameter) -> dict[str, Any]:
    """Build JSON schema type definition from Python type annotation.

    Args:
        py_type: Python type annotation
        param: inspect.Parameter object

    Returns:
        JSON schema type definition
    """

    # Handle Annotated types - extract metadata and base type
    if get_origin(py_type) is Annotated:
        args = get_args(py_type)
        if args:
            base_type = args[0]
            metadata = args[1:] if len(args) > 1 else []
            # Build schema for base type
            schema = _build_json_schema_type(base_type, param)
            # Add metadata as description if it's a string
            for meta in metadata:
                if isinstance(meta, str):
                    schema["description"] = meta
            return schema

    # Handle None type (unannotated parameters)
    if py_type == Parameter.empty:
        return {"type": "string"}

    # Handle basic types
    type_mapping: dict[type, dict[str, Any]] = {
        str: {"type": "string"},
        int: {"type": "integer"},
        float: {"type": "number"},
        bool: {"type": "boolean"},
        list: {"type": "array", "items": {"type": "string"}},
        dict: {"type": "object"},
    }

    if py_type in type_mapping:
        return dict(type_mapping[py_type])

    # Handle generic types like list[str], dict[str, int] BEFORE union types
    # This is important because Annotated[list[int] | None, "vararg"] should
    # extract the list[int] part first before handling the union
    origin = get_origin(py_type)
    if origin is not None:
        if origin is list:
            args = get_args(py_type)
            item_type = args[0] if args else str
            item_schema = _build_json_schema_type(item_type, param)
            return {"type": "array", "items": item_schema}
        elif origin is dict:
            return {"type": "object"}

    # Handle union types (X | Y, including Optional X | None)
    if hasattr(py_type, "__or__") or hasattr(py_type, "__args__"):
        if hasattr(py_type, "__args__"):
            args = py_type.__args__
            member_schemas: list[dict[str, Any]] = []
            for arg_type in args:
                if arg_type is type(None):
                    member_schemas.append({"type": "null"})
                else:
                    member_schemas.append(_build_json_schema_type(arg_type, param))
            if member_schemas:
                return {"anyOf": member_schemas}

    # Default: treat as string
    return {"type": "string"}
