"""Tests for the plugin config registry and the udan_config aggregator.

The registry answers by plugin name, but the instances it serves are the
container's: the composition root synthesizes a factory per CONFIG
declaration, so `udan config`, a plugin factory and a tool all resolve the
same one instance per config per process.
"""

import pytest

from tests.conftest import make_qp, register_tools_from_module
from udan.core.api_config_registry import ConfigRegistryAPI
from udan.core.api_plugins import PluginsAPI
from udan.core.api_udan_context import UdanContextAPI
from udan.core.config import UdanConfig
from udan.core.impl_config_registry import ConfigRegistry
from udan.core.impl_ioc import create_udan_container
from udan.decompof import Container
from udan.plugins_history.history_config import HistoryConfig
from udan.plugins_tools_core import plugins_system


def _container(config: UdanConfig | None = None) -> Container:
    """The boot's container: its CONFIG factories are the sections this registry serves."""
    return create_udan_container(config or UdanConfig())


def _boot(config: UdanConfig | None = None) -> tuple[ConfigRegistry, Container]:
    """A boot and the registry over it: one container, its snapshot, its sections."""
    resolved = config or UdanConfig()
    container = create_udan_container(resolved)

    return ConfigRegistry(resolved, container.get(PluginsAPI), container), container


def _registry(config: UdanConfig | None = None) -> ConfigRegistry:
    """A registry over a boot."""
    return _boot(config)[0]


@pytest.fixture
def ctx_with_system():
    """Context with the system plugins (udan_config) registered."""
    container = _container()
    ctx = container.get(UdanContextAPI)
    ctx.container = container
    register_tools_from_module(ctx, plugins_system.__name__)
    return ctx


def test_registry_discovers_history_section():
    """Test that the default history plugin's CONFIG declaration becomes a section."""
    registry = _registry()

    assert "history" in registry.names()
    assert registry._has("history")


def test_registry_get_returns_validated_plugin_config():
    """Test that get returns the plugin's own config type."""
    registry = _registry()

    assert isinstance(registry.get("history"), HistoryConfig)


def test_registry_get_unknown_section_is_loud():
    """Test that asking for a section of an absent plugin fails loudly."""
    registry = _registry()

    with pytest.raises(KeyError, match="No plugin config section named 'nonexistent'"):
        registry.get("nonexistent")


def test_registry_serves_api():
    """Test that ConfigRegistry implements ConfigRegistryAPI."""
    assert isinstance(_registry(), ConfigRegistryAPI)


def test_registry_skips_modules_without_config():
    """Test that plugins without a CONFIG declaration have no section."""
    registry = _registry(UdanConfig(udan_plugin_modules=["udan.plugins_tools_demo"]))

    assert "demo" not in registry.names()


def test_registry_discovers_explicitly_enabled_plugin_sections():
    """Test that a plugin's CONFIG declaration becomes a section when its module is enabled explicitly."""
    registry = _registry(UdanConfig(udan_plugin_modules=["udan.plugins_history"]))

    assert "history" in registry.names()
    assert isinstance(registry.get("history"), HistoryConfig)


def test_registry_history_section_not_governed_by_plugin_modules(monkeypatch):
    """Test that history's section survives any module list: the package is part of udan.

    The section was droppable when the package was external (UDAN_PLUGIN_MODULES
    excluding it unloaded it); now Plugins discovers udan/plugins_history on every boot the
    way it discovers udan/operator*, so no module list takes the section away.
    """
    monkeypatch.setenv("UDAN_PLUGIN_MODULES", '["udan_plugins_example"]')
    registry = _registry()

    assert "history" in registry.names()
    assert "demo" not in registry.names()


def test_registry_section_reflects_env(monkeypatch, tmp_path):
    """Test that the section value comes from the environment, like the plugin's own."""
    history_path = tmp_path / "h.jsonl"
    monkeypatch.setenv("UDAN_HISTORY_PATH", str(history_path))
    registry = _registry()

    assert str(registry.get("history").path) == str(history_path)


def test_registry_serves_the_containers_instance():
    """Test that the section is the very instance the container serves, not a second one."""
    registry, container = _boot()

    assert registry.get("history") is container.get(HistoryConfig)


def test_registry_core_dump_has_no_history_fields():
    """Test that core config no longer owns the history plugin's paths."""
    registry = _registry()

    core = registry._core_dump()

    assert "udan_cache_dir" in core
    assert "udan_history_path" not in core
    assert "udan_saved_path" not in core


def test_udan_config_shows_core_and_history_sections(ctx_with_system):
    qp_with_system = make_qp(ctx_with_system)
    """Test that udan config groups core and plugin sections."""
    _, _, _, out = qp_with_system.execute_query("udan_config")

    assert "core" in out
    assert "udan_cache_dir" in out or "cache_dir" in out
    assert "history" in out
    assert "path: " in out
    assert "saved_path" in out


def test_udan_config_history_section_hides_env_file_bookkeeping(ctx_with_system):
    qp_with_system = make_qp(ctx_with_system)
    """Test that the ConfigBaseSettings bookkeeping field is not shown as a knob."""
    _, _, _, out = qp_with_system.execute_query("udan_config")

    assert "env_file" not in out
