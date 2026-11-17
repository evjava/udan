"""The generic injector: classify, refine, resolve, wrap.

A function declares what it needs by annotation; the injector hides those
parameters from the signature the tool descriptors read and answers them at call
time. What counts as injectable and what answers it are supplied, not guessed: a
set of globals, the per-query overrides set_dependency writes, and
DependencySource objects in list order - the first answer that is not MISSING
wins, and a parameter nothing answers keeps its declared default or raises.

The one convention the module carries is a name, not an object: context_param
names the argument of a call that the engine always offers (udan's query
context). It is forwarded when the target declares the parameter and dropped
when it does not; it is never injected, never classified and never shown to a
source.

The contract - MISSING, DependencySource, FunctionInjectorAPI - is
api_function_injector beside this module. The udan half - the sources over the
dependency registry and the per-query context key - is composed in udan's
container (impl_ioc).
"""

import inspect
from collections.abc import Callable, Sequence
from typing import Any, Self, Union, get_args, get_origin, get_type_hints

from udan.core_tools_loading.api_annotated import get_annotated_kwargs
from udan.core_tools_loading.api_function_injector import MISSING, DependencySource, FunctionInjectorAPI

# Marker set on functions already wrapped by FunctionInjector.wrap_function, so a
# second wrap attempt can be skipped: a wrapper re-wraps to a function whose
# annotations no longer declare the injected params, and its signature has no
# context param, so the outer wrapper drops it instead of forwarding it and the
# inner one cannot resolve deps.
_INJECTOR_WRAPPED = "_injector_wrapped"


def _injectable_member(param_type: type, keys: set[type]) -> type | None:
    """The type a key set answers for this annotation, None when it answers nothing.

    A plain annotation answers by itself; a union answers by its first member a
    key covers (`X | None` included - the None member is skipped).

    Args:
        param_type: The annotation to classify.
        keys: The types that count as injected.

    Returns:
        The injectable type, or None when no key covers the annotation.
    """
    if param_type in keys:
        return param_type
    if get_origin(param_type) is Union:
        for arg in get_args(param_type):
            if arg is not type(None) and arg in keys:
                return arg
    return None


def _classify_injected_params(hints: dict[str, type], keys: set[type]) -> dict[str, type]:
    """Classify a function's parameters by the key set.

    Args:
        hints: Type hints for the function (from get_type_hints).
        keys: The types that count as injected.

    Returns:
        Dictionary mapping parameter names to their injectable types.
    """
    injected_params: dict[str, type] = {}
    for param_name, param_type in hints.items():
        if param_name == "return":
            continue
        injected_type = _injectable_member(param_type, keys)
        if injected_type is not None:
            injected_params[param_name] = injected_type
    return injected_params


def _create_refined_signature(fn: Callable[..., Any], injected_params: dict[str, type]) -> inspect.Signature:
    """Create refined signature excluding injected parameters.

    This is crucial for pydantic-based tool descriptors - they should only see user-facing parameters.

    Args:
        fn: The original function.
        injected_params: Parameters that will be injected.

    Returns:
        A Signature object with injected parameters removed.
    """
    sig = inspect.signature(fn)
    refined_params = [param for param_name, param in sig.parameters.items() if param_name not in injected_params]
    return sig.replace(parameters=refined_params)


def _create_refined_annotations(fn: Callable[..., Any], injected_params: dict[str, type]) -> dict[str, type]:
    """Create refined annotations excluding injected parameters.

    Args:
        fn: The original function.
        injected_params: Parameters that will be injected.

    Returns:
        A dictionary of annotations with injected parameters removed.
    """
    refined_annotations = {}
    for param_name, param_type in fn.__annotations__.items():
        if param_name != "return" and param_name not in injected_params:
            refined_annotations[param_name] = param_type
    if "return" in fn.__annotations__:
        refined_annotations["return"] = fn.__annotations__["return"]
    return refined_annotations


def _copy_function_metadata(
    wrapped: Any,  # Function object that will have attributes set
    fn: Callable[..., Any],
    refined_sig: inspect.Signature,
    refined_annotations: dict[str, type],
) -> Any:  # Returns the wrapped function (same object)
    """Copy all metadata from original function to wrapper.

    This is critical for pydantic-based tool descriptor compatibility.

    Args:
        wrapped: The wrapper function to update.
        fn: The original function to copy from.
        refined_sig: The refined signature (without injected params).
        refined_annotations: The refined annotations.

    Returns:
        The wrapped function with all metadata copied.
    """
    # Preserve the original function's metadata
    wrapped.__name__ = fn.__name__
    wrapped.__doc__ = fn.__doc__
    wrapped.__module__ = fn.__module__
    wrapped.__wrapped__ = fn  # type: ignore[attr-defined]
    # IMPORTANT: Use the refined signature that excludes injected parameters
    # This is crucial for pydantic-based tool descriptors - they should only see user-facing parameters
    wrapped.__signature__ = refined_sig  # type: ignore[attr-defined]
    wrapped.__annotations__ = refined_annotations  # type: ignore[attr-defined]
    # IMPORTANT: Add API types from original function's __globals__ to wrapped function's __globals__
    # This ensures type annotations can be resolved by pydantic. "ends with API" is the
    # udan naming convention for the contracts a function may annotate with, kept
    # until the consumer that resolves those names is identified - the names are not
    # derivable from the refined annotations alone, because 11 of 43 plugin modules use
    # `from __future__ import annotations` and theirs are strings.
    for key, value in fn.__globals__.items():
        if key.endswith("API") and key not in wrapped.__globals__:
            try:
                if isinstance(value, type):
                    wrapped.__globals__[key] = value  # type: ignore[index]
            except TypeError, AttributeError:
                pass

    # Copy all attributes from original function to wrapper (for pydantic)
    for attr_name in dir(fn):
        if not attr_name.startswith("__") and attr_name != "__wrapped__":
            try:
                setattr(wrapped, attr_name, getattr(fn, attr_name))
            except AttributeError, TypeError:
                pass

    # Copy over the _annotated_kwargs if present (for udan tool registration)
    annotated_kwargs = get_annotated_kwargs(fn)
    if annotated_kwargs:
        wrapped._annotated_kwargs = annotated_kwargs  # type: ignore[attr-defined]

    return wrapped


class FunctionInjector(FunctionInjectorAPI):
    """Injects a function's annotated parameters from the globals, the overrides and the sources.

    Args:
        dependencies: Dictionary mapping types to their singleton instances, the globals.
        sources: The resolution layers after the overrides, in order.
        context_param: Name of the call argument the engine always offers (udan's
            "ctx"). Forwarded when the target declares the parameter, dropped when
            it does not; never injected, never classified. None for a host without
            the convention.

    Note:
        A key that enters after a function was wrapped is not retroactive: the
        key set is read when the function is wrapped, and a dependency a host
        adds later (a source that starts answering a type, or a set_dependency
        for a type nothing declared) needs the type among the keys at wrap time
        - declare it in a source.
    """

    def __init__(
        self,
        dependencies: dict[type, Any],
        sources: Sequence[DependencySource] = (),
        context_param: str | None = None,
    ) -> None:
        self._dependencies = dependencies
        self._sources = list(sources)
        self._context_param = context_param
        # Overrides set_dependency writes; a query-scoped dependency (udan's chain
        # context) is served here, and the globals still win over it
        self._query_dependencies: dict[type, Any] = {}

    def wrap_function(self, fn: Callable[..., Any]) -> Any:
        """Wrap a function to automatically inject its dependencies.

        Args:
            fn: The function to wrap.

        Returns:
            Wrapped function that handles dependency injection. Calling it hands
            the resolved instances to the annotated parameters and everything
            else through.

        Example:
            >>> injector = FunctionInjector(dependencies={LoggerAPI: logger})
            >>> wrapped = injector.wrap_function(my_function)
            >>> wrapped(user_arg)
        """
        # Already wrapped: injected params are resolved by the existing wrapper
        if getattr(fn, _INJECTOR_WRAPPED, False):
            return fn

        # The key set is read per wrap, not kept from construction: a source's
        # keys() is a live accessor (the udan dependency registry is populated by
        # the host after the injector is built), and the wrap is when the
        # classification is asked for. From here on the wrapper is frozen.
        keys = set(self._dependencies)
        for source in self._sources:
            keys |= source.keys()

        hints = get_type_hints(fn)
        injected_params = _classify_injected_params(hints, keys)

        refined_sig = _create_refined_signature(fn, injected_params)
        refined_annotations = _create_refined_annotations(fn, injected_params)

        # Store original signature for positional argument checking
        original_sig = inspect.signature(fn)
        sig_param_names = list(original_sig.parameters.keys())

        # Store reference to self for use in closure
        injector = self
        context_param = self._context_param

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            # Inject all dependencies
            injected_kwargs = {}
            for param_name, injected_type in injected_params.items():
                # Skip injection if parameter was passed as positional argument
                # This handles cases where call sites pass dependencies positionally
                # (e.g., legacy code passing ctx, or code passing registry positionally)
                if param_name in sig_param_names:
                    param_index = sig_param_names.index(param_name)
                    # If enough positional args were provided, parameter was passed positionally
                    if len(args) > param_index:
                        continue  # Skip injection, already provided as positional arg

                # Only inject if not already provided in kwargs (or if value is None)
                # A host may pass context=None, so we need to check the actual value
                should_inject = param_name not in kwargs or kwargs.get(param_name) is None
                if should_inject:
                    try:
                        # get_dependency resolves from the globals, the overrides and the sources
                        dep = injector.get_dependency(injected_type)
                        injected_kwargs[param_name] = dep
                    except RuntimeError:
                        # If injection fails and value was provided (even if None), keep the original
                        if param_name not in kwargs:
                            parameter = original_sig.parameters.get(param_name)
                            if parameter is None or parameter.default is parameter.empty:
                                raise
                            # Nothing provides the dependency - a service a host left
                            # out: the declared default stands, the function runs
                            # degraded

            # Forward the engine's argument only to a function that declares it:
            # applicators hand it to every tool they run, declared or not
            filtered_kwargs = dict(kwargs)
            if context_param is not None and context_param in kwargs and context_param not in sig_param_names:
                filtered_kwargs.pop(context_param, None)

            merged_kwargs = {**filtered_kwargs, **injected_kwargs}

            # Call original function with injected dependencies
            return fn(*args, **merged_kwargs)

        # Copy metadata to make wrapper look like original function
        wrapped = _copy_function_metadata(wrapped, fn, refined_sig, refined_annotations)
        wrapped._injector_wrapped = True  # type: ignore[attr-defined]
        return wrapped

    def set_dependency(self, dep_type: type, instance: Any) -> None:
        """Set a query-specific dependency, the override a per-query object is served under.

        Args:
            dep_type: The dependency type.
            instance: The dependency instance.
        """
        self._query_dependencies[dep_type] = instance

    def with_global_dependency(self, dep_type: type, instance: Any) -> Self:
        """The injector with one more global dependency; see FunctionInjectorAPI.

        Args:
            dep_type: The dependency type the instance is resolved by.
            instance: The dependency instance.

        Returns:
            A new injector of the same kind over the extended globals with the
            same sources and context parameter.
        """
        return type(self)(
            dependencies={**self._dependencies, dep_type: instance},
            sources=self._sources,
            context_param=self._context_param,
        )

    @property
    def dependencies(self) -> dict[type, Any]:
        """Get the global dependencies dictionary."""
        return self._dependencies

    def get_dependency(self, expected_type: type) -> Any:
        """Resolve a dependency; see FunctionInjectorAPI.

        Args:
            expected_type: The type of dependency to resolve.

        Returns:
            The resolved dependency instance.

        Raises:
            RuntimeError: If nothing answers the type.
        """
        return self._resolve(expected_type)

    def _resolve(self, expected_type: type) -> Any:
        """Resolve a dependency from the globals, the overrides and the sources, in that order."""
        if expected_type in self._dependencies:
            return self._dependencies[expected_type]

        if expected_type in self._query_dependencies:
            return self._query_dependencies[expected_type]

        for source in self._sources:
            answer = source.get(expected_type)
            if answer is not MISSING:
                return answer

        raise RuntimeError(
            f"Could not inject dependency of type {expected_type.__name__}. "
            f"Ensure an @annotated_dependency provider exists or the injector holds it as a dependency."
        )
