"""Loading the plugins the caller names, and calling them through the injector.

Nothing here knows what a host is. A host arrives as an argument and is passed,
untouched, to whatever the plugin's :meth:`~udan.decompof.plugin.Plugin.attach`
and :meth:`~udan.decompof.plugin.Plugin.detach` annotate -- the
:class:`~udan.decompof.injector.Injector` does the reaching, and this module
never looks inside the host. It therefore loads plugins for any object the
caller composes - an application, a bare list - and imports neither.

One thing is a convention here, and it is a parameter with a default, so a host
application can choose its own without this module changing:

``PLUGIN``
    The module attribute naming the plugin to load. One declared name, read
    directly -- never a search of the module for something plugin-shaped, which
    would make a module holding two of them a coin toss.

A plugin is instantiated from nothing: the loader passes no arguments, so
configuration is the plugin's own business, read from wherever the plugin
finds it. Which plugins load at all is the caller's decision -- ``mount_plugins``
is handed the module names and loads exactly those, so a name that cannot be
imported, that declares no plugin, or whose ``attach`` asks for a type nothing
provides, raises: silently dropping plugins that were asked for would be much
harder to notice than a failed startup.
"""

import importlib
from collections.abc import Sequence
from types import ModuleType
from typing import TypeVar

from udan.decompof.injector import Injector
from udan.decompof.plugin import Plugin

#: The module attribute that says which class is the plugin.
PLUGIN_ATTRIBUTE = "PLUGIN"

Host = TypeVar("Host")


class PluginError(RuntimeError):
    """A named plugin cannot be loaded, instantiated, or attached."""


def is_plugin(value: object) -> bool:
    """Whether ``value`` is a plugin a module could declare, and not the base class."""
    return isinstance(value, type) and issubclass(value, Plugin) and value is not Plugin


def declared_plugin(module: ModuleType, origin: str, attribute: str = PLUGIN_ATTRIBUTE) -> Plugin:
    """The plugin ``module`` declares, built from nothing.

    Read off one name rather than discovered by searching, so a plugin is
    explicit about what it is. Construction is argument-free, and a constructor
    that needs arguments raises the ``TypeError`` Python raises for it, untouched
    -- like an import failure, that says more than any wrapper would.
    """
    plugin_type = getattr(module, attribute, None)
    if plugin_type is None:
        raise PluginError(f"{origin} declares no {attribute} to load")
    if not is_plugin(plugin_type):
        raise PluginError(f"{origin} declares a {attribute} that is not a plugin: {plugin_type!r}")
    return plugin_type()


def load_plugin(host: Host, injector: Injector, import_string: str, attribute: str = PLUGIN_ATTRIBUTE) -> Plugin:
    """Import ``import_string``, build its plugin, and attach it.

    Attaching goes through the injector: whatever the plugin's ``attach``
    annotates is resolved and handed over. The host is not touched here -- it is
    only ever a value the injector hands to the plugin that asked for it.
    """
    module = importlib.import_module(import_string)
    plugin = declared_plugin(module, import_string, attribute)
    injector.call(plugin.attach)
    return plugin


def mount_plugins(
    host: Host, injector: Injector, import_strings: Sequence[str], attribute: str = PLUGIN_ATTRIBUTE
) -> list[Plugin]:
    """Load and attach every plugin named, in the order given.

    ``import_strings`` are the modules to load, and the whole of the decision:
    nothing is discovered here, and nothing is loaded that was not named. Naming
    a plugin makes it required -- see :func:`load_plugin` for what raises.
    """
    return [load_plugin(host, injector, import_string, attribute) for import_string in import_strings]


def detach_plugin(host: Host, injector: Injector, plugin: Plugin) -> None:
    """Take one plugin's component back off the host.

    The same injector, so the plugin sees the same host coming off as it saw
    going on -- which is the whole of why this goes through injection rather than
    being a method call with an argument.
    """
    injector.call(plugin.detach)
