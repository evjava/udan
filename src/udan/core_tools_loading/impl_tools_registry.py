"""Registry for tools."""

import inspect
from collections.abc import Callable
from types import ModuleType
from typing import Any, Protocol, runtime_checkable

from udan.core_tools_loading.api_annotated import unwrap_function
from udan.core_tools_loading.api_function_injector import FunctionInjectorAPI
from udan.core_tools_loading.api_tool_kinds import ToolKindsRegistryAPI, get_kind_services
from udan.core_tools_loading.api_tools import (
    DEFAULT_KIND,
    ToolBinding,
    ToolDescriptor,
    ToolKind,
    ToolMetadata,
)
from udan.core_tools_loading.api_tools_loader import ToolsLoaderAPI
from udan.core_tools_loading.api_tools_registry import ToolsRegistryAPI


def _kind_name(kind: ToolKind | str | None) -> str | None:
    """Name of a `kind` argument: the registry accepts a kind or its name.

    Args:
        kind: A kind from the vocabulary, or a kind name as written in a query

    Returns:
        The kind name, or None
    """
    if isinstance(kind, ToolKind):
        return kind.name
    return kind


def _requires_item_parameter(metadata: ToolMetadata, kinds=None) -> bool:
    """Whether this kind's function must take an `item` parameter.

    The per-kind rule is the kind's own (ToolKind.requires_item_parameter): filters
    select items and groupers group them, so they are applied per item; inserters
    create items and take none. A kind whose members may be computed without an
    `item` declares the metadata field that names the member (its
    `metadata_variant_key`) and the values of that field that run item-free (its
    `metadata_item_free_values`): the rule then fires only when the tool
    declared the field. External tools have a **kwargs signature that cannot be
    inspected meaningfully.

    A tool registered as bare metadata - hand-built, so its kind is the
    loader's last-resort default - takes the law of the vocabulary's default kind:
    the default is what the language computes per item, and its law is the law a
    hand-built metadata is held to.

    Args:
        metadata: Tool metadata
        kinds: The kind vocabulary, for the default kind's law

    Returns:
        True if the registered function must accept `item`
    """
    is_external = not metadata.fn_path  # External tools have empty fn_path
    if is_external:
        return False
    # The kind travels with the metadata, so the signature law is read off it directly.
    kind = metadata.tool_type
    if kind is DEFAULT_KIND:
        kind = (kinds.default_kind() if kinds is not None else None) or kind
    if kind.metadata_variant_key is None:
        return kind.requires_item_parameter
    declared = metadata.meta.get(kind.metadata_variant_key)
    return declared is not None and declared not in kind.metadata_item_free_values


def _validate_tool_preferences(prefs: dict, metadatas: dict[str, ToolMetadata]) -> list[str]:
    """Validate preference values and warn about incorrect usage.

    Checks:
    - All preference values point to a registered tool (not-found check).
    - Unqualified values that do resolve are reported with their qualified form
      (e.g., "insert_diff" -> "git.insert_diff"), because the parser honors only
      qualified values for single-token queries.

    Args:
        prefs: Dictionary of preference key -> value mappings
        metadatas: Dictionary of tool name -> metadata mappings

    Returns:
        List of warning messages for invalid preferences
    """
    warnings: list[str] = []
    _MAX_SUGGESTIONS = 3

    for pref_key, pref_value in prefs.items():
        if "." in pref_value:
            # Qualified value: verify it points to a registered tool.
            # Either an exact registry key or "domain.name" for a registered name.
            if pref_value in metadatas:
                continue
            base, _, name = pref_value.rpartition(".")
            metadata = metadatas.get(name)
            if metadata is not None and metadata.meta.get("domain", "") == base:
                continue
            warnings.append(f"Preference '{pref_key} -> {pref_value}' not found: no registered tool with this name.")
            continue

        # Find all tools that match this unqualified name
        qualified_candidates = [name for name in metadatas if name == pref_value or name.endswith("." + pref_value)]

        if not qualified_candidates:
            warnings.append(f"Preference '{pref_key} -> {pref_value}' not found: no registered tool with this name.")
            continue

        # Build qualified suggestions by checking metadata
        qualified_suggestions = []
        for name in qualified_candidates:
            metadata = metadatas.get(name)
            if metadata:
                domain = metadata.meta.get("domain", "")
                if domain and domain != "builtins":
                    qualified_name = f"{domain}.{name}"
                    qualified_suggestions.append(qualified_name)
                else:
                    qualified_suggestions.append(name)

        if not qualified_suggestions:
            continue

        suggestions_str = ", ".join(qualified_suggestions[:_MAX_SUGGESTIONS])
        if len(qualified_suggestions) > _MAX_SUGGESTIONS:
            suggestions_str += ", ..."
        warnings.append(
            f"Preference '{pref_key} -> {pref_value}' should use a qualified name. Did you mean: {suggestions_str}?"
        )

    return warnings


def _name_of(key_or_descriptor: str | ToolDescriptor | None) -> str:
    """Get the registry key for a name or a descriptor.

    Args:
        key_or_descriptor: Tool name, alias, or descriptor

    Returns:
        The tool name

    Raises:
        ValueError: If nothing was passed to resolve
    """
    if key_or_descriptor is None:
        raise ValueError("resolve() needs a name or a descriptor")
    if isinstance(key_or_descriptor, ToolDescriptor):
        return key_or_descriptor.name
    return key_or_descriptor


@runtime_checkable
class Logger(Protocol):
    def debug(self, msg: str) -> None:
        """Log a debug message."""
        ...

    def warning(self, msg: str) -> None:
        """Log a warning message."""
        ...


class ToolsRegistry(ToolsRegistryAPI):
    """Registry for storing and resolving tools.

    Handles registration of metadata and functions, and resolution
    of descriptors to concrete objects.
    """

    def __init__(
        self,
        logger: Logger,
        loader: ToolsLoaderAPI,
        preferences: dict | None = None,
        kinds: ToolKindsRegistryAPI | None = None,
    ) -> None:
        """Initialize registry.

        Args:
            logger: Logger the registry reports to (anything with debug and warning)
            loader: Tools loader
            preferences: Tool preferences dict
            kinds: The tool kind vocabulary `kind` arguments are checked against
        """
        self._metadatas: dict[str, ToolMetadata] = {}
        self._functions: dict[str, Callable] = {}
        # Variants by (name_or_alias, variant value); see register() and resolve()
        self._variants: dict[tuple[str, str], Callable] = {}
        # Memoized name list, rebuilt lazily and dropped by _invalidate_name_list()
        self._tools_names: list[str] | None = None
        self._logger = logger
        self._preferences = preferences or {}
        self._kinds = kinds

        self._loader = loader

    def get_preferences(self) -> dict:
        """Get the tool preferences the registry was built with.

        Returns:
            The preferences dict, empty when none were configured
        """
        return self._preferences

    def validate_preferences(self) -> None:
        """Validate tool preferences and warn about incorrect usage.

        This method checks the configured tool preferences against
        the registered tool metadatas and issues warnings for any
        incorrect usage patterns.
        """
        prefs = self._preferences
        metadatas = self._metadatas
        warning_lines = _validate_tool_preferences(prefs, metadatas)
        for line in warning_lines:
            self._logger.warning(line)

    def get_metadata(self, key: str) -> ToolMetadata | None:
        """Get metadata for a tool by key.

        Args:
            key: Tool name or alias

        Returns:
            ToolMetadata if found, None otherwise
        """
        return self._metadatas.get(key)

    def get_function(self, key: str) -> Callable | None:
        """Get function for a tool by key.

        Args:
            key: Tool name or alias

        Returns:
            Callable if found, None otherwise
        """
        return self._functions.get(key)

    def get_metadatas(self, kind: ToolKind | str | None = None) -> dict[str, ToolMetadata]:
        """Get registered tool metadatas, optionally filtered by kind.

        Args:
            kind: Tool kind to filter by, as a kind or as its name; None
                returns every kind

        Returns:
            Dictionary mapping tool names/aliases to their metadata

        Raises:
            ValueError: If kind is not in the tool kind vocabulary
        """
        kind_name = _kind_name(kind)
        if kind_name is None:
            return self._metadatas.copy()
        return {key: metadata for key, metadata in self._metadatas.items() if metadata.tool_type.name == kind_name}

    def resolve(
        self,
        key_or_descriptor: str | ToolDescriptor | None = None,
        *,
        kind: ToolKind | str | None = None,
        **options: str,
    ) -> ToolBinding:
        """Resolve a tool to its metadata and function.

        Args:
            key_or_descriptor: Tool name, alias, or descriptor
            kind: Expected tool kind, checked against the registered metadata
            **options: Per-kind resolution options, keyed by the kind's
                `variant_meta_key` when it declares one; the requested value
                selects which variant of a name resolves

        Returns:
            ToolBinding for the resolved tool

        Raises:
            ValueError: If the tool is not found or the kind does not match
        """
        kind_name = _kind_name(kind)
        # A kind with a variant axis resolves through its variants (the requested
        # option picks one); kinds without one resolve flat.
        kind_of_name = self._kinds.get(kind_name) if kind_name is not None and self._kinds is not None else None
        has_variants = kind_of_name is not None and kind_of_name.variant_meta_key is not None
        if has_variants or options:
            return self._resolve_variant(key_or_descriptor, **options)
        return self._resolve_by_key(key_or_descriptor, kind=kind_name)

    def _validate_signature(self, metadata: ToolMetadata, fn: Callable) -> None:
        """Validate a function's signature against its declared kind.

        The single register-time hook for kind-specific signature rules: per-item
        kinds are computed per item, so their functions must accept `item`.
        External tools are exempt - they have a **kwargs signature.

        Deliberately off ToolsRegistryAPI: registration is the only caller, so
        exposing it on the interface would be dead surface.

        Args:
            metadata: Tool metadata carrying the kind
            fn: Function about to be registered

        Raises:
            ValueError: If the function does not satisfy its kind's signature rule
        """
        if not _requires_item_parameter(metadata, self._kinds):
            return
        sig = inspect.signature(unwrap_function(fn))
        if "item" not in sig.parameters:
            # The blame is the law's kind: a bare metadata is held to the default kind's law
            kind = metadata.tool_type
            if kind is DEFAULT_KIND and self._kinds is not None:
                kind = self._kinds.default_kind() or kind
            raise ValueError(
                f"Tool '{metadata.name}' ({kind.name}) must have an 'item' parameter. "
                f"Per-item tools are computed for individual items. Function signature: {sig}"
            )

    def _register(self, metadata: ToolMetadata, fn: Callable | None = None) -> None:
        """Register a tool with its function.

        Args:
            metadata: Tool metadata
            fn: Function to register

        Raises:
            ValueError: If function is None or the signature violates the kind's contract
        """
        # Check for required function first
        if fn is None:
            raise ValueError(f"Function is required for tool '{metadata.name}'")

        self._validate_signature(metadata, fn)

        # A kind with a variant axis indexes its functions per variant, so a name can
        # carry several functions, one per declared variant value
        is_variant_kind = metadata.tool_type.variant_meta_key is not None
        variant_value = metadata.meta.get(metadata.tool_type.variant_meta_key) if is_variant_kind else None
        if is_variant_kind:
            self._register_variant(metadata, fn)
        self._metadatas[metadata.name] = metadata
        for alias in metadata.meta.get("aliases", []):
            # A variant of a name never shadows an occupied flat alias: the flat
            # namespace belongs to the name's own function.
            if is_variant_kind and variant_value and alias in self._metadatas:
                continue
            self._metadatas[alias] = metadata
            self._functions[alias] = fn
        self._functions[metadata.name] = fn
        self._invalidate_name_list()

    def _invalidate_name_list(self) -> None:
        """Drop the memoized name list so the next read rebuilds it.

        Called from register() because that is the only place _metadatas grows.
        Kind-filtered reads walk _metadatas directly, so they need no invalidation.
        """
        self._tools_names = None

    def _register_variant(self, metadata: ToolMetadata, fn: Callable) -> None:
        """Index a function per (name_or_alias, variant value) of its kind's variant axis.

        Only a tool that declares a value in its kind's variant meta key is indexed:
        a tool without one is the name's own function, reachable flat.

        Args:
            metadata: Metadata carrying the variant value in its kind's variant meta key
            fn: Function
        """
        variant_value = metadata.meta.get(metadata.tool_type.variant_meta_key)
        if variant_value is None:
            return
        keys = [metadata.name, *metadata.meta.get("aliases", [])]
        for key in keys:
            self._variants[(key, variant_value)] = fn

    def _register_many(self, metadata_fns: list[tuple[ToolMetadata, Callable]]) -> None:
        """Register multiple tools.

        Args:
            metadata_fns: List of (metadata, function) tuples
        """
        tool_names = [metadata_fn[0].name for metadata_fn in metadata_fns]
        self._logger.debug(f"loaded tools: {tool_names}")
        for metadata, fn in metadata_fns:
            self._register(metadata, fn)

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
        # Wrap function to handle auto-injected dependencies
        if fn is not None and injector is not None:
            fn = injector.wrap_function(fn)
        self._register(metadata, fn)

    def register_many_metadatas(
        self, metadata_fns: list[tuple[ToolMetadata, Callable]], injector: FunctionInjectorAPI
    ) -> None:
        """Register multiple tools, wrapping functions with auto-injected dependencies.

        Args:
            metadata_fns: List of (metadata, function) tuples
            injector: FunctionInjectorAPI instance for wrapping functions
        """
        # Wrap functions to handle auto-injected dependencies
        wrapped_metadata_fns = []
        for metadata, fn in metadata_fns:
            if fn is not None:
                fn_wrapped = injector.wrap_function(fn)
                # NOTE: We no longer update the module's attribute with the wrapped function
                # This was causing issues when multiple contexts were created in tests
                # because the module attribute would be modified and subsequent wraps
                # would wrap the already-wrapped function
                fn = fn_wrapped
            wrapped_metadata_fns.append((metadata, fn))
        self._register_many(wrapped_metadata_fns)

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
        kind_name = _kind_name(kind)
        kinds = self._kinds
        if kind_name is not None and kinds is not None and kind_name not in kinds:
            allowed = ", ".join(sorted(kinds))
            raise ValueError(f"Unknown tool kind: {kind_name!r}. Allowed kinds: {allowed}")
        if kind_name is None:
            if self._tools_names is None:
                self._tools_names = list(self._metadatas.keys())
            return self._tools_names.copy()
        return [key for key, metadata in self._metadatas.items() if metadata.tool_type.name == kind_name]

    def load_plugins(self, *plugin_modules, injector: FunctionInjectorAPI) -> None:
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
        plugin_names = []
        for plugin_module in plugin_modules:
            module_name = plugin_module.__name__
            # Strip udan.plugins_ prefix for cleaner display
            display_name = module_name.replace("udan.plugins_", "")
            # A plugin defines its kinds in a service, and the declaration has to be in
            # the vocabulary before the module's metadata is built.
            self._register_module_kind_services(plugin_module)
            # Load tools from the module (returns metadata + original functions)
            # Use non-cached loader for load_plugins to avoid cache issues in tests
            metadata_fns = self._loader.load_from_module(plugin_module)
            if not metadata_fns:
                # Skip modules without tools (may be utility-only plugins)
                self._logger.debug(f"Skipping {module_name}: no tools found")
                continue
            plugin_names.append(display_name)
            # Register all tools from this module
            # register_many_metadatas does the wrapping: wrapping here too would double-wrap,
            # and the outer wrapper would drop ctx before the inner one could resolve deps
            self.register_many_metadatas(metadata_fns, injector=injector)
            self._logger.debug(f"Registered tools from {display_name}")

        # Log summary of loaded plugins
        self._logger.debug(f"Loaded plugins: {', '.join(plugin_names)}")

    def _register_module_kind_services(self, plugin_module: ModuleType) -> None:
        """Register the kinds the tool-kind services of a plugin module declare.

        A plugin defines its kinds in a service (a ToolKindService subclass):
        the class declares the kinds it owns as its `KINDS`, exactly like the core kind
        services (the applying service declares the chain-forming kinds). Registering
        them here, before the module's tools are loaded, is what lets the module's
        functions declare `tool_type` values of the module's own. A kind another module
        already registered is only filled in (see ToolKindsRegistry.register).

        Args:
            plugin_module: Module whose tools are about to be loaded
        """
        kind_services = get_kind_services(plugin_module)
        if not kind_services or self._kinds is None:
            return
        for kind_service in kind_services:
            for kind in kind_service.KINDS:
                self._kinds.register(kind)
        names = ", ".join(kind_service.__name__ for kind_service in kind_services)
        self._logger.debug(f"Registered kinds of {plugin_module.__name__} services: {names}")

    def _resolve_variant(self, key_or_descriptor: str | ToolDescriptor | None, **options: str) -> ToolBinding:
        """Resolve a name of a variant-axis kind to its function, honoring the request.

        A name of a kind with a variant axis (ToolKind.variant_meta_key) can carry
        several functions, one per declared variant value. Resolution picks the one
        indexed under the requested value; when none is requested or none matches,
        the name's flat function is returned.

        Args:
            key_or_descriptor: Name or alias of a tool of a variant-axis kind
            **options: Resolution options, keyed by the kind's variant meta key

        Returns:
            ToolBinding with the tool's metadata and the resolved variant function

        Raises:
            ValueError: If the name is not found
        """
        name = _name_of(key_or_descriptor)
        metadata = self._metadatas.get(name)
        if not metadata:
            raise ValueError(f"Not found tool with key={name}")
        variant_key = metadata.tool_type.variant_meta_key or ""
        requested = options.get(variant_key, "")
        fn = self._variants.get((name, requested)) if requested else None
        if not fn:
            fn = self._functions.get(name)
        if not fn:
            raise ValueError(f"Not found tool with key={name}")
        return ToolBinding(metadata=metadata, fn=fn)

    def _resolve_by_key(
        self,
        key_or_descriptor: str | ToolDescriptor | None,
        kind: str | None,
    ) -> ToolBinding:
        """Resolve a tool by name, alias, or descriptor.

        Args:
            key_or_descriptor: Tool name, alias, or descriptor
            kind: Expected kind name, when the caller wants it checked

        Returns:
            ToolBinding with the tool's metadata and function

        Raises:
            ValueError: If the tool or its function is not found, or the
                registered metadata does not have the expected kind
        """
        name = _name_of(key_or_descriptor)
        metadata = self._metadatas.get(name)
        if not metadata:
            raise ValueError(f"Not found tool with key={name}")
        if kind is not None and metadata.tool_type.name != kind:
            raise ValueError(f"Tool '{name}' is '{metadata.tool_type}', not '{kind}'")
        fn = self._functions.get(name)
        if not fn:
            err = f"metadata for key={name} is present: {metadata!r}, but function is not found"
            raise ValueError(err)
        return ToolBinding(metadata=metadata, fn=fn)
