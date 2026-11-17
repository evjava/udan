"""Plugin tests: a plugin is a Provider, is built from nothing, and attaches through the injector.

Nothing here imports a framework, and that is the point. The host is a list, the
component is a string, and the injector is given the host to offer -- so every
assertion below is about what the framework's base class and the loader's calling
convention do, not about what some framework does for them. What `attach` and
`detach` mean for a real app is asserted wherever a concrete plugin is tested,
never here.
"""

import pytest

from udan.decompof import Plugin, make_container, provide
from udan.decompof.injector import Injector, UnresolvableDependencyError


class ListPlugin(Plugin):
    """A host that holds what it is given, found again by identity."""

    def attach(self, host: list) -> None:
        host.append(self.config)

    def detach(self, host: list) -> None:
        host[:] = [item for item in host if item != self.config]


class AppendingPlugin(ListPlugin):
    """The same, but it wants a second dependency to prove more than one resolves."""

    def attach(self, host: list, suffix: str) -> None:
        host.append(self.config + suffix)


def test_a_plugin_that_declares_nothing_is_still_buildable():
    """attach/detach are no-ops on the base: a declarations-only plugin owes no verbs."""

    class NoPlugin(Plugin):
        pass

    plugin = NoPlugin()
    plugin.attach()
    plugin.detach()


def test_a_plugin_is_a_provider_its_declarations_join_the_wiring():
    """The base is a Provider: what a plugin declares with provide is container wiring."""

    class ContributingPlugin(Plugin):
        @provide
        def suffix(self) -> str:
            return "-suffix"

    assert make_container(ContributingPlugin()).get(str) == "-suffix"


def test_a_plugin_declares_no_configuration_by_default():
    assert ListPlugin().config is None


def test_a_plugin_defines_its_own_constructor_arguments():
    """The loader builds from nothing, so any arguments a plugin takes are its own."""

    class Configured(ListPlugin):
        def __init__(self, name: str = "default") -> None:
            self.config = name

    assert Configured().config == "default"
    assert Configured(name="called-something").config == "called-something"


def test_a_constructor_requiring_an_argument_cannot_be_built_from_nothing():
    """Legal Python, and unloadable: the loader calls a constructor with no arguments."""

    class NeedsName(ListPlugin):
        def __init__(self, name: str) -> None:
            self.config = name

    with pytest.raises(TypeError):
        NeedsName()


def test_attach_puts_the_plugin_component_on_the_host():
    plugin, host = ListPlugin(), []
    plugin.config = "a"

    Injector().provide(host).call(plugin.attach)

    assert host == ["a"]


def test_detach_takes_the_plugin_component_back_off():
    plugin, host = ListPlugin(), []
    plugin.config = "a"

    injector = Injector().provide(host)
    injector.call(plugin.attach)
    injector.call(plugin.detach)

    assert host == []


def test_attach_and_detach_are_resolved_by_annotation_not_by_name():
    """The parameter could be called anything; what matters is what it is typed as."""

    class OddlyNamed(ListPlugin):
        def attach(self, somewhere: list) -> None:
            somewhere.append(self.config)

    plugin, host = OddlyNamed(), []
    plugin.config = "a"

    Injector().provide(host).call(plugin.attach)

    assert host == ["a"]


def test_more_than_one_dependency_is_resolved():
    plugin, host = AppendingPlugin(), []
    plugin.config = "a"

    Injector().provide(host, "-suffix").call(plugin.attach)

    assert host == ["a-suffix"]


def test_an_annotation_nothing_provides_fails_before_attach_runs():
    """The startup fails, not the plugin: a plugin never runs half built."""

    class WantsUnknown(ListPlugin):
        def attach(self, nowhere: dict) -> None:
            raise AssertionError("the injector must not call attach it cannot satisfy")

    with pytest.raises(UnresolvableDependencyError, match="nowhere"):
        Injector().provide([]).call(WantsUnknown().attach)


def test_the_same_injector_resolves_detach_so_the_host_is_the_same_one():
    """A plugin sees the same host coming off as it saw going on."""

    class Seen(ListPlugin):
        hosts: list[object] = []

        def attach(self, host: list) -> None:
            self.hosts.append(host)

        def detach(self, host: list) -> None:
            self.hosts.append(host)

    plugin, host = Seen(), []
    injector = Injector().provide(host)
    injector.call(plugin.attach)
    injector.call(plugin.detach)

    assert plugin.hosts == [host, host]
