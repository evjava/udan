"""Tools loader for loading tool metadata from modules.

This module provides a clean separation between loading tool metadata
and wrapping functions with dependency injection. The loader only handles:
- Loading annotated functions from modules
- Generating tool metadata
- Caching for performance

Wrapping with dependency injection is handled by the caller (e.g., ToolsRegistry).
"""

from collections.abc import Callable, Mapping
from functools import partial
from importlib import import_module
from pathlib import Path
from types import ModuleType

from joblib import Memory  # type: ignore[import-untyped]

from udan.core_tools_loading.api_annotated import get_annotated_functions, get_module_domain
from udan.core_tools_loading.api_tools import ToolKind, ToolMetadata
from udan.core_tools_loading.api_tools_loader import ToolsLoaderAPI
from udan.core_tools_loading.impl_utils_tools_loader import convert_tool_to_metadata
from udan.core_tools_loading.io_fs import calc_file_hash_blake2s, get_module_name_update_time, get_module_update_time
from udan.core_tools_loading.io_inspect import extract_injectable_types_from_modules, get_tool_for_function


def _load_tool_metadata(
    fn: Callable,
    domain: str | None,
    injectable_types: set[type] | None = None,
    kinds_by_name: Mapping[str, ToolKind] | None = None,
) -> ToolMetadata | None:
    """Convert an annotated function to tool metadata.

    Args:
        fn: Annotated function to convert
        domain: Optional domain for the tool
        injectable_types: Set of types that should be considered injectable
        kinds_by_name: The kind vocabulary; None means none is available, so every
            declared kind name becomes a bare kind

    Returns:
        ToolMetadata, or None when the tool cannot be built in this
        installation (its kind carries no metadata class: the package declaring the
        kind is not installed)
    """
    tool = get_tool_for_function(fn, injectable_types=injectable_types)
    tool_dict = tool.model_dump()

    # Note: API-injected parameters are already filtered out by get_tool_for_function

    # A None here is the conversion's deliberate skip (logged there), so it is not an
    # error: the caller filters Nones out of the module's metadata list.
    return convert_tool_to_metadata(fn, tool_dict, domain, kinds_by_name or {})


class ToolsLoader(ToolsLoaderAPI):
    """Loader for tool metadata from Python modules.

    This class handles loading tool metadata from modules without
    any dependency injection wrapping. The wrapping is handled by the caller.

    The loader provides caching support to avoid redundant metadata computation.
    Caching behavior is configured at instantiation time.
    """

    def __init__(
        self,
        cache_dir: str | None = None,
        use_cache: bool = True,
        kinds: Mapping[str, ToolKind] | None = None,
    ):
        """Initialize the loader.

        Args:
            cache_dir: Directory for caching metadata (None disables caching)
            use_cache: Whether to use caching (only relevant if cache_dir is provided)
            kinds: The kind vocabulary the metadata is built against (the container's
                component, read live). None (a loader built outside the container,
                where no service has filled one) resolves every declared kind name to
                a bare kind of that name.
        """
        self._use_cache = use_cache and cache_dir is not None
        self._memory: Memory | None = None
        self._injectable_types: set[type] = set()
        self._kinds = kinds if kinds is not None else {}
        if cache_dir is not None:
            self._memory = Memory(cache_dir, verbose=0)

    def _set_injectable_types(self, injectable_types: set[type]) -> None:
        """Set the types that should be considered injectable.

        Injectable types are excluded from the generated tool schema.
        These are typically types from @annotated_dependency providers.

        Args:
            injectable_types: Set of types that should be considered injectable
        """
        self._injectable_types = injectable_types

    def set_injectable_types_from_modules(self, module_names: list[str]) -> None:
        """Extract injectable types from @annotated_dependency providers in modules.

        This scans the specified modules for functions decorated with
        @annotated_dependency and sets the return types as injectable.

        Args:
            module_names: List of module names to scan for providers
        """
        self._injectable_types = extract_injectable_types_from_modules(module_names)

    def add_injectable_types(self, injectable_types: set[type]) -> None:
        """Add types to the ones counted as injectable; see ToolsLoaderAPI.

        Args:
            injectable_types: The types to add to the injectable set
        """
        self._injectable_types.update(injectable_types)

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
        metadatas = self._load_metadatas_from_module(module)

        # Return ORIGINAL functions from the module (not wrapped)
        # Wrapped functions are created by the caller using the injector
        result = [(metadata, getattr(module, metadata.name)) for metadata in metadatas]
        return result

    def _load_metadatas_from_module(
        self,
        module: ModuleType,
    ) -> list[ToolMetadata]:
        """Load tool metadata from a module.

        Args:
            module: Python module to load from

        Returns:
            List of tool metadata

        Raises:
            AssertionError: If cached data is invalid (module or dependencies changed)
        """
        module_name = module.__name__
        module_update_time = get_module_update_time(module)
        assert module.__file__ is not None
        module_path = Path(module.__file__)
        module_hash = calc_file_hash_blake2s(module_path)

        # Include modification times of dependencies that affect metadata processing
        # This ensures cache is invalidated when these files change
        tools_update_time = get_module_name_update_time("udan.core_tools_loading.impl_utils_tools_loader")
        utils_inspect_update_time = get_module_name_update_time("udan.core_tools_loading.io_inspect")
        annotated_update_time = get_module_name_update_time("udan.core_tools_loading.api_annotated")

        load_func = _load_metadatas_cacheable
        if self._use_cache and self._memory is not None:
            load_func = self._memory.cache(load_func)

        return load_func(
            module_name,
            module_update_time,
            module_hash,
            tools_update_time,
            utils_inspect_update_time,
            annotated_update_time,
            self._injectable_types,
            self._kinds,
        )


def _load_metadatas_cacheable(
    module_name: str,
    module_update_time: str,
    module_hash: str,
    tools_update_time: str,
    utils_inspect_update_time: str,
    annotated_update_time: str,
    injectable_types: set[type],
    kinds_by_name: Mapping[str, ToolKind],
) -> list[ToolMetadata]:
    """Cacheable version of tool metadata loading.

    This function is designed to be memoized by joblib.Memory.
    Module-level function (not a method) to avoid pickling `self` in joblib cache.

    Args:
        module_name: Name of the module to load from
        module_update_time: Modification time of the module
        module_hash: blake2s hash of module file content (detects content changes when mtime unchanged)
        tools_update_time: Modification time of udan.core.impl_utils_tools
        utils_inspect_update_time: Modification time of udan.core_tools_loading.io_inspect
        annotated_update_time: Modification time of udan.core_tools_loading.api_annotated
        injectable_types: Set of types that should be considered injectable
        kinds_by_name: The kind vocabulary, part of the cache key so a changed
            vocabulary invalidates the cached metadata

    Returns:
        List of tool metadata

    Raises:
        AssertionError: If any dependency has been modified since caching
    """
    module = import_module(module_name)
    module_update_time_real = get_module_update_time(module)
    assert module_update_time == module_update_time_real

    # Verify module content hasn't changed (even if mtime was preserved e.g. git checkout)
    assert module.__file__ is not None
    module_hash_real = calc_file_hash_blake2s(Path(module.__file__))
    assert module_hash == module_hash_real, "Module content changed (hash mismatch): cache stale"

    # Verify dependencies haven't changed
    assert tools_update_time == get_module_name_update_time("udan.core_tools_loading.impl_utils_tools_loader")
    assert utils_inspect_update_time == get_module_name_update_time("udan.core_tools_loading.io_inspect")
    assert annotated_update_time == get_module_name_update_time("udan.core_tools_loading.api_annotated")

    domain = get_module_domain(module)
    annotated_functions = get_annotated_functions(module)

    # Load metadata - filters out injected parameters using injectable_types
    sm_loader = partial(
        _load_tool_metadata, domain=domain, injectable_types=injectable_types, kinds_by_name=kinds_by_name
    )
    metadatas = list(filter(None, map(sm_loader, annotated_functions)))
    return metadatas
