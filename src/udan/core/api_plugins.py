"""Public API for the plugin packages: what is enabled and what each declared.

A plugin package contributes by declaring module-level attributes and classes in
its ``plugins_*.py`` files: ``DOMAIN`` (its config section name), ``CONFIG`` (its
settings schema), ``PLUGIN`` (its container contribution),
``SUBSCRIBE`` (its event wiring) and ``ToolKindService`` subclasses (its tool
kinds). PluginsAPI owns the discovery of the enabled packages - one pass over the
core and the configured packages, built before the container exists and handed to
it as a context value - and answers questions about the declarations afterwards,
so no component re-derives which packages are enabled or re-reads what they
declared.

Discovery is the whole boundary: the declarations are read, not interpreted.
Tool loading stays with ToolsLoaderAPI, which reads the modules this hands out.
"""

from types import ModuleType

from pydantic import BaseModel, ConfigDict

from udan.core.api_event_bus import CommandExecutedEvent
from udan.core_tools_loading.api_tool_kinds import ToolKindService
from udan.decompof import Plugin, Provider


class PluginPackage(BaseModel):
    """One plugins_*.py module, with what it declared.

    Built by Plugins from a scanned module; nothing constructs it by hand. Every
    field is a declaration read off the module, in the module's own terms - the
    interpretation (which services the provider builds, which kinds make the
    chain) stays with the component that asked.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    module: ModuleType
    # The plugin module itself; its tools are loaded from it by ToolsLoaderAPI
    name: str
    # Full module name ("udan.plugins_tools_examples.plugins_fs")
    domain: str
    # The DOMAIN declaration, or the module stem without the plugins_ prefix
    config_schema: type[BaseModel] | None
    # The CONFIG declaration; None when the module declares no settings schema
    plugin: Plugin | None
    # The PLUGIN declaration, built from nothing at the scan - the package's
    # container contribution, plus the attach/detach verbs
    subscriptions: dict[type[CommandExecutedEvent], type]
    # The SUBSCRIBE declaration: command event -> service type
    kind_services: list[type[ToolKindService]]
    # The ToolKindService subclasses the module defines (its KINDS)


class PluginsAPI:
    """The enabled plugin packages, discovered once and asked afterwards.

    A context value, not a factory-built service: the container needs the
    packages' providers in order to be built, so the composition root builds
    Plugins first and hands it in. Everything that wants to know what is enabled
    asks this, and one scan answers for the whole boot.
    """

    def packages(self) -> list[PluginPackage]:
        """Every enabled package's plugin module, core first, then config order, deduplicated.

        Returns:
            One PluginPackage per plugins_*.py module the enabled packages carry
        """
        raise NotImplementedError

    def providers(self) -> list[Provider]:
        """The container contributions of the enabled packages, in package order.

        Returns:
            The PLUGIN declarations; a package that declares none contributes none
        """
        raise NotImplementedError

    def kind_services(self) -> list[type[ToolKindService]]:
        """The tool kind services the enabled packages declare, in package order.

        Returns:
            Every ToolKindService subclass defined in an enabled package's modules
        """
        raise NotImplementedError

    def config_schemas(self) -> dict[str, type[BaseModel]]:
        """The settings schemas of the enabled packages, by plugin domain.

        Returns:
            The CONFIG declarations keyed by DOMAIN; a package without one has no section
        """
        raise NotImplementedError
