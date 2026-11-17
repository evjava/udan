"""Characterization tests for the udan injector's injection contract.

The facts the tool pipeline relies on, stated against the public surface:
what a wrapped function receives, what its refined signature hides, and the order
the answers come in. The instances are real services, so a change to classification
or resolution shows up here before it shows up in a tool schema.
"""

import inspect
from collections.abc import Sequence
from typing import Any

import pytest

from udan.attributes.api_attribute_storage import AttributeStorageAPI
from udan.core.api_chain_context import ChainContextAPI
from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_forests import Forest
from udan.core.api_logger import LoggerAPI
from udan.core.impl_debug_logger import DebugLogger
from udan.core.impl_dependencies_registry import DependenciesRegistry
from udan.core.impl_exec_context import ExecContext
from udan.core.impl_ioc import IOC, _config_factories
from udan.core_tools_loading.api_function_injector import FunctionInjectorAPI
from udan.decompof import Container, Provider, make_container, provide
from udan.plugins_history.api_history import DummySavedQueries, SavedQueriesAPI
from udan.plugins_history.history_config import HistoryConfig
from udan.plugins_history.plugins_history import HistoryPlugin

PLUGIN_MODULE = "udan.plugins_history.plugins_history"

GLOBAL_DEPENDENCIES: dict[type, Any] = {LoggerAPI: DebugLogger(log_time=False)}


class StorageStub(AttributeStorageAPI):
    """A stand-in storage: only its identity matters to the resolution below."""


class StorageProvider(Provider):
    """The attributes package's storage, as its container contribution serves it."""

    @provide
    def storage(self) -> AttributeStorageAPI:
        return StorageStub()


def make_injector_container(providers: Sequence[Provider] = (HistoryPlugin(), StorageProvider())) -> Container:
    """A container over the services the injector resolves through: the CONFIG factories, then the plugins'."""
    return make_container(*_config_factories({"history": HistoryConfig}), *providers)


def make_injector(with_providers: bool = True, container: Container | None = None) -> FunctionInjectorAPI:
    """The injector as impl_ioc builds it: the container, the registry, the per-query key."""
    registry = DependenciesRegistry()
    if with_providers:
        registry.register_from_module(PLUGIN_MODULE)
    resolved = make_injector_container() if container is None else container

    return IOC()._udan_injector(
        dependency_registry=registry,
        container=resolved,
        dependencies=dict(GLOBAL_DEPENDENCIES),
    )


def make_ctx() -> ExecContext:
    return ExecContext(DebugLogger(log_time=False))


class WidgetDescriptor:
    """A descriptor type: data the caller owns, not a dependency."""


def wants_logger(logger: LoggerAPI) -> LoggerAPI:
    return logger


def wants_optional_logger(logger: LoggerAPI | None = None) -> LoggerAPI | None:
    return logger


def wants_saved(saved: SavedQueriesAPI | None = None) -> SavedQueriesAPI | None:
    return saved


def wants_history_config(config: HistoryConfig) -> HistoryConfig:
    return config


def wants_storage(storage: AttributeStorageAPI | None = None) -> AttributeStorageAPI | None:
    return storage


def wants_storage_required(storage: AttributeStorageAPI) -> AttributeStorageAPI:
    return storage


def wants_forest(forest: Forest | None = None) -> Forest | None:
    return forest


def wants_descriptor(descriptor: WidgetDescriptor | None = None) -> WidgetDescriptor | None:
    return descriptor


def wants_chain(chain: ChainContextAPI | None = None) -> ChainContextAPI | None:
    return chain


def wants_chain_required(chain: ChainContextAPI) -> ChainContextAPI:
    return chain


def wants_ctx(ctx: ExecContextAPI | None = None, item: str = "") -> Any:
    return ctx


def takes_item(item: str) -> str:
    return item


def mixed(logger: LoggerAPI, config: HistoryConfig, forest: Forest | None = None, item: str = "") -> Any:
    return item


def test_an_api_typed_parameter_is_injected_from_the_globals():
    injector = make_injector()

    assert injector.wrap_function(wants_logger)() is GLOBAL_DEPENDENCIES[LoggerAPI]


def test_an_optional_annotation_is_injected_by_the_type_it_wraps():
    injector = make_injector()

    assert injector.wrap_function(wants_optional_logger)() is GLOBAL_DEPENDENCIES[LoggerAPI]


def test_a_plugin_module_type_is_resolved_through_the_container():
    """The history plugin's config is its container factory's singleton, not a registry provider's."""
    wrapped = make_injector().wrap_function(wants_history_config)

    assert isinstance(wrapped(), HistoryConfig)
    assert wrapped() is wrapped()


def test_the_query_dependency_answers_before_the_container():
    injector = make_injector()
    mine = DummySavedQueries()
    injector.set_dependency(SavedQueriesAPI, mine)

    assert injector.wrap_function(wants_saved)() is mine


def test_the_globals_answer_before_the_query_dependency():
    injector = make_injector(with_providers=False)
    query_logger = DebugLogger(log_time=False)
    injector.set_dependency(LoggerAPI, query_logger)

    assert injector.wrap_function(wants_logger)() is GLOBAL_DEPENDENCIES[LoggerAPI]


def test_a_container_key_resolves_from_the_container():
    """The storage the attributes package serves: the container's own instance, every time."""
    wrapped = make_injector().wrap_function(wants_storage)

    assert type(wrapped()) is StorageStub
    assert wrapped() is wrapped()


def test_a_declared_key_nothing_answers_and_no_default_raises():
    """A declared key with no answer anywhere raises instead of running degraded."""
    wrapped = make_injector(with_providers=False).wrap_function(wants_chain_required)

    with pytest.raises(RuntimeError, match="Could not inject dependency"):
        wrapped()


def test_a_missing_dependency_with_a_default_stands_aside():
    wrapped = make_injector(with_providers=False).wrap_function(wants_chain)

    assert wrapped() is None


def test_a_udan_data_type_is_not_injected():
    forest = Forest(items=["a"], depths=[0])
    wrapped = make_injector().wrap_function(wants_forest)

    assert wrapped(forest=forest) is forest
    assert "forest" in inspect.signature(wrapped).parameters


def test_a_descriptor_typed_parameter_is_not_injected():
    descriptor = WidgetDescriptor()
    wrapped = make_injector().wrap_function(wants_descriptor)

    assert wrapped(descriptor=descriptor) is descriptor
    assert "descriptor" in inspect.signature(wrapped).parameters


def test_the_refined_signature_hides_only_the_injected_parameters():
    wrapped = make_injector().wrap_function(mixed)

    assert list(inspect.signature(wrapped).parameters) == ["forest", "item"]


def test_the_refined_annotations_exclude_the_injected_parameters():
    wrapped = make_injector().wrap_function(mixed)

    assert list(wrapped.__annotations__) == ["forest", "item", "return"]
    assert wrapped.__annotations__["return"] is Any


def test_wrapping_twice_returns_the_same_function():
    injector = make_injector()
    wrapped = injector.wrap_function(wants_logger)

    assert injector.wrap_function(wrapped) is wrapped


def test_an_applier_style_call_without_a_ctx_parameter_drops_it():
    wrapped = make_injector().wrap_function(takes_item)

    assert wrapped(item="x", ctx=make_ctx()) == "x"


def test_a_function_declaring_ctx_receives_it():
    ctx = make_ctx()
    wrapped = make_injector().wrap_function(wants_ctx)

    assert wrapped(item="x", ctx=ctx) is ctx


def test_a_caller_supplied_value_wins_over_the_injection():
    injector = make_injector()
    mine = DebugLogger(log_time=False)

    assert injector.wrap_function(wants_logger)(logger=mine) is mine


def test_a_positionally_supplied_value_wins_over_the_injection():
    injector = make_injector()
    mine = DebugLogger(log_time=False)

    assert injector.wrap_function(wants_logger)(mine) is mine
