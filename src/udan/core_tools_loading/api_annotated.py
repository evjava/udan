"""Annotated decorator for Udan tools.

This module provides decorators used to annotate tools and dependency providers.
"""

from collections.abc import Callable
from functools import wraps
from types import ModuleType
from typing import Any, get_type_hints


def annotated(*annot_args: Any, **annotated_kwargs: Any) -> Any:
    """Decorator to annotate tools with metadata.

    This decorator attaches metadata to functions that can be used by
    the tool loading system.

    Args:
        *annot_args: If a single callable is passed, decorates it directly
        **annotated_kwargs: Metadata to attach to the function

    Returns:
        Decorated function with metadata attached

    Raises:
        ValueError: If positional arguments are passed (not supported)
    """
    if annot_args and len(annot_args) == 1 and not annotated_kwargs:
        fn = annot_args[0]
        if callable(fn):
            return annotated()(fn)
    # todo support `@annotated`
    if annot_args:
        raise ValueError(f"Not supported passing args: {annot_args}")

    def wrapper(fn: Callable) -> Callable:
        @wraps(fn)
        def fix_fn(*args: Any, **kwargs: Any) -> Any:
            return fn(*args, **kwargs)

        # Preserve type hints from the original function
        # This is needed for dependency injection to work with auto-injected parameters
        try:
            fix_fn.__annotations__ = fn.__annotations__
        except AttributeError, TypeError:
            pass

        setattr(fix_fn, "_annotated", True)
        setattr(fix_fn, "_annotated_kwargs", annotated_kwargs)
        return fix_fn

    return wrapper


def get_annotated_functions(module: ModuleType) -> list[Callable]:
    """Extract all annotated functions defined in a module.

    Annotated functions are callables that have the `_annotated` attribute
    set to True, which is applied by the `@annotated` decorator.
    Only functions whose __module__ matches the given module are included,
    to avoid re-registering functions imported from other modules.

    Args:
        module: Python module to extract functions from

    Returns:
        List of callable functions that are annotated and defined in this module
    """
    module_name = module.__name__
    return [
        attr_val
        for attr_val in module.__dict__.values()
        if callable(attr_val)
        and getattr(attr_val, "_annotated", False) is True
        and getattr(attr_val, "__module__", None) == module_name
    ]


# ============ Dependency Provider Decorator ============


def annotated_dependency(
    fn: Callable | None = None,
    *,
    plugins_only: bool = False,
) -> Any:
    """Decorator to mark functions as dependency providers.

    Everything is inferred from the function signature:
    - What it provides: the return type annotation
    - What it needs: the parameter types

    Args:
        fn: Function to decorate (if used without arguments)
        plugins_only: If True, this provider works in the plugins mechanism only (the
            CLI flow); hosting processes that resolve dependencies on their own skip it.
            Default: False (works everywhere)

    Examples:
        # Simple: works everywhere
        @annotated_dependency
        def provide_workspace_root() -> WorkspaceRoot:
            return WorkspaceRoot(Path.cwd())

        # CLI-only: terminal input is not available to a hosting process
        @annotated_dependency(plugins_only=True)
        def get_user_prompt() -> UserPrompt:
            return UserPrompt(input("Enter value: "))

        # With dependencies: inferred from parameter names/types
        @annotated_dependency
        def provide_query_history(config: UdanConfig) -> QueryHistory:
            return QueryHistory(config.udan_history_path)
    """

    def decorator(f: Callable) -> Callable:
        # Validate return type annotation
        hints = get_type_hints(f)
        if "return" not in hints:
            fn_name = get_function_name(f)
            raise ValueError(f"@annotated_dependency function '{fn_name}' must have a return type annotation")

        @wraps(f)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return f(*args, **kwargs)

        # Preserve type hints
        wrapper.__annotations__ = f.__annotations__

        # Mark as dependency provider
        setattr(wrapper, "_dependency", True)
        setattr(wrapper, "_dependency_plugins_only", plugins_only)
        setattr(
            wrapper,
            "_dependency_kwargs",
            {
                "provides": hints["return"],
                "plugins_only": plugins_only,
            },
        )

        return wrapper

    # Support both @annotated_dependency and @annotated_dependency()
    if fn is None:
        # Called with arguments: @annotated_dependency(plugins_only=True)
        return decorator
    else:
        # Called without arguments: @annotated_dependency
        return decorator(fn)


def get_dependency_providers(module) -> list[Callable]:
    """Extract all dependency providers from a module.

    Returns:
        List of callable functions with _dependency=True
    """
    return [
        attr_val
        for attr_val in module.__dict__.values()
        if callable(attr_val) and getattr(attr_val, "_dependency", False) is True
    ]


def is_plugins_only(provider: Callable) -> bool:
    """Check if a provider only works in plugins mechanism (CLI mode).

    Args:
        provider: Provider function to check

    Returns:
        True if provider has plugins_only=True
    """
    return getattr(provider, "_dependency_plugins_only", False)


def get_annotated_kwargs(fn: Callable) -> dict:
    """Get the kwargs from @annotated decorator.

    Args:
        fn: Function to get kwargs from

    Returns:
        Dict of kwargs passed to @annotated decorator, empty dict if not annotated
    """
    return getattr(fn, "_annotated_kwargs", {})


def is_annotated(fn: Callable) -> bool:
    """Check if function has @annotated decorator.

    Args:
        fn: Function to check

    Returns:
        True if function has @annotated decorator
    """
    return getattr(fn, "_annotated", False) is True


# ============ Function Unwrapping Utilities ============


def unwrap_function(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Unwrap a function to get its original implementation.

    The @annotated decorator wraps functions, setting __wrapped__ to point
    to the original function. This utility follows the __wrapped__ chain to
    get the original unwrapped function.

    Args:
        fn: Function to unwrap

    Returns:
        The original unwrapped function

    Examples:
        >>> original = unwrap_function(decorated_fn)
        >>> inspect.signature(original)  # Get original signature
    """
    actual_fn = fn
    while hasattr(actual_fn, "__wrapped__"):
        actual_fn = actual_fn.__wrapped__
    # The unwrapped function should always be callable (Python's functools.wraps guarantees this)
    assert callable(actual_fn), f"Expected callable after unwrapping, got {type(actual_fn).__name__}"
    return actual_fn


def get_module_domain(module) -> str | None:
    """Get the domain from a module.

    Modules can optionally define a `DOMAIN` attribute to specify their domain.
    This is used by the plugin and hosting systems to categorize plugins.

    Args:
        module: Python module to check

    Returns:
        Domain string, or None if not defined

    Examples:
        >>> import my_plugin
        >>> domain = get_module_domain(my_plugin)
        >>> if domain:
        ...     print(f"Plugin domain: {domain}")
    """
    return getattr(module, "DOMAIN", None)


def get_function_name(fn: Callable) -> str:
    """Get the name of a function.

    Most callables have `__name__`, but some (like partial functions,
    certain callables, or mock objects) might not. This provides a safe
    way to get a function name with a sensible fallback.

    Args:
        fn: Function or callable to get the name from

    Returns:
        Function name, or "<unknown>" if not available

    Examples:
        >>> get_function_name(my_func)
        'my_func'
        >>> get_function_name(lambda x: x)
        '<lambda>'
        >>> get_function_name(partial(int, base=16))
        '<unknown>'
    """
    return getattr(fn, "__name__", "<unknown>")
