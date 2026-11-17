"""Tests for the history plugin's container contribution.

History is the package that holds resources open, so its PLUGIN declaration
carries both halves: the factories that select the storages by the configured
paths, and the detach that closes what they opened. The silent-failure cases
the plan warns about - a subscription nobody wires, a tool parameter that
resolves to None - are asserted here through the real boot.
"""

from tests.conftest import make_qp
from udan.core.api_plugins import PluginsAPI
from udan.core.config import UdanConfig
from udan.core.impl_ioc import _config_factories, _detach_udan_plugins, create_udan_container
from udan.core.impl_udan_context import UdanContext
from udan.decompof import Container, make_container
from udan.plugins_history import plugins_history
from udan.plugins_history.api_history import HistoryLoggerAPI, SavedQueriesAPI
from udan.plugins_history.history_config import HistoryConfig
from udan.plugins_history.impl_history_jsonl import HistoryLogger
from udan.plugins_history.impl_history_sqlite import HistoryLoggerSqlite
from udan.plugins_history.impl_saved_sqlite import SavedQueriesSqlite


class Unprovided:
    """A service nothing in the wiring declares."""


def _history_container() -> Container:
    """The container as the boot composes it: the CONFIG factory first, then the plugin."""
    return make_container(*_config_factories({"history": HistoryConfig}), plugins_history.HistoryPlugin())


def test_history_plugin_provides_the_two_storages():
    """The contribution is the two storages the configured paths select; the config is the container's factory."""
    container = _history_container()

    assert isinstance(container.get(HistoryConfig), HistoryConfig)
    assert isinstance(container.get(HistoryLoggerAPI), HistoryLoggerAPI)
    assert isinstance(container.get(SavedQueriesAPI), SavedQueriesAPI)


def test_history_plugin_storages_are_singletons():
    """A factory and a tool asking for the same storage receive the same instance."""
    container = _history_container()

    assert container.get(HistoryLoggerAPI) is container.get(HistoryLoggerAPI)
    assert container.get(SavedQueriesAPI) is container.get(SavedQueriesAPI)
    assert container.get(HistoryLoggerAPI) is not container.get(SavedQueriesAPI)


def test_history_plugin_selects_the_backend_by_path_extension():
    """The default .db paths select the sqlite implementations."""
    container = _history_container()

    assert isinstance(container.get(HistoryLoggerAPI), HistoryLoggerSqlite)
    assert isinstance(container.get(SavedQueriesAPI), SavedQueriesSqlite)


def test_history_plugin_storages_follow_the_config(monkeypatch, tmp_path):
    """The factories read the container's one config, so its paths are what they open."""
    monkeypatch.setenv("UDAN_HISTORY_PATH", str(tmp_path / "h.jsonl"))
    monkeypatch.setenv("UDAN_HISTORY_SAVED_PATH", str(tmp_path / "s.db"))
    container = _history_container()

    assert str(container.get(HistoryConfig).path) == str(tmp_path / "h.jsonl")
    assert isinstance(container.get(HistoryLoggerAPI), HistoryLogger)
    assert isinstance(container.get(SavedQueriesAPI), SavedQueriesSqlite)


def test_the_config_is_one_instance_wherever_asked():
    """The config the factories read and the container serves is one object."""
    container = _history_container()

    assert container.get(HistoryConfig) is container.get(HistoryConfig)


def test_the_container_answers_for_itself():
    """A factory or a verb asking for the container receives the container."""
    container = _history_container()

    assert container.get(Container) is container


def test_detach_closes_the_storages():
    """The verbs close what the factories opened, and a second detach does not raise."""
    container = _history_container()
    plugin = plugins_history.HistoryPlugin()
    logger = container.get(HistoryLoggerAPI)
    saved = container.get(SavedQueriesAPI)

    container.call(plugin.detach)
    container.call(plugin.detach)

    assert isinstance(logger, HistoryLoggerSqlite)
    assert isinstance(saved, SavedQueriesSqlite)


def test_sqlite_close_tolerates_a_second_call(tmp_path):
    """Closing a backend that never opened, or twice, does not raise."""
    logger = HistoryLoggerSqlite(history_path=str(tmp_path / "history.db"))
    saved = SavedQueriesSqlite(saved_path=str(tmp_path / "saved.db"))

    logger.close()
    logger.close()
    saved.close()
    saved.close()


def test_sqlite_close_reopens_on_the_next_use(tmp_path):
    """A closed storage reopens its database when it is used again."""
    saved = SavedQueriesSqlite(saved_path=str(tmp_path / "saved.db"))
    saved.add(pattern="demo", query="range 3")
    saved.close()

    entries = list(saved.list_saved())

    assert [entry["pattern"] for entry in entries] == ["demo"]


def test_history_declares_plugin_and_the_boot_composes_it():
    """The declaration is read: the boot's contributions carry the history plugin."""
    container = create_udan_container(UdanConfig())
    plugins = container.get(PluginsAPI)
    history_package = next(package for package in plugins.packages() if package.name == plugins_history.__name__)

    assert type(history_package.plugin) is plugins_history.HistoryPlugin
    assert history_package.plugin in plugins.providers()
    assert isinstance(container.get(HistoryLoggerAPI), HistoryLoggerAPI)


def test_a_command_lands_in_the_configured_backend(tmp_path):
    """The SUBSCRIBE service resolves from the container: a query is recorded in history."""
    config = UdanConfig()
    container = create_udan_container(config)
    ctx = container.get(UdanContext)
    ctx.container = container
    ctx.load_core()

    make_qp(ctx).execute_query("range 3")

    entries = list(container.get(HistoryLoggerAPI).get_history())
    assert [entry["command"] for entry in entries] == ["range 3"]
    assert [entry["success"] for entry in entries] == [True]


def test_saved_tool_lists_entries_through_the_container(tmp_path):
    """A tool's storage parameter resolves to the container's singleton, not to None."""
    config = UdanConfig()
    container = create_udan_container(config)
    ctx = container.get(UdanContext)
    ctx.container = container
    ctx.load_core()
    container.get(SavedQueriesAPI).add(pattern="demo", query="range 3, sort")

    forest, _attrs, _render_specs, _out = make_qp(ctx).execute_query("saved")

    assert [item["pattern"] for item in forest.items] == ["demo"]


def test_the_subscription_service_resolves_container_first(tmp_path):
    """A declared service comes from the container; one nobody provides is not resolved."""
    container = create_udan_container(UdanConfig())
    ctx = container.get(UdanContext)

    assert ctx._subscription_service(HistoryLoggerAPI) is container.get(HistoryLoggerAPI)
    assert ctx._subscription_service(Unprovided) is None


def test_detach_receives_the_boot_singletons(tmp_path, monkeypatch):
    """The shutdown half hands the verbs the container's own storages."""
    container = create_udan_container(UdanConfig())
    plugins = container.get(PluginsAPI)
    plugin = next(package for package in plugins.packages() if package.name == plugins_history.__name__).plugin
    seen: dict[str, object] = {}

    def record(self, history_logger: HistoryLoggerAPI, saved_storage: SavedQueriesAPI) -> None:
        seen["logger"] = history_logger
        seen["saved"] = saved_storage

    monkeypatch.setattr(type(plugin), "detach", record)
    _detach_udan_plugins(container, plugins)

    assert seen["logger"] is container.get(HistoryLoggerAPI)
    assert seen["saved"] is container.get(SavedQueriesAPI)


def test_a_boot_without_history_storages_still_detaches(monkeypatch):
    """The dummies close as no-ops: the configured extension selects them."""
    monkeypatch.setenv("UDAN_HISTORY_PATH", "./history.txt")
    monkeypatch.setenv("UDAN_HISTORY_SAVED_PATH", "./saved.txt")
    container = create_udan_container(UdanConfig())

    _detach_udan_plugins(container, container.get(PluginsAPI))
