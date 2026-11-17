"""Loader tests.

Nothing here imports a framework, and that is the point: the loader under test is
`udan.decompof.loader`, the host is a list, and the plugins are written into a
temporary directory and put on the path. If the loader needed a framework to load a
plugin for a list, these tests could not exist -- so they are the proof that it
does not. They name no real plugin: the module they load is written by `publish`
into `tmp_path`.
"""

import sys

import pytest

from udan.decompof.injector import Injector, UnresolvableDependencyError
from udan.decompof.loader import PluginError, detach_plugin, mount_plugins

#: A stand-in plugin for a list-shaped host. It annotates `host`, so the injector
#: is what hands it over -- the loader never does. Built from nothing, it takes
#: its name from the module it was published under, which is how the tests tell
#: one published module from another.
PLUGIN_SOURCE = """
from udan.decompof.plugin import Plugin


class TmpPlugin(Plugin):
    def attach(self, host: list) -> None:
        host.append(f"{type(self).__module__}@{id(host)}")

    def detach(self, host: list) -> None:
        host[:] = [item for item in host if item != f"{type(self).__module__}@{id(host)}"]


PLUGIN = TmpPlugin
"""

#: A plugin that reads its configuration from its own module. The loader passed
#: it nothing; the label came from wherever the plugin found it.
CONFIGURED_SOURCE = """
from udan.decompof.plugin import Plugin

LABEL = "from-own-source"


class OwnConfigPlugin(Plugin):
    def __init__(self) -> None:
        self.label = LABEL

    def attach(self, host: list) -> None:
        host.append(self.label)

    def detach(self, host: list) -> None:
        host.remove(self.label)


PLUGIN = OwnConfigPlugin
"""

#: A plugin whose constructor needs an argument. The loader builds from nothing,
#: so this is the plugin's own constructor raising, not the loader wrapping it.
NEEDS_ARGUMENT_SOURCE = """
from udan.decompof.plugin import Plugin


class NeedsArgumentPlugin(Plugin):
    def __init__(self, label: str) -> None:
        self.label = label

    def attach(self, host: list) -> None:
        host.append(self.label)

    def detach(self, host: list) -> None:
        host.remove(self.label)


PLUGIN = NeedsArgumentPlugin
"""


def publish(tmp_path, monkeypatch, name: str, source: str = PLUGIN_SOURCE) -> str:
    """Write a plugin module into a temp dir, put it on the path, return its name."""
    (tmp_path / f"{name}.py").write_text(source)
    monkeypatch.syspath_prepend(tmp_path)
    return name


@pytest.fixture
def plugin_name(tmp_path, monkeypatch) -> str:
    return publish(tmp_path, monkeypatch, "tmp_plugin")


@pytest.fixture
def unloaded_plugin(plugin_name):
    """Drop the module from the import cache so import attempts are observable."""
    saved = sys.modules.pop(plugin_name, None)
    try:
        yield plugin_name
    finally:
        if saved is not None:
            sys.modules[plugin_name] = saved


def host() -> list:
    return []


def loaded(host: list, injector: Injector, names: list[str]) -> object:
    [plugin] = mount_plugins(host, injector, names)
    return plugin


def test_nothing_named_means_nothing_loaded():
    assert mount_plugins(host(), Injector(), []) == []


def test_a_named_plugin_is_attached_to_the_host(plugin_name):
    target = host()

    loaded(target, Injector().provide(target), [plugin_name])

    assert len(target) == 1


def test_attach_is_called_through_the_injector(plugin_name):
    """The host the plugin saw is the one it was offered, not a copy of it."""
    target = host()

    loaded(target, Injector().provide(target), [plugin_name])

    assert target == [f"{plugin_name}@{id(target)}"]


def test_plugins_load_in_the_order_given(tmp_path, monkeypatch):
    first = publish(tmp_path, monkeypatch, "tmp_plugin_first")
    second = publish(tmp_path, monkeypatch, "tmp_plugin_second")
    target = host()

    mount_plugins(target, Injector().provide(target), [first, second])

    assert target == [f"{first}@{id(target)}", f"{second}@{id(target)}"]


def test_the_host_is_passed_through_untouched(plugin_name):
    """The loader never looks inside the host; the injector hands it over whole."""
    first, second = host(), host()

    mount_plugins(first, Injector().provide(first), [plugin_name])
    mount_plugins(second, Injector().provide(second), [plugin_name])

    assert first != second  # each host saw itself, not some shared one


def test_a_loaded_plugin_comes_back_off_whole(plugin_name):
    target = host()
    injector = Injector().provide(target)

    plugin = loaded(target, injector, [plugin_name])
    detach_plugin(target, injector, plugin)

    assert target == []


def test_a_plugin_reads_its_own_configuration(tmp_path, monkeypatch):
    """The loader passed nothing; the label is the plugin's own doing."""
    name = publish(tmp_path, monkeypatch, "tmp_configured", CONFIGURED_SOURCE)
    target = host()

    loaded(target, Injector().provide(target), [name])

    assert target == ["from-own-source"]


def test_a_constructor_needing_an_argument_raises_untouched(tmp_path, monkeypatch):
    """A plugin built from nothing that wants arguments is the plugin's own TypeError."""
    name = publish(tmp_path, monkeypatch, "tmp_needs_arg", NEEDS_ARGUMENT_SOURCE)
    target = host()

    with pytest.raises(TypeError, match="label"):
        mount_plugins(target, Injector().provide(target), [name])


def test_the_plugin_attribute_is_a_choice(tmp_path, monkeypatch):
    """`PLUGIN` is the convention, not a requirement."""
    renamed = PLUGIN_SOURCE.replace("PLUGIN = TmpPlugin", "LOAD_ME = TmpPlugin")
    name = publish(tmp_path, monkeypatch, "tmp_renamed", renamed)
    target = host()

    [plugin] = mount_plugins(target, Injector().provide(target), [name], attribute="LOAD_ME")

    assert len(target) == 1
    assert type(plugin).__name__ == "TmpPlugin"


def test_a_module_declaring_no_plugin_fails_loudly(tmp_path, monkeypatch):
    name = publish(tmp_path, monkeypatch, "tmp_bare", "x = 1\n")
    target = host()

    with pytest.raises(PluginError, match="declares no PLUGIN"):
        mount_plugins(target, Injector().provide(target), [name])


def test_a_module_declaring_the_wrong_thing_fails_loudly(tmp_path, monkeypatch):
    name = publish(tmp_path, monkeypatch, "tmp_wrong", f"{PLUGIN_SOURCE}\n\nPLUGIN = 'not a plugin'\n")
    target = host()

    with pytest.raises(PluginError, match="not a plugin"):
        mount_plugins(target, Injector().provide(target), [name])


def test_an_attach_asking_for_an_unknown_type_fails_before_it_runs(tmp_path, monkeypatch):
    """The plugin is never half-run: an unsatisfiable annotation is a startup failure."""
    wants_unknown = PLUGIN_SOURCE.replace(
        "PLUGIN = TmpPlugin",
        """
class WantsUnknown(Plugin):
    def attach(self, nowhere: dict) -> None:
        raise AssertionError("the loader must not call attach it cannot satisfy")

    def detach(self) -> None:
        raise AssertionError("never attached")


PLUGIN = WantsUnknown""",
    )
    name = publish(tmp_path, monkeypatch, "tmp_unknown", wants_unknown)
    target = host()

    with pytest.raises(UnresolvableDependencyError, match="nowhere"):
        mount_plugins(target, Injector().provide(target), [name])


def test_an_unnamed_module_is_never_imported(unloaded_plugin):
    mount_plugins(host(), Injector(), [])

    assert unloaded_plugin not in sys.modules


def test_a_named_module_is_imported(unloaded_plugin):
    """A real import happens, rather than a hit on a module some other test cached."""
    target = host()

    mount_plugins(target, Injector().provide(target), [unloaded_plugin])

    assert unloaded_plugin in sys.modules


def test_a_missing_named_module_fails_loudly():
    target = host()

    with pytest.raises(ModuleNotFoundError):
        mount_plugins(target, Injector().provide(target), ["tmp_plugin_that_does_not_exist"])
