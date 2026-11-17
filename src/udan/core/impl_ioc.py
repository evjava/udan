"""Inversion of Control container using udan.decompof.

This module defines the core components and their dependencies for the
UdanContext. create_udan_container composes them with the container
contributions of the enabled plugin packages (read through their PLUGIN
declarations) into the one container the runtime resolves from - a
package left out of udan_plugin_modules contributes no services. The packages
that contribute a Plugin attach here, once the wiring is validated, and
detach through _detach_udan_plugins, the shutdown half a host calls.
"""

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from udan.core.api_chain_context import ChainContextFactoryAPI
from udan.core.api_chain_routing import ChainRoutingAPI
from udan.core.api_config_registry import ConfigRegistryAPI
from udan.core.api_dependencies_registry import DependenciesRegistryAPI
from udan.core.api_descriptor_factory import DescriptorFactoryAPI
from udan.core.api_event_bus import EventBusAPI
from udan.core.api_logger import LoggerAPI
from udan.core.api_output_engine import OutputEngineAPI
from udan.core.api_plugins import PluginsAPI
from udan.core.api_query_processor import QueryProcessorAPI
from udan.core.api_symbols_env import SymbolsEnvAPI
from udan.core.api_type_system import TypeSystemAPI
from udan.core.api_types_registry import TypesRegistryAPI
from udan.core.api_udan_context import UdanContextAPI
from udan.core.api_variable_handler import VariableHandlerAPI
from udan.core.config import UdanConfig
from udan.core.impl_chain_context import DummyChainContextFactory
from udan.core.impl_chain_routing import ChainRouting
from udan.core.impl_config_registry import ConfigRegistry
from udan.core.impl_debug_logger import DebugLogger
from udan.core.impl_dependencies_registry import DependenciesRegistry
from udan.core.impl_descriptor_factory import DescriptorFactory
from udan.core.impl_event_bus import EventBus
from udan.core.impl_output_engine import NoOutputEngine
from udan.core.impl_plugins import Plugins
from udan.core.impl_query_processor import QueryProcessor
from udan.core.impl_symbols_env import SymbolsEnv
from udan.core.impl_type_system import DummyTypeSystem, TypeSystem
from udan.core.impl_types_registry import TypesRegistry
from udan.core.impl_udan_context import UdanContext
from udan.core.impl_udan_injector import PER_QUERY_KEY, ContainerSource, DeclaredKeysSource, RegistrySource
from udan.core.impl_variable_handler import VariableHandler
from udan.core_tools_loading.api_function_injector import FunctionInjectorAPI
from udan.core_tools_loading.api_tool_kinds import ToolKindsRegistryAPI
from udan.core_tools_loading.api_tools_loader import ToolsLoaderAPI
from udan.core_tools_loading.api_tools_registry import ToolsRegistryAPI
from udan.core_tools_loading.impl_function_injector import FunctionInjector
from udan.core_tools_loading.impl_tool_kinds import ToolKindsRegistry
from udan.core_tools_loading.impl_tools_loader import ToolsLoader
from udan.core_tools_loading.impl_tools_registry import ToolsRegistry
from udan.decompof import Container, Provider, make_container, provide


class IOC(Provider):
    """Provider for Udan components."""

    # Config marker - must be provided externally via context
    @provide
    def config(self) -> UdanConfig:
        raise RuntimeError(
            "UdanConfig must be provided to create_udan_container(). "
            "Use create_udan_container(config) with a UdanConfig instance."
        )

    # Core components - using functional style where possible
    @provide
    def logger(self, config: UdanConfig) -> LoggerAPI:
        return DebugLogger(log_time=config.udan_log_time)

    @provide
    def tool_kinds(self, plugins: PluginsAPI) -> ToolKindsRegistryAPI:
        """The tool kind vocabulary, built filled.

        Every kind service - a ToolKindService subclass - declares the kinds it
        owns as its `KINDS`, and the container registers them here, when the
        vocabulary is built. Which other services happen to be constructed first does
        not matter. The core owns no kind service: every kind - the chain kinds, the
        attribute kind, the render kind - is declared by the enabled plugin packages
        (the plugins snapshot answers which those are; a package left out of
        udan_plugin_modules contributes none), and a module loaded outside the
        configured packages - a test module - registers its kinds through
        ToolsRegistry.load_plugins.

        Returns:
            The vocabulary with the enabled packages' kinds registered
        """
        kinds = ToolKindsRegistry()
        for kind_service in plugins.kind_services():
            for kind in kind_service.KINDS:
                kinds.register(kind)
        return kinds

    @provide
    def registry(
        self,
        config: UdanConfig,
        logger: LoggerAPI,
        loader: ToolsLoaderAPI,
        tool_kinds: ToolKindsRegistryAPI,
    ) -> ToolsRegistryAPI:
        return ToolsRegistry(
            logger,
            loader,
            config.udan_tools_preferences_input,
            kinds=tool_kinds,
        )

    @provide
    def loader(
        self,
        config: UdanConfig,
        tool_kinds: ToolKindsRegistryAPI,
    ) -> ToolsLoaderAPI:
        """Create the tools loader."""
        if config.udan_cache_dir:
            cache_dir = str(Path(config.udan_cache_dir) / "loader")
        else:
            cache_dir = None
        # Use caching when cache_dir is available
        return ToolsLoader(
            cache_dir=cache_dir,
            use_cache=cache_dir is not None,
            kinds=tool_kinds,
        )

    @provide
    def symbols_env(self, config: UdanConfig, logger: LoggerAPI) -> SymbolsEnvAPI:
        return SymbolsEnv(str(config.udan_vars_path), logger)

    # QueryParserAPI is provided by the udan.parsing package (its PLUGIN
    # declaration), composed into the container by create_udan_container below.
    # The resolver's composition (QueryProcessorAPI, DescriptorFactoryAPI,
    # VariableHandlerAPI) is core: it binds parsed arguments into descriptors and
    # resolves variables - not parsing. The context takes the resolver: it runs
    # the steps of an execution after the parse (execute_query); the parser stays
    # the caller's - the context names no parsing package.

    # The value domains and the output step are domain packages' services the same
    # way: udan.attributes (part of udan, always composed) provides the attribute
    # storage and the runtime, udan.renders (part of udan, always composed) provides
    # the render engine - each reaching the seam it belongs to through its own
    # decorations. The core provides the seams and their fallbacks only.

    @provide
    def output_engine(self, logger: LoggerAPI) -> OutputEngineAPI:
        """Create the core's output engine: the one that answers with advice.

        Without an output-producing domain's service (udan.renders provides one
        on every normal boot) nothing turns a forest into text; the chain still
        applies, the output step fails with what is missing. A package that
        produces output decorates this key.
        """
        return NoOutputEngine(logger)

    @provide
    def chain_context_factory(self, registry: ToolsRegistryAPI) -> ChainContextFactoryAPI:
        """Create the core's chain-context factory: the one whose context only stores.

        Without a computing domain's service (udan.attributes provides one on
        every normal boot) nothing computes values; the walk still owes the chain handlers a context, and this
        one stores what a chain sets itself and answers computes with advice. A
        package that computes decorates this key.
        """
        return DummyChainContextFactory(registry)

    @provide
    def config_registry(self, config: UdanConfig, plugins: PluginsAPI, container: Container) -> ConfigRegistryAPI:
        """Create the plugin config registry.

        Serves the enabled packages' CONFIG declarations as validated config
        instances by plugin name (used by udan_config and by anything that
        needs a plugin's configuration) - resolved through the container, so
        the instance a tool or a factory sees is the one the registry reports.
        """
        return ConfigRegistry(config, plugins, container)

    @provide
    def event_bus(self) -> EventBusAPI:
        """Create the app event bus as a dependency-free component.

        Subscribers (e.g. the history logger) register themselves on the bus
        in their own providers; UdanContext emits CommandExecutedEvent after
        each command execution.
        """
        return EventBus()

    dependency_registry = provide(source=DependenciesRegistry, provides=DependenciesRegistryAPI)

    @provide
    def udan_injector(
        self,
        dependency_registry: DependenciesRegistryAPI,
        container: Container,
    ) -> FunctionInjectorAPI:
        """Create the udan injector over the container, the registry and the per-query key.

        No app-scoped service is a global here: a tool's parameter annotated
        with one resolves through the container source, lazily, into the
        container's one memo - the same instance a factory, a verb or the
        config registry reaches. A decoration extends the globals the same way
        it always did (with_global_dependency), and the globals still win over
        the sources.

        LoggerAPI is NOT a global dependency - it's created per-query. A service a
        package owns (the engine that applies the chain and the attribute runtime
        among them) is not one either: those are plugin packages' components, a host
        may not enable them, and nothing injects them from here - a package that
        needs its service injected adds it around this injector (its container
        provider decorates FunctionInjectorAPI).
        """
        return self._udan_injector(dependency_registry=dependency_registry, container=container)

    def _udan_injector(
        self,
        dependency_registry: DependenciesRegistryAPI,
        container: Container,
        dependencies: dict[type, Any] | None = None,
    ) -> FunctionInjector:
        """The injector as udan composes it: the container first, then the registry, then the declarations.

        The udan flavor is in the sources (impl_udan_injector), not in a subclass:
        with_global_dependency passes them through, so a plugin decoration that
        extends the globals re-uses the same resolution layers. The engine's
        per-query key (PER_QUERY_KEY) is the one declaration nothing answers at
        build time: the walk serves it, per query, through set_dependency.

        Args:
            dependency_registry: Dependency registry for the providers that stay
                registry-side (the per-query and plugins_only ones).
            container: The container the container source resolves through.
            dependencies: The globals, empty for the boot's own injector; a
                decoration extends them, and they win over the sources.

        Returns:
            The injector under the FunctionInjectorAPI contract.
        """
        return FunctionInjector(
            dependencies=dependencies or {},
            sources=[
                ContainerSource(container),
                RegistrySource(dependency_registry),
                DeclaredKeysSource([PER_QUERY_KEY]),
            ],
            context_param="ctx",
        )

    @provide
    def chain_routing(
        self,
        registry: ToolsRegistryAPI,
        tool_kinds: ToolKindsRegistryAPI,
    ) -> ChainRoutingAPI:
        """Build the chain routing over no core services: an open table.

        A service declares the kinds it owns as its `KINDS`; the routing indexes those
        declarations into a kind -> handler table. The core owns no kind service, so
        the core builds an empty table, and the table is open: a plugin package whose
        kinds form the chain (the chain kinds' packages, the attribute runtime among
        them) adds its handler around this routing (its container provider decorates
        ChainRoutingAPI). The completeness invariant is checked at the composition
        root (create_udan_container), once every decoration has applied - so a wiring
        gap fails the build instead of the query.

        Returns:
            The routing the orchestrator dispatches chain groups through
        """
        return ChainRouting(
            [],
            kinds=tool_kinds,
            registry=registry,
        )

    types_registry = provide(source=TypesRegistry, provides=TypesRegistryAPI)

    variable_handler = provide(source=VariableHandler, provides=VariableHandlerAPI)

    @provide
    def descriptor_factory(
        self,
        config: UdanConfig,
        symbols_env: SymbolsEnvAPI,
        registry: ToolsRegistryAPI,
    ) -> DescriptorFactoryAPI:
        """Create the descriptor factory: parsed arguments bound into descriptors."""
        return DescriptorFactory(
            symbols_env,
            config.udan_tools_variables_defaults,
            registry=registry,
        )

    @provide
    def query_processor(
        self,
        config: UdanConfig,
        registry: ToolsRegistryAPI,
        type_system: TypeSystemAPI,
        symbols_env: SymbolsEnvAPI,
        variable_handler: VariableHandlerAPI,
        descriptor_factory: DescriptorFactoryAPI,
    ) -> QueryProcessorAPI:
        """Create the query resolver: the Node -> Forest stage of an execution.

        The parser (str -> Node) is the parsing package's service; the context
        composes the two stages (execute_query on UdanContextAPI runs the
        resolve half and the engine half together).
        """
        return QueryProcessor(
            registry,
            type_system,
            config.udan_tools_preferences_input,
            symbols_env,
            variable_handler,
            descriptor_factory,
        )

    @provide
    def type_system(
        self, config: UdanConfig, registry: ToolsRegistryAPI, tool_kinds: ToolKindsRegistryAPI
    ) -> TypeSystemAPI:
        """Create the type system, or the dummy impl when the type system is disabled."""
        if config.udan_types_enabled:
            return TypeSystem(registry, kinds=tool_kinds)
        return DummyTypeSystem(registry)

    @provide
    def udan_context_api(  # noqa: PLR0913, PLR0917
        self,
        config: UdanConfig,
        registry: ToolsRegistryAPI,
        loader: ToolsLoaderAPI,
        dependency_registry: DependenciesRegistryAPI,
        bus: EventBusAPI,
        symbols_env: SymbolsEnvAPI,
        output: OutputEngineAPI,
        udan_injector: FunctionInjectorAPI,
        chain_routing: ChainRoutingAPI,
        chain_context_factory: ChainContextFactoryAPI,
        query_processor: QueryProcessorAPI,
        plugins: PluginsAPI,
        container: Container,
    ) -> UdanContextAPI:
        """Create the UdanContext with all dependencies injected, under its contract.

        The services a plugin package owns are not among them: the engine that applies
        the chain, the value domains and the output step are plugin packages'
        components, whose container contributions decorate the seams they belong to.
        A host that leaves a package out gets the core's own answer for its seam.
        The query language is not here either: the context names no parser - the
        caller parses (the CLI through the parsing package's parser) and hands it
        the node; the resolver it holds is core.

        The contract key is the one built here, and the one a plugin decorates - a
        plugin package cannot name the impl class - so udan_context below serves the
        same instance under the class key.
        """
        return UdanContext(
            config=config,
            registry=registry,
            loader=loader,
            dependency_registry=dependency_registry,
            bus=bus,
            symbols_env=symbols_env,
            output=output,
            udan_injector=udan_injector,
            query_processor=query_processor,
            chain_routing=chain_routing,
            chain_context_factory=chain_context_factory,
            plugins=plugins,
            container=container,
        )

    @provide
    def udan_context(self, udan_context_api: UdanContextAPI) -> UdanContext:
        """The context under its class: the same instance the contract key serves.

        The decorations a plugin applies land on the contract key, so the class key
        has to resolve through it - one context either way, not a decorated one and
        an undecorated twin.
        """
        assert isinstance(udan_context_api, UdanContext)
        return udan_context_api


def _config_factories(schemas: dict[str, type[BaseModel]]) -> list[Provider]:
    """The enabled packages' settings schemas, as the container's own factories.

    The schema's ``__init__`` is the factory: it reads the environment and
    .env the way every reader of the section does, so one validated instance
    per config per process is what the plugin's factories, its tools and
    ``udan config`` all reach. Declaring it is what makes the config
    injectable; not declaring it leaves the type unreachable.

    The declarations are synthesized onto a class built per boot - the schemas
    are whatever the enabled packages declared - so no instance carries them
    and no declaration reads instance state. Always synthesized, loudly: a
    package whose contribution also provides its schema key fails the build
    with the container's duplicate error, because CONFIG is the factory.

    Args:
        schemas: The enabled packages' CONFIG declarations, keyed by DOMAIN.

    Returns:
        One provider per schema, each registering its class under the schema key.
    """
    return [
        type(f"{schema.__name__}Factory", (Provider,), {"config": provide(source=schema, provides=schema)})()
        for schema in schemas.values()
    ]


def _detach_udan_plugins(container: Container, plugins: PluginsAPI) -> None:
    """Detach the plugins that attached at boot, in reverse package order.

    The shutdown half of create_udan_container, a module-level helper because
    the CLI or a test owns the shutdown, not the container: the container
    serves the verbs' dependencies, the caller decides when the process is
    done with them. Protected per the module-surface convention
    (check-no-global-non-protected-functions), not because it is internal to
    this module: the shutdown path is its caller.

    Args:
        container: The container create_udan_container built.
        plugins: The plugins snapshot the container was composed from.
    """
    for plugin in reversed([package.plugin for package in plugins.packages() if package.plugin is not None]):
        container.call(plugin.detach)


def create_udan_container(config: UdanConfig) -> Any:
    """Create a container with all Udan components.

    The enabled plugin packages are discovered before the container exists -
    the container is built from their PLUGIN declarations - so
    the plugins snapshot is composed as a context value: it wins over any
    factory claiming its key, and every component that asks for PluginsAPI
    gets the boot's own discovery, not a fresh scan.

    Args:
        config: UdanConfig instance for this context.

    Returns:
        The container. Use container.get(UdanContextAPI) to get the context.

    Raises:
        ValueError: If a chain-forming kind of the vocabulary has no handler - the
            routing is resolved here, complete with the plugins' decorations, so the
            chain invariant fails the build instead of the first query.
        TypeError: If an enabled package declares a PLUGIN that is
            not a Plugin (see impl_plugins).
        UnresolvableKeyError: If a plugin's attach or detach asks for a key
            nothing provides - the verbs' parameters are dependencies, so a
            mistake there fails the build like a factory's would.
        DuplicateProviderError: If a package's contribution provides the key of a
            schema it declares through CONFIG - the config is the container's
            factory, another factory for the same key is a duplicate.
    """
    # Discovery happens once: the packages, their declarations and their providers
    # are read here and asked for everywhere else.
    plugins = Plugins(config)
    # Validation is strict and the only mode: two providers claiming one key fail
    # the build instead of winning or losing by composition order without a sound.
    container = make_container(
        IOC(),
        *_config_factories(plugins.config_schemas()),
        *plugins.providers(),
        context={UdanConfig: config, PluginsAPI: plugins},
    )
    # The verbs join the validation before any of them runs: attach in package
    # order, detach in the reverse order _detach_udan_plugins applies.
    plugin_packages = [package.plugin for package in plugins.packages() if package.plugin is not None]
    for plugin in plugin_packages:
        container.check(plugin.attach)
        container.check(plugin.detach)
    for plugin in plugin_packages:
        container.call(plugin.attach)
    # The chain routing is complete here - the plugins' decorations applied at build,
    # the handlers their attach verbs added - so this is where "every chain-forming
    # kind has a handler" can be checked.
    container.get(ChainRoutingAPI).validate()
    return container
