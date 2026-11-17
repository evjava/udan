"""Udan configuration system for default tool parameters."""

import pkgutil
from typing import Any

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from udan.core.utils_pydantic import CommaSeparatedList, ConfigBaseSettings, ExpandedPath

# A plugin package follows the udan plugin naming convention; the prefix is the
# whole contract, so udan names no plugin package - a package joins the defaults
# by being installed and leaves them by being removed.
_PLUGIN_PACKAGE_PREFIX = "udan_plugins_"


def _discover_plugin_packages() -> list[str]:
    """Names of the installed plugin packages, sorted.

    A plugin package is any installed top-level package whose name follows the udan
    plugin naming convention (_PLUGIN_PACKAGE_PREFIX). Discovery is by convention
    alone, which is why udan can list the installed plugins without naming any of
    them.

    Returns:
        Sorted names of the installed plugin packages
    """
    found = {name for _, name, is_pkg in pkgutil.iter_modules() if is_pkg and name.startswith(_PLUGIN_PACKAGE_PREFIX)}
    return sorted(found)


class UdanConfig(ConfigBaseSettings):
    """Configuration for default tool parameters and preferences of Udan.

    Environment Variables:
        ENV_FILE: Path to custom .env file (overrides default .env file location)
        UDAN_CONFIG_DIR: Base directory for all udan configuration (default: "./.udan")
        UDAN_CACHE_DIR: Cache directory (default: "~/.local/share/udan")
        UDAN_VARS_PATH: Path to variables file (default: "./.udan/vars.env")
        UDAN_TOOLS_VARIABLES_DEFAULTS: JSON string with default tool parameters
        UDAN_TOOLS_PREFERENCES_INPUT: JSON string with preferred tool names

    Note:
        Plugin-specific configuration (e.g. history and saved queries paths) is
        declared by the plugins themselves: a plugin module declares CONFIG
        with its own env prefix, and the ConfigRegistry serves validated
        instances by plugin name. See udan.plugins_history for an example.

    Example:
        config = UdanConfig(
            udan_cache_dir="~/.local/share/udan",
            udan_vars_path="~/.config/udan/vars.env",
            udan_tools_variables_defaults={
                "insert_fruits": {"pattern": "apple"},
                "org.cur": {"dir": "~/org"},
            },
            udan_tools_preferences_input={
                "diff": "git.insert_diff"
            }
        )

    Note:
        All path fields automatically expand ~ (home directory) using validators.
    """

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
    )

    # ============================================================================
    # Core Configuration - Directories and Files
    # ============================================================================

    udan_cache_dir: ExpandedPath = Field(
        default="~/.local/share/udan",
        description="Cache directory (~ is expanded)",
    )
    udan_vars_path: ExpandedPath = Field(
        default="./.udan/vars.env",
        description="Variables file path (~ is expanded)",
    )

    # ============================================================================
    # Tool Configuration
    # ============================================================================

    udan_tools_variables_defaults: dict[str, dict[str, Any]] = Field(
        default_factory=dict, description="Default parameter values for tools"
    )
    udan_tools_preferences_input: dict[str, str] = Field(
        default_factory=dict, description="Preferred tool name aliases"
    )

    # ============================================================================
    # Debug Configuration
    # ============================================================================

    udan_log_time: bool = Field(
        default=False, description="Enable timestamp prefix in debug logs (format: [HH:MM.mmm])"
    )

    # ============================================================================
    # Type System Configuration
    # ============================================================================

    udan_types_enabled: bool = Field(
        default=True,
        description=(
            "Enable the forest type system: chain validation (TypeCombinationError), "
            "type-aware `?` completions and `:` render suggestions"
        ),
    )

    # ============================================================================
    # Plugin Loading Configuration
    # ============================================================================

    udan_plugin_modules: CommaSeparatedList = Field(
        default_factory=_discover_plugin_packages,
        description=(
            "List of external modules to scan for plugins_*.py "
            "(e.g., ['udan_plugins_example']). "
            "Defaults to every installed plugin package (the udan_plugins_* naming "
            "convention, see _discover_plugin_packages). "
            "UDAN_PLUGIN_MODULES replaces the list, so omitting a package turns its "
            "capability off. "
            "The core's own plugin subpackages (the query language in udan.parsing, "
            "the operator engine and kinds under udan.operator*, the value and output "
            "domains udan.attributes and udan.renders, the built-in tools under "
            "udan.plugins_tools_*, the history domain udan.plugins_history) are scanned with the core "
            "itself and are not on this list: they are always loaded. "
            "Can be set via UDAN_PLUGIN_MODULES env var as comma-separated module "
            "names (e.g., 'udan_plugins_example') or as a JSON list."
        ),
    )

    # ============================================================================
    # Auto-Limit Configuration
    # ============================================================================

    udan_default_limit: int = Field(
        default=30,
        description=(
            "Default limit to apply when no explicit limit is specified. "
            "Applied after the chain is applied but before rendering. "
            "Set to 0 or None to disable auto-limit."
        ),
    )
