"""Attributes plugin: the kind service and the package's container contribution.

The package's contribution is the attribute domain as a whole: the storage the
values land in, the runtime that computes them (plugins_attributes provides both
as services), the chain-context factory that answers the walk with the computing
context, and the hand-outs that wire the runtime in - the chain routing gets the
handler for the attribute chain steps, the injector gets the runtime as the global
dependency attribute-taking tools resolve. A host that leaves this package
out builds the container without any of them: the attribute kind is not in the
vocabulary, no factory computes, and the walk's own store-only context answers
reads with the advice that says what is missing.
"""

from __future__ import annotations

from pathlib import Path

from udan.attributes.api_attribute_cache import AttributeCacheAPI
from udan.attributes.api_attribute_runtime import AttributeRuntimeAPI
from udan.attributes.api_attribute_storage import AttributeStorageAPI
from udan.attributes.impl_attribute_cache import AttributeCache
from udan.attributes.impl_attribute_contexts import AttributesChainContextFactory
from udan.attributes.impl_attribute_runtime import AttributeRuntimeImpl
from udan.attributes.impl_attribute_storage import AttributeStorage
from udan.core.api_chain_context import ChainContextFactoryAPI
from udan.core.api_chain_routing import ChainRoutingAPI
from udan.core.api_logger import LoggerAPI
from udan.core.config import UdanConfig
from udan.core_tools_loading.api_function_injector import FunctionInjectorAPI
from udan.core_tools_loading.api_tools_registry import ToolsRegistryAPI
from udan.decompof import Plugin, decorate, provide


class AttributeRuntime(AttributeRuntimeImpl):
    """The package's kind service.

    A kind service declares its KINDS where the container harvests them - a plugin
    package's plugins_*.py modules - and the KINDS themselves live on the contract
    (AttributeRuntimeAPI, this package's own); the calculation lives on the base class.
    """


class AttributesPlugin(Plugin):
    """The package's container contribution.

    Providing the storage and the runtime contributes the place attribute values
    live and the service that computes them. The decorations are what make the
    runtime reachable without any core module naming it: the chain routing hands
    attribute groups to it, the walk's per-query contexts come from its factory,
    and the injector holds it as the optional attribute service.
    """

    @provide
    def attribute_cache(
        self,
        config: UdanConfig,
        logger: LoggerAPI,
    ) -> AttributeCacheAPI:
        """Create the attribute cache."""
        cache_attrs_path = str(Path(config.udan_cache_dir) / "attrs") if config.udan_cache_dir else None
        return AttributeCache(cache_path=cache_attrs_path or "", logger=logger)

    @provide
    def attribute_storage(self) -> AttributeStorageAPI:
        """Create the attribute storage as an APP-scoped singleton.

        The store the runtime writes computed values into, the render engine reads
        them from, and the walk's context stores what a chain sets itself in: one
        store, so the values survive the query they were set in.
        """
        return AttributeStorage()

    @provide
    def attribute_runtime(
        self,
        registry: ToolsRegistryAPI,
        attribute_storage: AttributeStorageAPI,
        cache: AttributeCacheAPI,
    ) -> AttributeRuntime:
        """Create the attribute runtime: the service that computes attribute values."""
        return AttributeRuntime(registry=registry, attribute_storage=attribute_storage, cache=cache)

    @provide
    def attribute_runtime_api(self, runtime: AttributeRuntime) -> AttributeRuntimeAPI:
        """The runtime under its contract, for the consumers that resolve it directly."""
        return runtime

    @decorate
    def routing_with_attributes(self, routing: ChainRoutingAPI, attribute_runtime: AttributeRuntime) -> ChainRoutingAPI:
        """Hand the runtime to the routing as the handler of the attribute chain steps."""
        return routing.with_handler(attribute_runtime)

    @decorate
    def chain_context_factory_with_attributes(
        self, factory: ChainContextFactoryAPI, attribute_runtime: AttributeRuntime
    ) -> ChainContextFactoryAPI:
        """Answer the walk's per-query context requests with the computing factory."""
        return AttributesChainContextFactory(attribute_runtime)

    @decorate
    def injector_with_attributes(
        self, injector: FunctionInjectorAPI, attribute_runtime: AttributeRuntime
    ) -> FunctionInjectorAPI:
        """Give the injector the runtime as the global dependency attributes resolve."""
        return injector.with_global_dependency(AttributeRuntimeAPI, attribute_runtime)


DOMAIN = "attributes"
PLUGIN = AttributesPlugin
