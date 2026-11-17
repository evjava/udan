"""The injector contract: what counts as injected, and what answers it.

A DependencySource declares the types it answers for (keys) and answers them at
call time (get), returning MISSING when the dependency is not its to answer - a
sentinel rather than None, because None is a legitimate answer.
FunctionInjectorAPI is the contract an injector serves and the key a container
resolves it under; the implementation is FunctionInjector in
udan.core_tools_loading.impl_function_injector.
"""

from collections.abc import Callable
from typing import Any, Final, Protocol, Self


class _Missing:
    """The answer "not mine": a source that does not hold the dependency says so with this.

    A sentinel rather than None because None is a legitimate answer - every
    `X | None = None` dependency resolves to it.
    """

    __slots__ = ()

    def __repr__(self) -> str:
        return "<MISSING>"


MISSING: Final = _Missing()


class DependencySource(Protocol):
    """A resolution layer: what it declares counts as injected, what it answers is used."""

    def keys(self) -> set[type]:
        """The types that count as injected; a parameter annotated with one stays out of the refined signature."""
        ...

    def get(self, dep_type: type) -> Any:
        """The instance for dep_type, or MISSING when this source does not answer it."""
        ...


class FunctionInjectorAPI:
    """The injector contract: wrap a function, set a per-query dependency, extend the globals."""

    def wrap_function(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        """Wrap a function to automatically inject its dependencies.

        Args:
            fn: The function to wrap.

        Returns:
            Wrapped function that handles dependency injection.
        """
        raise NotImplementedError

    def set_dependency(self, dep_type: type, instance: Any) -> None:
        """Set a query-specific dependency, the override a per-query object is served under.

        Args:
            dep_type: The dependency type.
            instance: The dependency instance.
        """
        raise NotImplementedError

    def with_global_dependency(self, dep_type: type, instance: Any) -> Self:
        """The injector with one more global dependency; the extension a plugin's decoration performs.

        Args:
            dep_type: The dependency type the instance is resolved by.
            instance: The dependency instance.

        Returns:
            An injector of the same kind over the extended globals; a host whose
            constructor takes more overrides this to build itself.
        """
        raise NotImplementedError

    def get_dependency(self, expected_type: type) -> Any:
        """Resolve a dependency: the globals, then the per-query overrides, then the sources.

        Args:
            expected_type: The type of dependency to resolve.

        Returns:
            The resolved dependency instance.

        Raises:
            RuntimeError: If nothing answers the type.
        """
        raise NotImplementedError

    @property
    def dependencies(self) -> dict[type, Any]:
        """Get the global dependencies dictionary."""
        raise NotImplementedError
