"""Utility functions for argument binding and value conversion.

This module contains utility functions shared by multiple impl_ modules
for converting and validating argument values during tool binding.
"""

import inspect
from collections.abc import Callable
from typing import Any

from udan.core.api_constants import FRAMEWORK_PARAMS_ALL


def resolve_fn_args(
    fn: Callable,
    user_args: dict[str, Any],
    dep_param_names: set[str] | None = None,
    pre_resolved_deps: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve function arguments from user args and pre-resolved dependencies.

    Inspects the function signature and binds parameters from user_args,
    skipping framework params (ctx, item, etc.) and dependency params
    (resolved from pre_resolved_deps instead).
    Falls back to default values for unspecified parameters.

    Args:
        fn: Function whose parameters need resolution
        user_args: User-provided arguments
        dep_param_names: Parameter names that are dependencies (skip from user_args)
        pre_resolved_deps: Pre-resolved dependency values (param_name -> value)

    Returns:
        Complete args dictionary with all parameters resolved
    """
    sig = inspect.signature(fn)
    resolved_args: dict[str, Any] = {}
    _dep_param_names = dep_param_names or set()

    # Inject pre-resolved dependency values
    if pre_resolved_deps:
        resolved_args.update(pre_resolved_deps)

    for param_name, param in sig.parameters.items():
        # Skip framework parameters - they are injected by the wrapper
        if param_name in FRAMEWORK_PARAMS_ALL:
            continue
        if param_name in resolved_args:
            continue
        # User-provided value takes precedence (but not for dependency params)
        if param_name in user_args and param_name not in _dep_param_names:
            resolved_args[param_name] = user_args[param_name]
            continue
        # Use default value if available
        if param.default is not param.empty and param_name not in resolved_args:
            resolved_args[param_name] = param.default
        # Handle **kwargs (VAR_KEYWORD) - pass through all unused user_args
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            handled_keys = set(resolved_args.keys()) | _dep_param_names
            for key, value in user_args.items():
                if key not in handled_keys:
                    resolved_args[key] = value

    return resolved_args


def convert_boolean_string(value: str) -> bool | None:
    """Convert a string 'true'/'false' to boolean.

    Args:
        value: String value to convert

    Returns:
        True if 'true', False if 'false', None otherwise
    """
    value_lower = value.lower()
    if value_lower == "true":
        return True
    elif value_lower == "false":
        return False
    return None


def convert_string_value(arg_str: str, param_type: str | None) -> str | bool | int | float:
    """Convert a string argument value to the proper type based on parameter type.

    Args:
        arg_str: String argument value
        param_type: Parameter type (e.g., 'boolean', 'integer', 'number')

    Returns:
        Converted value (string, int, boolean, or float)

    Raises:
        ValueError: If conversion fails
    """
    if param_type in {"boolean", "bool"}:
        # Handle boolean values
        if arg_str.lower() in ("true", "1", "yes", "on"):
            return True
        elif arg_str.lower() in ("false", "0", "no", "off"):
            return False
        else:
            raise ValueError(f"Invalid boolean value: '{arg_str}'")
    elif param_type in {"integer", "int"}:
        # Handle integer values
        try:
            return int(arg_str)
        except ValueError:
            raise ValueError(f"Invalid integer value: '{arg_str}'")
    elif param_type in {"number", "float"}:
        # Handle float values
        try:
            return float(arg_str)
        except ValueError:
            raise ValueError(f"Invalid number value: '{arg_str}'")
    else:
        # Default to string
        return arg_str


def _accepts_scalar(param_def: dict) -> bool:
    """Check whether a parameter schema can hold a scalar (int/float/bool) value.

    Args:
        param_def: JSON schema property definition

    Returns:
        True when the parameter is scalar-typed or an anyOf containing a
        scalar member; False for string-only and container-typed parameters
    """
    if not param_def:
        return True  # no schema for this parameter: the contract is unknown
    if param_def.get("type") in ("integer", "number", "boolean", "any"):
        return True
    members = param_def.get("anyOf") or []
    return any(schema.get("type") in ("integer", "number", "boolean", "any") for schema in members)


def _convert_anyof(param_def: dict, name: str, value: str) -> object:
    """Convert a string value via an anyOf schema: first matching member wins.

    Args:
        param_def: JSON schema property definition with an anyOf member
        name: Parameter name (for error messages)
        value: String value to convert

    Returns:
        Converted value

    Raises:
        ValueError: When no member can take the value - silently passing the
            raw string through would hand the tool a wrong-typed
            argument (e.g. "2" for an int param, which then does string
            repetition)
    """
    for schema in param_def["anyOf"]:
        member_type = schema.get("type")
        if member_type is None:
            continue
        success, converted = _try_convert_string(member_type, value)
        if success:
            return converted
    member_types = [schema.get("type", "?") for schema in param_def["anyOf"]]
    raise ValueError(f"Expected argument with name={name} to be one of {member_types}, found: {value}")


def convert_value(props: dict, name: str, value: object) -> object:
    """Convert a value to the proper type based on schema.

    Args:
        props: Parameters schema properties
        name: Parameter name
        value: Value to convert (can be string or already converted)

    Returns:
        Converted value

    Raises:
        ValueError: If conversion fails
    """
    # Non-string values pass through (already converted, or non-scalar objects
    # like descriptor args) - except a scalar bound to a parameter
    # that cannot take one: e.g. a scalar landing on a `field: str` parameter
    # parameter is a binding mistake, not a value.
    if not isinstance(value, str):
        if isinstance(value, (int, float, bool)) and not _accepts_scalar(props.get(name, {})):
            raise ValueError(f"Expected argument with name={name} to be string, found: {value}")
        return value

    param_def = props.get(name, {})

    # anyOf (JSON Schema) - e.g., bool | None becomes anyOf[boolean, null],
    # bool | int becomes anyOf[boolean, integer]
    if "anyOf" in param_def:
        return _convert_anyof(param_def, name, value)

    # Handle type conversion from string
    if "type" not in param_def:
        return value

    param_type = param_def["type"]
    if param_type == "integer":
        try:
            return int(value)
        except ValueError:
            raise ValueError(f"Expected argument with name={name} is integer, found: {value}")
    if param_type == "boolean":
        # Convert string "true"/"false" to boolean
        converted = convert_boolean_string(value)
        if converted is not None:
            return converted
        raise ValueError(f"Expected argument with name={name} to be 'true' or 'false', found: {value}")
    if param_type in ("number", "float"):
        try:
            return float(value)
        except ValueError:
            raise ValueError(f"Expected argument with name={name} is number, found: {value}")
    # For "any" type, check if value is boolean string (from bool | None annotations)
    if param_type == "any":
        converted = convert_boolean_string(value)
        if converted is not None:
            return converted
    # Add more type conversions here as needed
    return value


def _try_convert_string(param_type: str, value: str) -> tuple[bool, object]:
    """Try to convert a string value for a single JSON schema type.

    Args:
        param_type: JSON schema type name
        value: String value to convert

    Returns:
        Tuple of (True, converted_value) on success, (False, None) if the
        value does not match the type
    """
    if param_type == "boolean":
        converted = convert_boolean_string(value)
        if converted is not None:
            return True, converted
        return False, None
    if param_type == "integer":
        try:
            return True, int(value)
        except ValueError:
            return False, None
    if param_type in ("number", "float"):
        try:
            return True, float(value)
        except ValueError:
            return False, None
    if param_type == "string":
        return True, value
    # "null" and unknown types cannot be produced from a bare string flag
    return False, None
