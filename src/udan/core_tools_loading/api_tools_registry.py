"""Public API for tools registry.

This module defines the public API interface for accessing and querying
tools registered in the system.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType
from typing import Any

from udan.core_tools_loading.api_function_injector import FunctionInjectorAPI
from udan.core_tools_loading.api_tools import (
    ToolBinding,
    ToolDescriptor,
    ToolKind,
    ToolMetadata,
)


class ToolsRegistryAPI:
    """API interface for tools registry.

    This class defines the public API for accessing and querying tools
    registered in the system.

    The surface is generic: no method is tied to one tool kind. Kind-selective
    behaviour is expressed as the `kind` argument on the read methods and as per-kind
    `options` on `resolve` (the option name a kind declares as its `variant_meta_key`),
    so a kind that grows a new axis adds an option value, not a method.
    """

    def get_tools(self, kind: ToolKind | str | None = None) -> list[str]:
        """Get list of registered tool names.

        Args:
            kind: Tool kind to filter by (e.g. "inserter"), as a kind
                or as its name; None returns every kind

        Returns:
            List of tool names including aliases

        Raises:
            ValueError: If kind is not in the tool kind vocabulary
        """
        raise NotImplementedError

    def get_metadatas(self, kind: ToolKind | str | None = None) -> dict[str, ToolMetadata]:
        """Get registered tool metadatas, optionally filtered by kind.

        Args:
            kind: Tool kind to filter by, as a kind or as its name; None
                returns every kind

        Returns:
            Dictionary mapping tool names/aliases to their metadata
        """
        raise NotImplementedError

    def get_metadata(self, key: str) -> ToolMetadata | None:
        """Get metadata for a tool.

        Args:
            key: Tool name or alias

        Returns:
            Tool metadata, or None if not found
        """
        raise NotImplementedError

    def get_function(self, key: str) -> Callable | None:
        """Get function for a tool.

        Args:
            key: Tool name or alias

        Returns:
            Function callable, or None if not found
        """
        raise NotImplementedError

    def resolve(
        self,
        key_or_descriptor: str | ToolDescriptor | None = None,
        *,
        kind: ToolKind | str | None = None,
        **options: str,
    ) -> ToolBinding:
        """Resolve a tool to its metadata and function.

        Two shapes, both returning a ToolBinding:

        - By descriptor (`resolve(descriptor)`): resolves the descriptor's name. This is the
          descriptor path.
        - By name (`resolve(name)`): resolves a registered tool by name or alias.

        Args:
            key_or_descriptor: Tool name, alias, or descriptor.
            kind: Expected tool kind, checked against the registered metadata.
            **options: Per-kind resolution options, keyed by the kind's
                `variant_meta_key` when it declares one; the requested value
                selects which variant of a name resolves (falling back to the
                name's flat function).

        Returns:
            ToolBinding for the resolved tool

        Raises:
            ValueError: If the tool is not found, or the resolved metadata does
                not match `kind`
        """
        raise NotImplementedError

    def load_plugins(self, *plugin_modules: ModuleType, injector: FunctionInjectorAPI) -> None:
        """Load and register tools from plugin modules.

        A module may also define kinds: the `KINDS` declared by its tool kind
        services are registered before the module's tools are loaded - so the
        module's functions can declare `tool_type` values of its own.

        Args:
            *plugin_modules: Variable number of plugin modules to register.
                Each module should be an imported module object (e.g., plugins_demo, plugins_builtins).
            injector: FunctionInjectorAPI instance for wrapping functions with dependency injection.

        Raises:
            ValueError: If a module contains no tools
        """
        raise NotImplementedError

    def register_metadata(
        self,
        metadata: ToolMetadata,
        injector: FunctionInjectorAPI | None = None,
        fn: Callable[..., Any] | None = None,
    ) -> None:
        """Register a tool, wrapping functions with auto-injected dependencies.

        Args:
            metadata: Tool metadata
            injector: FunctionInjectorAPI instance for wrapping functions; None is allowed
                when fn has no injectable dependencies (e.g. closures over their inputs)
            fn: Function to register (will be wrapped for injection when injector given)
        """
        raise NotImplementedError

    def register_many_metadatas(
        self, metadata_fns: list[tuple[ToolMetadata, Callable]], injector: FunctionInjectorAPI
    ) -> None:
        """Register multiple tools, wrapping functions with auto-injected dependencies.

        Args:
            metadata_fns: List of (metadata, function) tuples
            injector: FunctionInjectorAPI instance for wrapping functions
        """
        raise NotImplementedError

    def get_preferences(self) -> dict:
        """Get the tool preferences the registry was built with.

        The preferences map a query word to the tool it stands for (e.g.
        `{"diff": "git.insert_diff"}`). Consumers that resolve a bare query word
        against them read them here instead of reaching for the configuration,
        which stays a core detail.

        Returns:
            The preferences dict, empty when none were configured
        """
        raise NotImplementedError

    def validate_preferences(self) -> None:
        """Validate tool preferences and warn about incorrect usage.

        This method checks the configured tool preferences against
        the registered tool metadatas and issues warnings for any
        incorrect usage patterns.
        """
        raise NotImplementedError
