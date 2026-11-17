"""Public API for dependency provider registry.

This module defines the public API interface for registering and resolving
dependency providers.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from udan.core.api_exec_context import ExecContextAPI


class DependenciesRegistryAPI:
    """API interface for dependency provider registry.

    This class defines the public API for registering and resolving dependency providers.
    Dependency providers are functions decorated with @annotated_dependency that return
    instances of types that can be injected into tool functions.

    The registry handles:
    - Registration of providers from modules
    - Provider dependency resolution (with circular dependency detection)
    - Singleton caching of resolved dependencies
    - Separation between the providers a hosting process may resolve and the plugins_only ones
    """

    def register_from_module(self, module_name: str) -> None:
        """Register all dependency providers from a module.

        Args:
            module_name: Python module name (e.g., "udan.core.impl_dependencies_registry")
        """
        raise NotImplementedError

    def has_provider(self, dep_type: type) -> bool:
        """Check if a dependency type has a registered provider.

        Args:
            dep_type: The dependency type to check

        Returns:
            True if a provider is registered for this type
        """
        raise NotImplementedError

    def provided_types(self) -> set[type]:
        """The types the registered providers answer.

        Returns:
            Set of the provider keys registered so far
        """
        raise NotImplementedError

    def get_shared_providers(self) -> dict[type, Callable]:
        """Get the providers resolvable outside the CLI flow.

        The plugins_only providers - the ones that need the CLI - stay out.

        Returns:
            Dict of type -> provider, excluding plugins_only providers
        """
        raise NotImplementedError

    def resolve(
        self,
        dep_type: type,
        context: dict[type, Any] | None = None,
        ctx: ExecContextAPI | None = None,
    ) -> Any:
        """Resolve a dependency by calling its provider.

        Args:
            dep_type: The dependency type to resolve
            context: Optional context with already-resolved dependencies
            ctx: Optional ExecContextAPI for injecting ExecContextAPI dependencies

        Returns:
            The resolved dependency value

        Raises:
            ValueError: If provider not found or circular dependency detected
        """
        raise NotImplementedError
