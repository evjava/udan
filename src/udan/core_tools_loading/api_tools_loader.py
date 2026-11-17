"""Public API for tools loader.

This module defines the public API interface for loading tool metadata
from Python modules.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

from udan.core_tools_loading.api_tools import ToolMetadata


class ToolsLoaderAPI:
    """API interface for tools loader.

    This class defines the public API for loading tool metadata
    from Python modules. The loader only handles loading and metadata generation,
    without any dependency injection wrapping.

    Caching behavior is configured at instantiation time.
    """

    def set_injectable_types_from_modules(self, module_names: list[str]) -> None:
        """Extract injectable types from @annotated_dependency providers in modules.

        This scans the specified modules for functions decorated with
        @annotated_dependency and sets the return types as injectable.

        Args:
            module_names: List of module names to scan for providers
        """
        raise NotImplementedError

    def add_injectable_types(self, injectable_types: set[type]) -> None:
        """Add types to the ones counted as injectable, without dropping the set.

        A service that resolves from a host other than a provider module - the
        DI container's own declarations among them - classifies the same way:
        a tool annotating one keeps it out of its schema.

        Args:
            injectable_types: The types to add to the injectable set
        """
        raise NotImplementedError

    def load_from_module(
        self,
        module: ModuleType,
    ) -> list[tuple[ToolMetadata, Callable]]:
        """Load tools from a module.

        This loads both the tool metadata and the original functions
        from the module. Functions are NOT wrapped with dependency injection.

        Args:
            module: Python module to load from

        Returns:
            List of (metadata, original_function) tuples

        Raises:
            AssertionError: If cached data is invalid (module or dependencies changed)
        """
        raise NotImplementedError
