import time
import traceback
from collections.abc import Callable, Sequence
from importlib import import_module
from typing import Any, Self

from udan.core.api_chain_context import ChainContextAPI, ChainContextFactoryAPI
from udan.core.api_chain_routing import ChainRoutingAPI, ChainStepServiceAPI
from udan.core.api_constants import NODE_ROOT_ITEM, NOLIMIT_TOKEN, OVERRIDES_OUTPUT
from udan.core.api_dependencies_registry import DependenciesRegistryAPI
from udan.core.api_event_bus import CommandExecutedEvent, CommandLogSink, EventBusAPI
from udan.core.api_exceptions import ExceptionWithAdvice, OverrideForestException
from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_forests import EMPTY_FOREST, Forest, Node
from udan.core.api_operators import OperatorDescriptor
from udan.core.api_output_engine import OutputEngineAPI
from udan.core.api_plugins import PluginsAPI
from udan.core.api_query_processor import QueryProcessorAPI
from udan.core.api_symbols_env import SymbolsEnvAPI
from udan.core.api_type_system import ForestTypeDescriptor
from udan.core.api_udan_context import UdanContextAPI
from udan.core.config import UdanConfig
from udan.core.impl_debug_logger import DebugLogger, _format_time_prefix
from udan.core.impl_exec_context import ExecContext
from udan.core.impl_plugins import _plugin_subscriptions
from udan.core.utils_chain import chain_declares_meta
from udan.core_tools_loading.api_function_injector import FunctionInjectorAPI
from udan.core_tools_loading.api_tools import ToolDescriptor, ToolMetadata
from udan.core_tools_loading.api_tools_loader import ToolsLoaderAPI
from udan.core_tools_loading.api_tools_registry import ToolsRegistryAPI
from udan.decompof import Container
from udan.renders.api_renders import RenderDescriptor


def _command_log_handler(service: CommandLogSink) -> Callable[[CommandExecutedEvent], None]:
    """Adapt a command log sink to the CommandExecutedEvent handler signature.

    Args:
        service: Command log sink (e.g. a history logger) to record emitted events.

    Returns:
        Handler callable for EventBus.subscribe.
    """

    def handler(event: CommandExecutedEvent) -> None:
        service.log(event.command, event.success, event.forest, event.error, event.comment)

    return handler


def _query_mentions_limit(node: Node) -> bool:
    """Check whether the user has explicit control over limiting.

    Only returns True when ``limit`` is the **last** operator in the
    pipeline, or when the ``:nolimit`` escape-hatch token is present.
    This ensures that intermediate uses of ``limit`` (e.g.
    ``(range 40; range 50, limit 10), sort``) do not suppress the
    global auto-limit.

    Strategy: collect all leaf strings that look like tool
    names (skip numbers, variable refs, structural keywords, named args).
    If the last such string is ``"limit"`` or the token contains
    ``nolimit``, the user is in control.
    """
    candidates: list[str] = []

    def _walk(n: Node) -> None:
        item = n.item
        if isinstance(item, str):
            if item == NOLIMIT_TOKEN:
                candidates.append(item)
            elif item in (NODE_ROOT_ITEM, "CHAIN") or item.startswith("$") or item.startswith(":"):
                pass
            elif item.startswith("--"):
                # Skip named arguments like --offset=10
                pass
            else:
                try:
                    int(item)
                except ValueError, TypeError:
                    candidates.append(item)
        elif isinstance(item, OperatorDescriptor) and item.name == "limit":
            candidates.append("limit")
        for child in n.children:
            _walk(child)

    _walk(node)
    if not candidates:
        return False
    last = candidates[-1]
    return last == "limit" or "nolimit" in last


class UdanContext(UdanContextAPI):
    def __init__(  # noqa: PLR0913, PLR0917
        self,
        config: UdanConfig,
        registry: ToolsRegistryAPI,
        loader: ToolsLoaderAPI,
        dependency_registry: DependenciesRegistryAPI,
        bus: EventBusAPI,
        symbols_env: SymbolsEnvAPI,
        output: OutputEngineAPI,
        udan_injector: FunctionInjectorAPI,
        query_processor: QueryProcessorAPI,
        chain_routing: ChainRoutingAPI,
        chain_context_factory: ChainContextFactoryAPI,
        plugins: PluginsAPI,
        container: Container,
    ) -> None:
        """Initialize UdanContext with injected dependencies.

        The services that compute values and produce output are not among the
        core's own: they are plugin packages' components, handed in as the
        OutputEngineAPI and the ChainContextFactoryAPI those packages decorate.
        A host that leaves a package out gets the core's own answers - storing
        works, computing and producing output fail with the advice that says
        what is missing.

        Args:
            config: UdanConfig instance.
            registry: Tools registry API.
            loader: Tools loader API.
            dependency_registry: Dependency provider registry.
            bus: Event bus API.
            symbols_env: Symbols environment API.
            output: Output engine API, the seam that turns an applied forest
                into text (the renders package's engine).
            udan_injector: Dependency injector for plugin functions.
            query_processor: The query resolver (Node -> Forest), the resolve
                half execute_query runs before the engine half; the parser
                that produces its node is not here - the caller parses.
            chain_routing: Chain routing API, the kind-to-service table the chain
                walk dispatches through; it also owns the output-overriding chain,
                whose handler a plugin package contributes.
            chain_context_factory: The factory of the per-query context the walk
                hands the chain handlers (the value domains' packages decorate it).
            plugins: The enabled packages and their declarations - the snapshot
                the container was composed from, which load_core reads instead
                of discovering the packages again.
            container: The container the boot composed, which the SUBSCRIBE
                wiring resolves a declared service through first and whose
                keys classify as injectable for the tools load_core loads.
        """
        self._config = config
        self._registry = registry
        self._loader = loader
        self._dependency_registry = dependency_registry
        self._bus = bus
        self._symbols_env = symbols_env
        self._output = output
        self._injector = udan_injector
        self._query_processor = query_processor
        self._chain_routing = chain_routing
        self._chain_context_factory = chain_context_factory
        self._plugins = plugins
        self._container = container
        # IOC log (shared app-scoped logger, holds startup logs) is included in
        # debug output only for the first query of the process; subsequent
        # queries in long-lived sessions (REPL) show only the query log.
        self._ioc_log_shown = False
        # Sticky `debug-time`: set when a query uses the marker; later queries
        # in this context keep showing the elapsed-time line
        self._debug_time_session = False
        # Plugin modules whose SUBSCRIBE declarations were already wired on the
        # bus, with the handlers each wiring made (detach unwires them): keyed
        # by module name, so re-registering a module does not duplicate
        self._wired_subscriptions: dict[
            str, list[tuple[type[CommandExecutedEvent], Callable[[CommandExecutedEvent], None]]]
        ] = {}

    @property
    def config(self) -> UdanConfig:
        """Get the udan configuration."""
        return self._config

    @property
    def registry(self) -> ToolsRegistryAPI:
        """Get the tools registry."""
        return self._registry

    @property
    def symbols_env(self) -> SymbolsEnvAPI:
        """Get the symbols environment."""
        return self._symbols_env

    @property
    def bus(self) -> EventBusAPI:
        """Get the event bus."""
        return self._bus

    @property
    def dependency_registry(self) -> DependenciesRegistryAPI:
        """Get the dependency provider registry."""
        return self._dependency_registry

    @property
    def injector(self) -> FunctionInjectorAPI:
        """Get the dependency injector."""
        return self._injector

    def _with_plugins(self, *plugin_modules) -> Self:
        self.registry.load_plugins(*plugin_modules, injector=self._injector)
        return self

    def _register_dependency_providers_from_module(self, module_name: str) -> None:
        """Register dependency providers from a module and wire its event subscriptions.

        Args:
            module_name: Name of the module to scan for providers.
        """
        self._dependency_registry.register_from_module(module_name)
        self._subscribe_module_events(module_name)

    def _subscribe_module_events(self, module_name: str) -> None:
        """Subscribe the named module's declared event services on the bus.

        The by-name path: the module's SUBSCRIBE declaration is read off the
        module here. The boot (load_core) does not take it - the packages'
        subscriptions were read once at container build and are handed over
        directly (see _wire_module_subscriptions).
        """
        module = import_module(module_name)
        self._wire_module_subscriptions(module_name, _plugin_subscriptions(module))

    def _subscription_service(self, service_type: type) -> Any:
        """Resolve the service a SUBSCRIBE declaration names: the container first, the registry second.

        A package contributing through the container serves its own services
        there; the registry answers what a package still declares through
        @annotated_dependency. Neither is a silent miss: an event declared
        with a service nobody provides stays unsubscribed, which the
        acceptance checks (a command landing in the backend) exist to catch.

        Args:
            service_type: The type the SUBSCRIBE declaration names.

        Returns:
            The service instance, or None when nothing provides it.
        """
        if service_type in self._container.provided_keys():
            return self._container.get(service_type)
        if self._dependency_registry.has_provider(service_type):
            return self._dependency_registry.resolve(service_type)
        return None

    def _wire_module_subscriptions(
        self, module_name: str, subscriptions: dict[type[CommandExecutedEvent], type]
    ) -> None:
        """Subscribe a module's declared event services on the bus, once per module.

        A plugin module declares SUBSCRIBE = {event_type: service_type}; the
        service is resolved (the container first, the dependency registry
        second) and subscribed to the event. Each module is wired once per
        context, so re-registering a module does not duplicate subscriptions,
        and what was wired is remembered per module for the teardown (detach).

        Args:
            module_name: Name of the module whose subscriptions are wired (the
                deduplication key).
            subscriptions: The module's SUBSCRIBE declaration, already read.
        """
        if module_name in self._wired_subscriptions:
            return
        wired: list[tuple[type[CommandExecutedEvent], Callable[[CommandExecutedEvent], None]]] = []
        for event_type, service_type in subscriptions.items():
            service = self._subscription_service(service_type)
            if service is None:
                continue
            handler = _command_log_handler(service)
            self._bus.subscribe(event_type, handler)
            wired.append((event_type, handler))
        self._wired_subscriptions[module_name] = wired

    def detach(self) -> None:
        """Unwire every SUBSCRIBE declaration this context wired, per module.

        The declaration stays declarative - it does not move into a plugin's
        attach/detach, which would hide it from the introspection that reads
        the module - and the teardown is the mirror image of the wiring: the
        same handlers, taken back off the same event types, so a host that
        shuts the context down leaves the bus as it found it.
        """
        for module_name, wired in self._wired_subscriptions.items():
            for event_type, handler in wired:
                self._bus.unsubscribe(event_type, handler)
        self._wired_subscriptions.clear()

    def load_core(self) -> Self:
        """Load the enabled plugin packages into the context.

        The packages come from the plugins snapshot the container was composed
        with - the "udan" core first, then the built-in and configured ones,
        each module scanned once at container build. Their dependency providers
        register, their SUBSCRIBE declarations wire on the bus, the loader's
        injectable types are set from them plus the container's own keys, and
        their tools load last - after the injectable types, so injected
        parameters stay out of the tool metadata schemas.

        Returns:
            Self for method chaining.
        """
        packages = self._plugins.packages()

        # Register dependency providers and wire event subscriptions, in package order
        for package in packages:
            self._dependency_registry.register_from_module(package.name)
            self._wire_module_subscriptions(package.name, package.subscriptions)

        # Update loader with injectable types from the packages' dependency modules:
        # types provided by @annotated_dependency must be injectable before metadata
        # is computed. The container's keys join them: a package contributing
        # through PLUGIN serves its services there, not through the registry, and
        # a tool annotating one stays out of its schema the same way.
        self._loader.set_injectable_types_from_modules([package.name for package in packages])
        self._loader.add_injectable_types(set(self._container.provided_keys()))

        # Load plugins AFTER injectable types are set, so injected parameters
        # are excluded from the tool metadata schemas
        self.registry.load_plugins(*(package.module for package in packages), injector=self._injector)

        return self

    def _register_metadata(self, metadata: ToolMetadata, fn: Callable[..., Any] | None = None) -> None:
        self.registry.register_metadata(metadata, self._injector, fn)

    def _register_many_metadatas(self, metadata_fns: list[tuple[ToolMetadata, Callable[..., Any]]]) -> None:
        self.registry.register_many_metadatas(metadata_fns, injector=self._injector)

    def output_forest(
        self,
        forest: Forest,
        requested: Sequence[ToolDescriptor],
        output_specs: Sequence[ToolDescriptor],
        exec_ctx: ExecContextAPI,
        frontend: str = "",
    ) -> str:
        """Produce the output string for a forest, through the output engine.

        Args:
            forest: The forest to produce the output of
            requested: The descriptors requested with the query
            output_specs: The output descriptors the query resolved
            exec_ctx: Execution context (with logger, symbols_env)
            frontend: Requested output frontend for the output resolution; empty
                leaves the choice to the output engine's own default
        """
        return self._output.output_forest(forest, requested, output_specs, ctx=exec_ctx, frontend=frontend)

    def create_exec_context(self, debug: bool = False) -> ExecContextAPI:
        """Create a new execution context for direct API usage.

        Args:
            debug: Whether to enable debug mode for the logger.

        Returns:
            New ExecContextAPI instance with fresh logger and shared symbols_env.
        """
        return self._create_exec_context(debug=debug)

    def _log_history(
        self, command: str, success: bool, forest: Forest, error: str | None = None, comment: str | None = None
    ) -> None:
        """Publish a CommandExecutedEvent; consumers (e.g. history) subscribe to it."""
        self.bus.emit(
            CommandExecutedEvent(command=command, success=success, forest=forest, error=error, comment=comment)
        )

    def _get_variable(self, name: str) -> Forest:
        value, _ = self.symbols_env.get_variable_with_type(name)
        return value

    def has_variable(self, name: str) -> bool:
        return self.symbols_env.has_variable(name)

    def _clear_variables(self) -> None:
        self.symbols_env.clear_variables()

    def _list_variables(self) -> list[str]:
        return self.symbols_env.list_variables()

    def _apply_and_apply_values(self, forest, requested, exec_ctx, item_cap: int | None = None):
        """Walk the resolved chain, merge what was discovered on the way, apply the rest over the forest.

        The per-query context comes from the factory (a value domain's package
        decorates it, so the context computes); the walk hands it to every chain
        group, and the descriptors the walk did not apply at a chain position are
        applied over the whole forest afterwards.
        """
        chain_context = self._chain_context_factory.create(requested=forest.types.flattened_requested(), ctx=exec_ctx)
        # Expose the per-query context for dependency injection, so tool
        # functions declaring ChainContextAPI (or a domain's subclass of it)
        # receive it instead of failing injection in CLI mode.
        self.injector.set_dependency(ChainContextAPI, chain_context)
        forest_exp, applied = self._apply_chain(forest, chain_context, exec_ctx, item_cap)
        dynamic = [desc for desc in chain_context.get_requested() if desc not in requested]
        if dynamic:
            requested = requested + dynamic
            # Keep the forest self-describing: fold what was discovered during
            # application into the deepest level of its type descriptor
            for desc in dynamic:
                forest_exp.types = forest_exp.types.with_requested(desc)
        # The walk applied the chain items it saw at a top-level position; what is
        # left - the ones nested deeper than depth 0 and the dynamic ones - keeps the
        # whole-forest timing, applied over the final forest.
        remaining = [desc for desc in requested if desc not in applied]
        chain_context.apply_values(forest_exp, remaining, exec_ctx)
        return forest_exp, requested

    def _apply_chain(
        self,
        forest: Forest,
        chain_context: ChainContextAPI,
        exec_ctx: ExecContextAPI,
        item_cap: int | None = None,
    ) -> tuple[Forest, list[ToolDescriptor]]:
        """Apply the resolved chain one group at a time, threading the stage.

        Consecutive chain items handled by one service go to that service together,
        each group over the stage the previous groups produced: a run of chain items is
        one engine call (streaming and the item cap behave as in a whole-forest call),
        a computing group is one runtime call over the items that exist at its
        position. Data children - literal items, spliced forests - are stage items:
        the ones before the first chain item are the first stage, the ones written
        after a group join the stage when that group has run, so the forest keeps the
        written order (`range 3; 7` is 0, 1, 2, then 7).

        Args:
            forest: Resolved forest the chain is read from
            chain_context: The per-query context the groups are handed
            exec_ctx: Execution context (with logger, symbols_env)
            item_cap: Item cap for the last group alone, None when uncapped

        Returns:
            Tuple of (the final stage as a forest, the descriptors applied)

        Raises:
            OverrideForestException: When the chain contains an output-overriding
                tool; its own forest rides on the exception
        """
        chain = forest.convert_to_node().children
        chain_root = Node(item=NODE_ROOT_ITEM, children=chain)
        if chain_declares_meta(self._registry.get_metadatas(), chain_root, OVERRIDES_OUTPUT):
            # An output-overriding chain keeps its short-circuit: nothing of the chain
            # applies, the handler that owns the override raises
            # OverrideForestException with its own forest - `range 5, ?` is unchanged
            self._chain_routing.apply_override(forest, chain_context, exec_ctx)
            return forest, []
        stage = self._initial_stage(chain, forest.types)
        segments = self._segments_after_stage(chain)
        last_group_index = max(
            (index for index, (handler, _) in enumerate(segments) if handler is not None), default=-1
        )
        applied: list[ToolDescriptor] = []
        for group_index, (handler, nodes) in enumerate(segments):
            if handler is None:
                stage = self._stage_with_data(stage, nodes)
                continue
            descriptors = [node.item for node in nodes]
            stage = handler.apply_chain_step(
                descriptors,
                stage,
                chain_context,
                exec_ctx,
                item_cap=item_cap if group_index == last_group_index else None,
            )
            applied.extend(descriptors)
        return stage, applied

    def _initial_stage(self, chain: list[Node], types: ForestTypeDescriptor) -> Forest:
        """Build the stage the chain starts from: the data children before the first chain item.

        Args:
            chain: The resolved forest's top-level children
            types: Forest type descriptor of the resolved forest

        Returns:
            Forest of the data children, their depths preserved
        """
        data_children: list[Node] = []
        for node in chain:
            if self._is_chain_item_node(node):
                break
            data_children.append(node)
        return Node(item=NODE_ROOT_ITEM, children=data_children, types=types).convert_to_forest()

    def _stage_with_data(self, stage: Forest, nodes: list[Node]) -> Forest:
        """Append a data run to the stage at the position it is written at.

        Args:
            stage: The forest the chain has produced so far
            nodes: The run's data children, top-level children of the resolved forest

        Returns:
            The stage with the run's items appended after the ones already there
        """
        added = Node(item=NODE_ROOT_ITEM, children=nodes).convert_to_forest()
        return Forest(
            depths=[*stage.depths, *added.depths],
            items=[*stage.items, *added.items],
            types=stage.types,
        )

    def _is_chain_item_node(self, node: Node) -> bool:
        """Whether this chain child is a tool descriptor, so a handler may apply it.

        Args:
            node: A top-level child of the resolved forest

        Returns:
            True for a descriptor node; anything else (a literal, a spliced item, a
            group) is data and belongs to the stage
        """
        return isinstance(node.item, ToolDescriptor)

    def _segments_after_stage(self, chain: list[Node]) -> list[tuple[ChainStepServiceAPI | None, list[Node]]]:
        """Split the chain into the runs the walk applies after the initial stage.

        Args:
            chain: The resolved forest's top-level children

        Returns:
            List of (handler, nodes) pairs, in written order. Handler is None for a
            run of data children written after a group: their items join the stage
            there. Data children before the first chain item are the initial stage
            (see _initial_stage) and appear in no segment, and neither does a
            descriptor no handler applies (a render)
        """
        segments: list[tuple[ChainStepServiceAPI | None, list[Node]]] = []
        for node in chain:
            if self._is_chain_item_node(node):
                handler = self._chain_routing.handler_for(node.item)
                if handler is None:
                    continue
                if segments and segments[-1][0] is handler:
                    segments[-1][1].append(node)
                else:
                    segments.append((handler, [node]))
            elif segments:
                if segments[-1][0] is None:
                    segments[-1][1].append(node)
                else:
                    segments.append((None, [node]))
        return segments

    def _apply_auto_limit(self, forest: Forest, item_cap: int | None, exec_ctx: ExecContextAPI) -> Forest:
        """Apply the default limit by truncating the forest to the resolved cap.

        Truncates forest items/depths arrays directly, preserving item metadata
        (mutability, sources, etc.). Only truncates when the result exceeds
        the cap.

        Args:
            forest: Expanded forest after chain application
            item_cap: Item cap the chain was applied with, None when uncapped
            exec_ctx: Execution context for debug logging

        Returns:
            Forest, possibly truncated to item_cap items
        """
        default_limit = item_cap
        if default_limit is not None:
            items = forest.items
            depths = forest.depths
            if len(items) > default_limit:
                forest = Forest(
                    depths=depths[:default_limit],
                    items=items[:default_limit],
                    # Truncation does not change the level types
                    types=forest.types,
                )
                exec_ctx.debug(f"auto-limit: truncated to {default_limit} items")
        return forest

    def _create_exec_context(self, debug: bool = False) -> ExecContextAPI:
        """Create a new execution context for query execution.

        Args:
            debug: Whether to enable debug mode for the logger.

        Returns:
            New ExecContextAPI instance with fresh logger and shared symbols_env.
        """
        logger = DebugLogger(log_time=self._config.udan_log_time)
        if debug:
            logger.is_debug = True
        if self._debug_time_session:
            # Sticky `debug-time`: once a query used the marker, later queries in
            # this context (REPL and other long-lived sessions) keep the elapsed-time line
            logger.is_time = True
        return ExecContext(logger=logger, symbols_env=self._symbols_env)

    def _take_ioc_log(self, show_time: bool = False) -> str:
        """Return the IOC startup log for the first query in the process, empty afterwards.

        The IOC log (startup logs from the shared app-scoped logger) is shown only
        for the first query in the process; see _ioc_log_shown in __init__.

        Args:
            show_time: Render the startup lines with timestamp prefixes (a
                `debug-time` query shows them like its own log lines).
        """
        if self._ioc_log_shown:
            return ""
        self._ioc_log_shown = True
        return self._output.get_ioc_debug_log(show_time=show_time)

    def _log_forest_types(self, exec_ctx: ExecContextAPI, forest: Forest) -> None:
        """Log the forest type descriptor to the debug log.

        Args:
            exec_ctx: Execution context whose debug log the line goes to.
            forest: Forest whose types field is shown (pretty-printed by the descriptor).
        """
        exec_ctx.debug(f"forest types: {forest.types}")

    def _finalize_debug_output(
        self,
        out: str,
        logger: ExecContextAPI,
        started: float,
        prepend_debug: bool,
    ) -> tuple[str, str]:
        """Build debug info for the rendered output, optionally prepending it.

        Args:
            out: The rendered output string.
            logger: Execution context (used for debug log access).
            started: perf_counter value captured at query start (for the time line).
            prepend_debug: When True, prepend debug info to the output string (CLI
                behavior); when False, keep the output clean.

        Returns:
            Tuple of (possibly-prepended output, debug info text).
        """
        ioc_log = self._take_ioc_log(show_time=logger.is_time)
        time_line = self._time_line(logger, started)
        debug_info = self._build_debug_info(logger, ioc_log, time_line)
        if prepend_debug:
            out = self._prepend_debug_info(out, logger, ioc_log, time_line)
        return out, debug_info

    def _time_line(self, logger: ExecContextAPI, started: float) -> str:
        """Format the elapsed-time line shown by the `debug-time` marker.

        Args:
            logger: Execution context whose is_time flag enables the line.
            started: perf_counter value captured at query start.

        Returns:
            Elapsed-time line as a normal log line, e.g.
            '# [12.34.567] [DEBUG] Time: 0.123s', or empty when is_time is off
            (plain `debug` output stays unchanged).
        """
        if not logger.is_time:
            return ""
        elapsed = time.perf_counter() - started
        return f"# {_format_time_prefix(time.time())} [DEBUG] Time: {elapsed:.3f}s"

    def _build_debug_info_raw(self, logger: ExecContextAPI, ioc_log: str, time_line: str = "") -> str:
        """Build raw debug info text: IOC startup log, query debug log, and time line.

        Args:
            logger: Execution context (used for debug log access).
            ioc_log: IOC startup log section (captured once per query via _take_ioc_log).
            time_line: Elapsed-time line (shown when the `debug-time` marker is used).

        Returns:
            Raw (unstripped) debug info text.
        """
        parts: list[str] = []
        if logger.is_debug:
            # Initialization (IOC startup) lines predate the query, so they come
            # first, then the query's own log.
            parts.extend([ioc_log, logger.get_debug_log()])
        if time_line:
            parts.append(time_line)
        return "\n".join(part for part in parts if part) + "\n"

    def _build_debug_info(self, logger: ExecContextAPI, ioc_log: str, time_line: str = "") -> str:
        """Build debug info text for separate (non-prepended) return.

        Args:
            logger: Execution context (used for debug log access).
            ioc_log: IOC startup log section (captured once per query via _take_ioc_log).
            time_line: Elapsed-time line (shown when the `debug-time` marker is used).

        Returns:
            Debug info text when logger.is_debug or logger.is_time is True,
            otherwise empty string.
        """
        if not (logger.is_debug or logger.is_time):
            return ""
        return self._build_debug_info_raw(logger, ioc_log, time_line).strip()

    def _prepend_debug_info(self, out: str, logger: ExecContextAPI, ioc_log: str, time_line: str = "") -> str:
        """Prepend the debug block (IOC log, query log, time line) to output.

        Args:
            out: The rendered output string.
            logger: Execution context (used for debug log access).
            ioc_log: IOC startup log section (captured once per query via _take_ioc_log).
            time_line: Elapsed-time line (shown when the `debug-time` marker is used).

        Returns:
            Output with debug info prepended when logger.is_debug or logger.is_time
            is True, otherwise the original output unchanged.
        """
        if not (logger.is_debug or logger.is_time):
            return out
        return (self._build_debug_info_raw(logger, ioc_log, time_line) + out).strip()

    def apply_state(
        self,
        forest: Forest,
        requested: Sequence[ToolDescriptor],
        output_specs: Sequence[ToolDescriptor],
        exec_ctx: ExecContextAPI,
    ) -> tuple[Forest, list, str]:
        """Apply the chain, fold what was discovered on the way, apply the values, produce output.

        No item cap, no auto-limit, no debug finalization, no history: errors
        propagate to the caller.

        Args:
            forest: Resolved forest the chain applies to
            requested: Descriptors resolved with the forest
            output_specs: Output descriptors resolved with the forest
            exec_ctx: Execution context (with logger, symbols_env)

        Returns:
            Tuple of (expanded forest, requested, output_string)
        """
        forest_exp, requested = self._apply_and_apply_values(forest, requested, exec_ctx)
        self._log_forest_types(exec_ctx, forest_exp)
        out = self._output.output_forest(forest_exp, requested, output_specs, ctx=exec_ctx)
        return forest_exp, requested, out

    def run_state(  # noqa: PLR0913
        self,
        forest: Forest,
        requested: Sequence[ToolDescriptor],
        output_specs: Sequence[ToolDescriptor],
        exec_ctx: ExecContextAPI,
        *,
        started: float,
        query_text: str,
        item_cap: int | None = None,
        comment: str | None = None,
        prepend_debug: bool = True,
        apply: bool = True,
    ) -> tuple[Forest | None, list, Sequence[ToolDescriptor], str, str]:
        """The engine half of a full execution, with the error contract.

        Applies with the item cap, auto-limits to the same cap, renders,
        finalizes the debug output and logs history. Never raises: a failure is
        a None forest with the message in the output string. An introspection
        override renders its own forest instead - one raised by the engine
        inside the application, and one handed in by the caller when the
        resolve half already produced an override forest (type combination).

        Args:
            forest: Resolved forest the chain applies to; with apply=False the
                override forest to produce the output of directly
            requested: Descriptors resolved with the forest
            output_specs: Output descriptors resolved with the forest; the
                override output falls back to the engine's default when empty
            exec_ctx: Execution context (with logger, symbols_env)
            started: The caller's perf_counter, so the `debug-time` line still
                covers the whole query
            query_text: The query the state was resolved from (the history label)
            item_cap: Item cap for chain application, None when uncapped;
                the same cap drives the auto-limit truncation
            comment: Optional comment describing the query purpose (history)
            prepend_debug: When True, prepend debug info to the output string;
                when False, return it separately as the fifth element
            apply: When False, skip chain application and the auto-limit:
                `forest` is an override forest and is rendered as resolved

        Returns:
            Tuple of (forest, requested, output_specs, output_string, debug_info)
            If an error occurs, output_string contains the error message
            and forest will be None.
        """
        try:
            # `debug-time` is session-level: a query using the marker turns the
            # elapsed-time line on for the rest of the queries in this context
            self._debug_time_session = self._debug_time_session or exec_ctx.is_time

            if apply:
                # Apply the chain and apply the values. The item cap lets the
                # engine stop pulling lazy sources once the default limit is
                # reached; the auto-limit below still truncates the exact amount.
                forest_exp, requested = self._apply_and_apply_values(forest, requested, exec_ctx, item_cap=item_cap)

                # The forest type descriptor after application (dynamic requests already folded in)
                self._log_forest_types(exec_ctx, forest_exp)

                # Auto-limit: truncate results if no explicit limit in query
                forest_exp = self._apply_auto_limit(forest_exp, item_cap, exec_ctx)

                # Produce the output
                exec_ctx.debug("#execute_query: OK")
                out = self._output.output_forest(forest_exp, requested, output_specs, ctx=exec_ctx)
                rendered = (forest_exp, requested, output_specs)
            else:
                # Introspection override handed in resolved: produce its output directly.
                # The specs the query resolved already carry the right output (they use
                # the last chain item's supported_renders); with none, the engine defaults.
                specs_to_use = output_specs if output_specs else self._output.default_output_specs()
                exec_ctx.debug("#execute_query: OVERRIDE")
                self._log_forest_types(exec_ctx, forest)
                out = self._output.output_forest(forest, [], specs_to_use, ctx=exec_ctx)
                rendered = (forest, [], specs_to_use)

            # Prepend debug info or return it separately
            out, debug_info = self._finalize_debug_output(out, exec_ctx, started, prepend_debug)

            result = (*rendered, out, debug_info)

            self.log_execution_result(query_text, success=True, result=result[:4], comment=comment)
            return result
        except OverrideForestException as ex:
            # Introspection override raised inside the application: produce the output
            # of the exception's forest directly, with the specs requested above
            specs_to_use = output_specs if output_specs else self._output.default_output_specs()
            exec_ctx.debug("#execute_query: OVERRIDE")
            self._log_forest_types(exec_ctx, ex.forest)
            out = self._output.output_forest(ex.forest, [], specs_to_use, ctx=exec_ctx)

            # Prepend debug info or return it separately
            out, debug_info = self._finalize_debug_output(out, exec_ctx, started, prepend_debug)

            result = (ex.forest, [], specs_to_use, out, debug_info)
            self.log_execution_result(query_text, success=True, result=result[:4], comment=comment)
            return result
        except Exception as ex:
            if isinstance(ex, ExceptionWithAdvice):
                out = ex.advice
            else:
                out = traceback.format_exc()
            exec_ctx.debug("#execute_query: FAIL")
            debug_info = self.execution_debug_text(exec_ctx, started)
            if prepend_debug:
                out = (debug_info + "\n" + out).strip()
            self.log_execution_result(query_text, success=False, error=ex, comment=comment)
            return None, [], [], out, debug_info

    def execute_query(  # noqa: PLR0913
        self,
        query_node: Node,
        exec_ctx: ExecContextAPI,
        *,
        query_text: str,
        started: float | None = None,
        comment: str | None = None,
        prepend_debug: bool = True,
    ) -> tuple[Forest | None, list, Sequence[ToolDescriptor], str, str]:
        """Execute a parsed query node: the resolve half and the engine half, with the error contract.

        Validates the preferences, resolves the node (the query processor), applies
        with the item cap, auto-limits, renders, finalizes the debug output and logs
        history. Never raises: a failure is a None forest with the message in the
        output string; an introspection override (type combination) renders its own
        forest instead. Parse errors are the caller's: the caller parsed the node
        this method takes.

        Args:
            query_node: The parsed query tree (the parser's product)
            exec_ctx: Execution context (with logger, symbols_env)
            query_text: The query the node was parsed from (the debug line and
                the history label)
            started: The caller's perf_counter captured before the parse, so the
                `debug-time` line still covers the whole query; None captures at entry
            comment: Optional comment describing the purpose/goal of the query (history)
            prepend_debug: When True, prepend debug info to the output string (CLI behavior);
                when False, return it separately as the fifth element (API behavior)

        Returns:
            Tuple of (forest, requested, output_specs, output_string, debug_info)
            If an error occurs, output_string contains the error message
            and forest will be None.
        """
        return self._execute_query_impl(
            query_node,
            exec_ctx,
            query_text=query_text,
            started=started,
            comment=comment,
            prepend_debug=prepend_debug,
        )

    def _execute_query_impl(  # noqa: PLR0913
        self,
        query_node: Node,
        exec_ctx: ExecContextAPI,
        *,
        query_text: str,
        started: float | None = None,
        comment: str | None = None,
        prepend_debug: bool = True,
    ) -> tuple[Forest | None, list, Sequence[ToolDescriptor], str, str]:
        """execute_query's impl: the resolve half, then the engine half through run_state.

        A resolve failure takes the same error contract run_state gives the engine
        half - None forest, the message in the output string, history logged - and
        an introspection override from the resolve half (type combination) renders
        its forest directly (run_state with apply=False).

        Args:
            query_node: The parsed query tree the resolver resolves
            exec_ctx: Execution context (with logger, symbols_env)
            query_text: The query the node was parsed from (the debug line and
                the history label)
            started: The caller's perf_counter captured before the parse, so the
                `debug-time` line still covers the whole query; None captures at entry
            comment: Optional comment describing the query purpose (history)
            prepend_debug: When True, prepend debug info to the output string;
                when False, return it separately as the fifth element

        Returns:
            Tuple of (forest, requested, output_specs, output_string, debug_info)
        """
        if started is None:
            started = time.perf_counter()
        exec_ctx.debug(f"{query_text=}")
        # Validate preferences (warn about incorrect usage)
        # This is done here so plugins have a chance to be loaded first
        self._registry.validate_preferences()
        try:
            exec_ctx.debug(f"query_tree: {query_node.item} children={len(query_node.children)}")
            forest, attrs, render_tools = self._query_processor.resolve_query(query_node, exec_ctx)
        except OverrideForestException as ex:
            # Resolve-side override (type combination): the forest rides on the
            # exception and is rendered without applying operators
            return self.run_state(
                ex.forest,
                [],
                [],
                exec_ctx,
                started=started,
                query_text=query_text,
                comment=comment,
                prepend_debug=prepend_debug,
                apply=False,
            )
        except Exception as ex:
            if isinstance(ex, ExceptionWithAdvice):
                out = ex.advice
            else:
                out = traceback.format_exc()
            exec_ctx.debug("#execute_query: FAIL")
            debug_info = self.execution_debug_text(exec_ctx, started)
            if prepend_debug:
                out = (debug_info + "\n" + out).strip()
            self.log_execution_result(query_text, success=False, error=ex, comment=comment)
            return None, [], [], out, debug_info
        return self.run_state(
            forest,
            attrs,
            render_tools,
            exec_ctx,
            started=started,
            query_text=query_text,
            item_cap=self._item_cap(query_node),
            comment=comment,
            prepend_debug=prepend_debug,
        )

    def prepare_query_state(
        self, query_node: Node, exec_ctx: ExecContextAPI
    ) -> tuple[Forest, list, list[RenderDescriptor], str]:
        """Prepare the query state: resolve, apply operators and attributes, render.

        Unlike execute_query this applies no item cap and no auto-limit, does no
        debug finalization, and logs no history; errors propagate to the caller
        instead of becoming a None-forest result. For flows that post-process the
        state and own their reporting; the caller parses the node this method takes.

        Args:
            query_node: The parsed query tree the resolver resolves
            exec_ctx: Execution context (with logger, symbols_env)

        Returns:
            Tuple of (forest, attrs, render_tools, output_string)
        """
        forest, attrs, render_specs = self._query_processor.resolve_query(query_node, exec_ctx)
        forest_exp, attrs, out = self.apply_state(forest, attrs, render_specs, exec_ctx)
        return forest_exp, attrs, render_specs, out

    def _item_cap(self, query_tree: Node) -> int | None:
        """Resolve the item cap for operator application, or None if uncapped.

        Returns the configured default limit when the auto-limit will apply
        (limit configured and the query leaves limiting to udan). The operator
        engine uses it to stop pulling items from lazy sources (db cursors,
        files) once the limit is reached, instead of materializing everything
        and truncating afterwards.

        Args:
            query_tree: Original parsed query tree (for limit keyword detection)

        Returns:
            Item cap, or None when operators should not be bounded
        """
        default_limit = self._config.udan_default_limit
        if default_limit > 0 and not _query_mentions_limit(query_tree):
            return default_limit
        return None

    def execution_debug_text(self, exec_ctx: ExecContextAPI, started: float) -> str:
        """Collect the debug text of a finished execution.

        Args:
            exec_ctx: The execution context the execution ran with.
            started: perf_counter value captured at execution start (for the time line).

        Returns:
            The context's debug log followed by the elapsed-time line; empty when
            the log is empty and the time line is off.
        """
        debug_text = exec_ctx.get_debug_log().strip()
        time_line = self._time_line(exec_ctx, started)
        return "\n".join(part for part in (debug_text, time_line) if part)

    def log_execution_result(
        self,
        query_text: str,
        success: bool,
        result: tuple[Forest, list, Sequence[ToolDescriptor], str] | None = None,
        error: Exception | None = None,
        comment: str | None = None,
    ) -> None:
        """Log an execution result to history.

        Args:
            query_text: The query that was executed
            success: Whether execution succeeded
            result: The result tuple (forest, requested, output_specs, out) for success cases
            error: The exception for failure cases
            comment: Optional comment describing the query purpose
        """
        if success and result is not None:
            forest = result[0]
            self._log_history(query_text, success=True, forest=forest, comment=comment)
        elif error is not None:
            self._log_history(query_text, success=False, forest=EMPTY_FOREST, error=str(error), comment=comment)
