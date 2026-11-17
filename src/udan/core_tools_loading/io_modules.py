"""Utility functions for loading modules from the filesystem.

The universal half of the plugin scan: importing a module by name, finding the
``plugins_*.py`` files in its directory tree and loading them, and reading ``DOMAIN``,
the one declaration that names no udan type. The scan reaches into the package's
subpackages as well - the core's operator subpackages contribute their plugin modules
from inside ``udan`` the same way an external package contributes from its own
directory. The readers that name one - the container provider, the event
subscriptions, the settings schema - live in udan.core.impl_plugins, which assembles them
into the plugins snapshot and is this module's only udan caller.
"""

import logging
from importlib import import_module
from pathlib import Path
from types import ModuleType

logger = logging.getLogger(__name__)


def get_plugin_domain(module: ModuleType) -> str:
    """Get a plugin module's DOMAIN, or the module stem without the plugins_ prefix."""
    domain = module.__dict__.get("DOMAIN")
    if domain:
        return str(domain)
    return module.__name__.rsplit(".", maxsplit=1)[-1].replace("plugins_", "", 1)


def _load_module(module_name: str) -> ModuleType | None:
    """Load a single module by name.

    Args:
        module_name: Full module name to import

    Returns:
        The loaded module, or None if import failed
    """
    try:
        return import_module(module_name)
    except Exception as e:
        logger.warning(f"Failed to load module '{module_name}': {e}")
        return None


def scan_module_for_plugins(module_name: str) -> list[ModuleType]:
    """Scan a module for plugins_*.py files and load them.

    The scan walks the module's whole directory tree, so a package contributes the
    plugin modules of its subpackages too. Sorted order keeps the composition of the
    found modules deterministic (a package's own directory first, then its
    subpackages in name order).

    Args:
        module_name: Name of the module to scan (e.g., 'udan', 'udan.plugins_tools_demo').

    Returns:
        List of loaded plugin modules (plugins_*.py files found in the module directory tree).
    """
    # Import the module to get its path
    try:
        module = import_module(module_name)
    except ModuleNotFoundError as e:
        logger.warning(f"Plugin module '{module_name}' not found, skipping: {e}")
        return []

    # Get the module's path to scan for plugins_*.py files
    if module.__file__ is None:
        return []
    module_dir = Path(module.__file__).resolve().parent

    # Scan for plugins_*.py files in the module directory tree
    plugin_modules = []
    for plugin_file in sorted(module_dir.rglob("plugins_*.py")):
        parent = plugin_file.parent.relative_to(module_dir)
        prefix = f"{module_name}.{'.'.join(parent.parts)}" if parent.parts else module_name
        plugin_module_name = f"{prefix}.{plugin_file.stem}"
        plugin_module = _load_module(plugin_module_name)
        if plugin_module is not None:
            plugin_modules.append(plugin_module)

    return plugin_modules
