"""Tests for the PLUGIN declaration: the read, the boot verbs.

The PLUGIN mechanism is impl_plugins' reader plus the container's check/call:
a package declares one contribution site, the boot validates the verbs'
dependencies with the rest of the wiring and attaches in package order, and
the shutdown half detaches in the reverse order.
"""

from types import ModuleType

import pytest

from tests.udan_plugins_boot.recording import RECORD
from udan.core.api_plugins import PluginsAPI
from udan.core.config import UdanConfig
from udan.core.impl_ioc import _config_factories, _detach_udan_plugins, create_udan_container
from udan.core.impl_plugins import Plugins, _plugin_package
from udan.decompof import DuplicateProviderError, Plugin, UnresolvableKeyError, make_container, provide
from udan.plugins_history.history_config import HistoryConfig
from udan.plugins_history.plugins_history import HistoryPlugin

BOOT_PACKAGE = "tests.udan_plugins_boot"
BROKEN_PACKAGE = "tests.udan_plugins_broken"


def _module_with(**attributes: object) -> ModuleType:
    """A plugin module carrying the declarations given, as a scan would hand one over."""
    module = ModuleType("udan.plugins_test_fake")
    for name, value in attributes.items():
        setattr(module, name, value)
    return module


def test_providers_serve_the_plugin_of_a_declaring_package():
    """The container contributions the snapshot hands the container are the plugins."""
    config = UdanConfig(udan_plugin_modules=[BOOT_PACKAGE])
    plugins = Plugins(config)

    assert plugins.packages()[-1].plugin is not None
    assert plugins.providers()[-1] is plugins.packages()[-1].plugin


def test_the_declared_class_is_built_from_nothing():
    """PLUGIN names the class; the scan instantiates it argument-free, like decompof's loader."""

    class DeclaredPlugin(Plugin):
        pass

    package = _plugin_package(_module_with(PLUGIN=DeclaredPlugin))

    assert type(package.plugin) is DeclaredPlugin
    assert DeclaredPlugin not in (package.plugin,)


def test_an_instance_is_not_a_declaration():
    """A module declares the class; instantiating it is the scan's job, not the module's."""

    class DeclaredPlugin(Plugin):
        pass

    with pytest.raises(TypeError, match="declares PLUGIN that is not a Plugin class: DeclaredPlugin"):
        _plugin_package(_module_with(PLUGIN=DeclaredPlugin()))


def test_a_non_plugin_declaration_fails_the_scan():
    """A PLUGIN that is not a Plugin fails the boot instead of contributing nothing."""
    with pytest.raises(TypeError, match="declares PLUGIN that is not a Plugin class: int"):
        _plugin_package(_module_with(PLUGIN=1))


def test_boot_attaches_in_package_order_and_detaches_in_reverse():
    """The verbs run once each, attach in package order, detach in the reverse order."""
    RECORD.clear()
    config = UdanConfig(udan_plugin_modules=[BOOT_PACKAGE])
    container = create_udan_container(config)
    plugins = container.get(PluginsAPI)

    assert RECORD == ["alpha:UdanConfig", "beta"]

    _detach_udan_plugins(container, plugins)

    assert RECORD == ["alpha:UdanConfig", "beta", "-beta", "-alpha"]


def test_a_verb_asking_for_a_key_nothing_provides_fails_the_build():
    """The verbs' parameters join the build validation, so a mistake there is a boot error."""
    config = UdanConfig(udan_plugin_modules=[BROKEN_PACKAGE])

    with pytest.raises(UnresolvableKeyError, match="nothing provides Unprovided: 'service' of .*attach asks for it"):
        create_udan_container(config)


def test_a_contribution_providing_its_own_config_key_fails_the_build():
    """CONFIG is the container's factory: another factory for the schema key is a duplicate."""

    class OwnConfigPlugin(HistoryPlugin):
        """Declares the factory the CONFIG declaration already synthesizes."""

        @provide
        def history_config(self) -> HistoryConfig:
            return HistoryConfig()

    container_providers = [*_config_factories({"history": HistoryConfig}), OwnConfigPlugin()]

    with pytest.raises(DuplicateProviderError, match="HistoryConfig is provided by both .*ConfigFactory"):
        make_container(*container_providers)
