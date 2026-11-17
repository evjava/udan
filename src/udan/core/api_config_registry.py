"""Public API for the plugin configuration registry.

The registry answers "which configurations exist and what are their values?"
without core importing plugin modules by hand. Plugin modules declare their
schema next to the plugin code (module-level ``CONFIG`` and ``DOMAIN``);
the registry discovers those declarations, validates the values and serves
them by plugin name.
"""

from pydantic import BaseModel


class ConfigRegistryAPI:
    """API interface for the plugin configuration registry.

    A "section" is one plugin's validated configuration instance. Section
    names are plugin DOMAIN names; only installed plugins that declare a
    ``CONFIG`` schema appear in the registry.
    """

    def names(self) -> list[str]:
        """Get the names of all registered plugin config sections.

        Returns:
            Sorted list of plugin names (DOMAINs) that declared a CONFIG schema.
        """
        raise NotImplementedError

    def get(self, name: str) -> BaseModel:
        """Get the validated config instance of a plugin.

        Args:
            name: Plugin name (DOMAIN).

        Returns:
            The plugin's config model instance (validated, env overrides applied).

        Raises:
            KeyError: If no plugin with this name declared a CONFIG schema.
        """
        raise NotImplementedError
