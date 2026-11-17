"""The enabled plugin packages: discovered once, read once.

impl_plugins implements udan.core.api_plugins. Plugins scans the enabled packages in
one pass - the "udan" core first (its plugin subpackages included: the operator
engine and kinds contribute from inside udan.operator*), then
UdanConfig.udan_plugin_modules in config order, deduplicated by module name - and
builds a PluginPackage per plugins_*.py module. The readers of the declarations
live here, not in a generic io_ module: they are DOMAIN-bound, each one naming a
udan type (a decompof Provider, a CommandExecutedEvent key, a pydantic
BaseModel), so a declaration has exactly one reader and one home. Only the
universal half of the scan - importing a module, finding its plugins_*.py files,
reading DOMAIN - is udan.core_tools_loading.io_modules. A PLUGIN that is not a Plugin
fails the boot instead of being silently dropped.
"""

import logging
from types import ModuleType
from typing import Any

from pydantic import BaseModel

from udan.core.api_event_bus import CommandExecutedEvent
from udan.core.api_plugins import PluginPackage, PluginsAPI
from udan.core.config import UdanConfig
from udan.core_tools_loading.api_tool_kinds import ToolKindService, get_kind_services
from udan.core_tools_loading.io_modules import get_plugin_domain, scan_module_for_plugins
from udan.decompof import Plugin, Provider
from udan.decompof.loader import PLUGIN_ATTRIBUTE

logger = logging.getLogger(__name__)


def _module_declaration(module: ModuleType, attribute: str) -> Any:
    """A module's declaration by attribute name, or None when the module declares none.

    Args:
        module: The scanned plugins_*.py module.
        attribute: The declaration's name (PLUGIN_ATTRIBUTE, "CONFIG", "SUBSCRIBE").

    Returns:
        What the module declared, or None.
    """
    return module.__dict__.get(attribute)


def _plugin_plugin(module: ModuleType) -> Plugin | None:
    """Read a module's PLUGIN declaration, or None when the module declares none.

    Read off one declared name, never a search for something plugin-shaped -
    the discipline decompof's loader applies to the same attribute name
    (declared_plugin): a module holding two plugin-shaped objects would
    otherwise be a coin toss. What a module declares is the class, and the
    scan builds it from nothing, the way the loader builds its plugins - an
    instance is not a declaration, and a module that declares one has
    instantiating where declaring was meant.

    Raises:
        TypeError: The module declares PLUGIN that is not a Plugin class - a
            wiring mistake that used to surface as silence (the declaration
            silently contributed nothing) fails the boot instead.
    """
    declared = _module_declaration(module, PLUGIN_ATTRIBUTE)
    if declared is None:
        return None
    if isinstance(declared, type) and issubclass(declared, Plugin):
        return declared()
    raise TypeError(f"{module.__name__} declares PLUGIN that is not a Plugin class: {type(declared).__name__}")


def _plugin_subscriptions(module: ModuleType) -> dict[type[CommandExecutedEvent], type]:
    """Read a module's SUBSCRIBE declaration (command event -> service type).

    The service is resolved from the dependency registry and subscribed to the
    event by UdanContext when the module's providers are registered. Entries
    whose event is not a CommandExecutedEvent (the only event with a generic
    handler today) or whose service is not a class are skipped.
    """
    declared = _module_declaration(module, "SUBSCRIBE")
    if not isinstance(declared, dict):
        return {}
    subscriptions: dict[type[CommandExecutedEvent], type] = {}
    for event_type, service_type in declared.items():
        if isinstance(event_type, type) and issubclass(event_type, CommandExecutedEvent):
            if isinstance(service_type, type):
                subscriptions[event_type] = service_type
    return subscriptions


def _plugin_config_schema(module: ModuleType) -> type[BaseModel] | None:
    """Read a module's CONFIG declaration, or None when absent or not a model."""
    schema = _module_declaration(module, "CONFIG")
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        return schema
    return None


def _plugin_package(module: ModuleType) -> PluginPackage:
    """Read one scanned module's declarations into a PluginPackage."""
    return PluginPackage(
        module=module,
        name=module.__name__,
        domain=get_plugin_domain(module),
        config_schema=_plugin_config_schema(module),
        plugin=_plugin_plugin(module),
        subscriptions=_plugin_subscriptions(module),
        kind_services=get_kind_services(module),
    )


class Plugins(PluginsAPI):
    """The enabled packages of one configuration, scanned once at construction."""

    def __init__(self, config: UdanConfig) -> None:
        """Scan the enabled packages and read what each of their modules declared.

        Args:
            config: Core udan configuration; its udan_plugin_modules lists the
                external packages (the "udan" core - its plugin subpackages
                included - is always scanned first).
        """
        seen: set[str] = set()
        modules: list[ModuleType] = []
        for package_name in ["udan", *config.udan_plugin_modules]:
            for module in scan_module_for_plugins(package_name):
                if module.__name__ not in seen:
                    seen.add(module.__name__)
                    modules.append(module)
        self._packages: list[PluginPackage] = [_plugin_package(module) for module in modules]
        logger.info(
            "plugins: %d modules in %d packages: %d container contributions, %d config sections, %d kind services",
            len(self._packages),
            len({package.name.rsplit(".", maxsplit=1)[0] for package in self._packages}),
            sum(1 for package in self._packages if package.plugin is not None),
            sum(1 for package in self._packages if package.config_schema is not None),
            sum(len(package.kind_services) for package in self._packages),
        )

    def packages(self) -> list[PluginPackage]:
        """Every enabled package's plugin module, core first, then config order."""
        return list(self._packages)

    def providers(self) -> list[Provider]:
        """The container contributions of the enabled packages, in package order.

        A package that declares PLUGIN contributes it - a Plugin is a Provider,
        so the container sees one kind of contribution. A package that declares
        none contributes nothing.
        """
        contributions = [package.plugin for package in self._packages]
        return [contribution for contribution in contributions if contribution is not None]

    def kind_services(self) -> list[type[ToolKindService]]:
        """The tool kind services the enabled packages declare, in package order."""
        return [service for package in self._packages for service in package.kind_services]

    def config_schemas(self) -> dict[str, type[BaseModel]]:
        """The settings schemas of the enabled packages, keyed by plugin domain."""
        return {
            package.domain: package.config_schema for package in self._packages if package.config_schema is not None
        }
