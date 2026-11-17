"""Dependency provider registry and resolution."""

import importlib
from collections import defaultdict
from collections.abc import Callable
from typing import Any, get_type_hints

from udan.core.api_dependencies_registry import DependenciesRegistryAPI
from udan.core.api_exec_context import ExecContextAPI
from udan.core_tools_loading.api_annotated import get_dependency_providers, is_plugins_only


class DependenciesRegistry(DependenciesRegistryAPI):
    """Registry for dependency providers.

    This is the implementation of DependenciesRegistryAPI.
    The API documentation is in the DependenciesRegistryAPI class in api.py.
    """

    def __init__(self):
        self._providers: dict[type, Callable] = {}  # Type -> provider function
        self._plugins_only: set[type] = set()  # Types that are CLI-only
        self._dependencies: dict[type, list[type]] = defaultdict(list)  # Type -> [what it needs]
        self._resolved: dict[type, Any] = {}  # Type -> resolved value (singletons)

    def register_from_module(self, module_name: str) -> None:
        """Register all dependency providers from a module."""
        module = importlib.import_module(module_name)

        for provider in get_dependency_providers(module):
            hints = get_type_hints(provider)
            return_type = hints.get("return")

            if not return_type:
                continue

            self._providers[return_type] = provider

            # Track plugins_only
            if is_plugins_only(provider):
                self._plugins_only.add(return_type)

            # Track dependencies from parameters
            for param_name, param_type in hints.items():
                if param_name != "return":
                    self._dependencies[return_type].append(param_type)

    def has_provider(self, dep_type: type) -> bool:
        """Check if a dependency type has a registered provider.

        Args:
            dep_type: The dependency type to check

        Returns:
            True if a provider is registered for this type
        """
        return dep_type in self._providers

    def provided_types(self) -> set[type]:
        """The types the registered providers answer.

        Returns:
            Set of the provider keys registered so far
        """
        return set(self._providers)

    def get_shared_providers(self) -> dict[type, Callable]:
        """Get providers a hosting process may resolve.

        Returns:
            Dict of type -> provider, excluding plugins_only providers
        """
        return {
            dep_type: provider for dep_type, provider in self._providers.items() if dep_type not in self._plugins_only
        }

    def _get_providers_for_plugins(self) -> dict[type, Callable]:
        """Get all providers for plugins mechanism (CLI mode).

        Returns:
            Dict of type -> provider, including plugins_only providers
        """
        return self._providers.copy()

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
        context = context or {}

        # Check if already resolved (singleton)
        if dep_type in self._resolved:
            return self._resolved[dep_type]

        # Check for circular dependencies
        if dep_type in context:
            cycle = " -> ".join(str(t) for t in list(context.keys()) + [dep_type])
            raise ValueError(f"Circular dependency detected: {cycle}")

        provider = self._providers.get(dep_type)
        if not provider:
            raise ValueError(f"No provider found for: {dep_type}")

        # Build provider args with ctx for ExecContextAPI injection
        kwargs = self._build_provider_args(provider, context, ctx)

        # Call the provider
        result = provider(**kwargs)

        # Cache singleton
        self._resolved[dep_type] = result

        return result

    def _build_provider_args(
        self,
        provider: Callable,
        context: dict[type, Any],
        ctx: ExecContextAPI | None = None,
    ) -> dict[str, Any]:
        """Build keyword arguments for a provider by resolving its dependencies.

        Args:
            provider: Provider function
            context: Resolution context
            ctx: Optional ExecContextAPI for injecting ExecContextAPI dependencies

        Returns:
            Dict of parameter names to resolved values
        """
        hints = get_type_hints(provider)
        kwargs = {}

        for param_name, param_type in hints.items():
            if param_name == "return":
                continue

            # Special case for ExecContextAPI - inject ctx
            if param_type is ExecContextAPI or (
                isinstance(param_type, type) and issubclass(param_type, ExecContextAPI)
            ):
                if ctx is not None:
                    kwargs[param_name] = ctx
                continue

            if param_type in context:
                # Already resolved
                kwargs[param_name] = context[param_type]
            elif param_type in self._providers:
                # Need to resolve recursively
                kwargs[param_name] = self.resolve(param_type, context, ctx)

        return kwargs
