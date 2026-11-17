"""Implementation of the plugin configuration registry."""

from typing import Any

from pydantic import BaseModel

from udan.core.api_config_registry import ConfigRegistryAPI
from udan.core.api_plugins import PluginsAPI
from udan.core.config import UdanConfig
from udan.decompof import Container


class ConfigRegistry(ConfigRegistryAPI):
    """Registry of plugin configuration sections.

    Serves the ``CONFIG`` declarations of the enabled plugin packages (udan
    core, built-in plugin packages, and the modules listed in
    ``UdanConfig.udan_plugin_modules``) as one validated instance per plugin.
    The instances are the container's own: the composition root synthesizes a
    factory per declaration, so what this registry reports is the very
    instance the plugin's factories and tools resolve - not a second
    construction of the same schema. Core never imports a plugin module
    statically: it only sees names and ``type[BaseModel]`` schemas, read off
    the plugins snapshot the container was composed from.
    """

    def __init__(self, config: UdanConfig, plugins: PluginsAPI, container: Container):
        """Read the enabled packages' sections, to be answered from the container.

        Args:
            config: Core udan configuration (kept for _core_dump()).
            plugins: The enabled packages and their declarations (the snapshot
                the container was composed from).
            container: The container the sections resolve through - one
                instance per config per process, built on the first ask.
        """
        self._config = config
        self._schemas: dict[str, type[BaseModel]] = plugins.config_schemas()
        self._container = container

    def names(self) -> list[str]:
        """Get sorted names of all registered plugin config sections."""
        return sorted(self._schemas)

    def _has(self, name: str) -> bool:
        """Check whether a plugin config section is registered.

        Args:
            name: Plugin name (DOMAIN).

        Returns:
            True if the plugin declared a CONFIG schema.
        """
        return name in self._schemas

    def get(self, name: str) -> BaseModel:
        """Get the validated config instance of a plugin, from the container.

        Raises:
            KeyError: With the known section names when the plugin is unknown.
        """
        schema = self._schemas.get(name)
        if schema is None:
            known = ", ".join(self.names()) or "none"
            raise KeyError(f"No plugin config section named {name!r} (installed: {known})")
        instance = self._container.get(schema)
        assert isinstance(instance, BaseModel)
        return instance

    def _core_dump(self) -> dict[str, Any]:
        """Dump the core (non-plugin) configuration.

        Returns:
            Dict of core UdanConfig field names to values.
        """
        return self._config.model_dump()
