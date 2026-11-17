"""Implementation of the chain routing: kind name -> the service that applies it.

Built by the IoC container from the kind services it holds: a service declares the kinds
it owns as its `KINDS` (ToolKindService), and the routing indexes exactly those
declarations, so ownership is declared once and dispatched everywhere. Plugin packages
extend the table through `with_handler` (their routing decorations) or in place through
`add_handler`/`remove_handler` (their attach/detach verbs), and the invariant is checked
at the composition root - `validate`, run once the routing is complete, so a wiring gap
fails at container build, not at query time.
"""

from collections.abc import Iterator

from udan.core.api_chain_context import ChainContextAPI
from udan.core.api_chain_routing import ChainRoutingAPI, ChainStepServiceAPI
from udan.core.api_exceptions import ExceptionWithAdvice
from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_forests import Forest
from udan.core_tools_loading.api_tool_kinds import ToolKindService, ToolKindsRegistryAPI
from udan.core_tools_loading.api_tools import ToolDescriptor
from udan.core_tools_loading.api_tools_registry import ToolsRegistryAPI


class ChainRouting(ChainRoutingAPI):
    """Kind name -> handler, read from what the kind services declared."""

    def __init__(
        self,
        services: list[ToolKindService],
        kinds: ToolKindsRegistryAPI,
        registry: ToolsRegistryAPI,
        override_handler: ChainStepServiceAPI | None = None,
    ) -> None:
        """Build the routing from the kind services' declarations.

        Args:
            services: The services that can apply chain steps (ChainStepServiceAPI)
            kinds: The tool kind vocabulary, for the forms_chain lookups
            registry: Tools registry, resolving a descriptor to its kind
            override_handler: The service an output-overriding chain is handed to,
                None until the package that owns it contributes one

        Raises:
            ValueError: If a service declares kinds without implementing the chain
                step contract, or two services claim one kind
        """
        self._handlers: dict[str, ChainStepServiceAPI] = {}
        for service in services:
            self._claim(service)
        self._services = list(services)
        self._override_handler = override_handler
        self._kinds = kinds
        self._registry = registry

    def with_handler(self, service: ToolKindService) -> ChainRoutingAPI:
        """The routing with one more handler; the duplicate-claim check runs over the table.

        The completeness invariant is deliberately not checked here: a routing may have
        several decorations pending, so the check is `validate`, run once the last one
        applied.

        Args:
            service: The handler for the kinds its `KINDS` declare

        Returns:
            The routing with the service's kinds added to its table

        Raises:
            ValueError: If the service cannot apply a chain step, or claims a kind
                another handler already claims
        """
        return ChainRouting([*self._services, service], self._kinds, self._registry, self._override_handler)

    def add_handler(self, service: ToolKindService) -> None:
        """Add one handler to the table, in place; the duplicate-claim check runs over the table.

        The completeness invariant is deliberately not checked here: several handlers
        may still be pending, so the check is `validate`, run once the last one applied.

        Args:
            service: The handler for the kinds its `KINDS` declare

        Raises:
            ValueError: If the service cannot apply a chain step, or claims a kind
                another handler already claims
        """
        self._claim(service)
        self._services.append(service)

    def remove_handler(self, service: ToolKindService) -> None:
        """Take one handler back off the table, in place; see ChainRoutingAPI.

        Only the kinds the service still owns come off: a kind another handler has
        taken over in between stays handled.

        Args:
            service: The handler whose kinds come off the table
        """
        if service in self._services:
            self._services.remove(service)
        for kind in service.KINDS:
            if self._handlers.get(kind.name) is service:
                del self._handlers[kind.name]

    def with_override_handler(self, service: ChainStepServiceAPI) -> ChainRoutingAPI:
        """The routing with the handler for an output-overriding chain; see ChainRoutingAPI.

        Args:
            service: The service the routing hands an overriding forest to

        Returns:
            The routing with that handler set
        """
        return ChainRouting([*self._services], self._kinds, self._registry, service)

    def apply_override(
        self,
        forest: Forest,
        chain_context: ChainContextAPI,
        ctx: ExecContextAPI,
        item_cap: int | None = None,
    ) -> None:
        """Apply a chain that overrides the output, whole; see ChainRoutingAPI.

        The handler answers by raising OverrideForestException with the forest the
        output should be, so this returns nothing.

        Raises:
            OverrideForestException: Always, once a handler owns the override
            ValueError: If none does - the package that owns it is not enabled
        """
        handler = self._override_handler
        if handler is None:
            raise ValueError(
                "This chain overrides the output, but no handler applies it: the "
                "package owning the output-overriding kind is not enabled, so the "
                "query cannot run."
            )
        handler.apply_chain_step([], forest, chain_context, ctx, item_cap=item_cap)

    def validate(self) -> None:
        """Fail when a chain-forming kind of the vocabulary has no handler.

        Raises:
            ValueError: If a chain-forming kind of the vocabulary is unhandled
        """
        unhandled = [name for name, kind in self._kinds.items() if kind.forms_chain and name not in self._handlers]
        if unhandled:
            raise ValueError(f"Chain-forming kinds with no handler: {', '.join(sorted(unhandled))}")

    def _claim(self, service: ToolKindService) -> None:
        """Index one service's kinds into the handler table, checking the claims.

        Args:
            service: The service claiming the kinds its `KINDS` declare

        Raises:
            ValueError: If the service cannot apply a chain step, or claims a kind
                another handler already claims
        """
        if not isinstance(service, ChainStepServiceAPI):
            raise ValueError(f"{type(service).__name__} declares kinds but cannot apply a chain step")
        for kind in service.KINDS:
            claimed = self._handlers.get(kind.name)
            if claimed is not None and claimed is not service:
                raise ValueError(
                    f"Kind '{kind.name}' is claimed by two chain services: "
                    f"{type(claimed).__name__} and {type(service).__name__}"
                )
            self._handlers[kind.name] = service

    def handler_for(self, descriptor: ToolDescriptor) -> ChainStepServiceAPI | None:
        """The service that applies this descriptor's kind, resolved through the registry.

        The descriptor carries no kind of its own (ToolDescriptor is name +
        args + tool_args), so the kind comes from the registered metadata - one lookup,
        keeping the walk free of metadata.

        Args:
            descriptor: A chain descriptor from the resolved forest

        Returns:
            The handler of the descriptor's kind, or None when the kind does not
            form the chain

        Raises:
            ExceptionWithAdvice: If no loaded package owns the kind - the tool loaded
                as a bare kind that declares no rules, so it cannot be interpreted,
                and the message says what is missing; or if the kind forms the chain
                but no service handles it - the package owning the kind is not
                enabled, which is a query the user can fix, so the message says what
                is missing
        """
        metadata = self._registry.get_metadata(descriptor.name)
        if metadata is None:
            return None
        declared = self._kinds.get(metadata.tool_type.name)
        if declared is None:
            raise ExceptionWithAdvice(
                f"tool '{descriptor.name}' cannot be interpreted: no loaded package owns its kind "
                f"'{metadata.tool_type.name}' - the package declaring '{metadata.tool_type.name}' is not in "
                f"udan_plugin_modules. Enable that package, or drop the '{descriptor.name}' step."
            )
        kind = declared
        if not kind.forms_chain:
            return None
        handler = self._handlers.get(kind.name)
        if handler is None:
            raise ExceptionWithAdvice(
                f"A '{kind.name}' tool forms the chain, but no enabled package applies "
                f"its kind: the package owning '{kind.name}' is not in udan_plugin_modules, so "
                f"the query cannot run. Enable that package, or drop the '{kind.name}' step."
            )
        return handler

    def __getitem__(self, name: str) -> ChainStepServiceAPI:
        handler = self._handlers.get(name)
        if handler is None:
            registered = ", ".join(self._handlers)
            raise KeyError(f"No chain handler for kind: {name!r}. Handled kinds: {registered}")
        return handler

    def __iter__(self) -> Iterator[str]:
        return iter(self._handlers)

    def __len__(self) -> int:
        return len(self._handlers)

    def __repr__(self) -> str:
        """Readable listing of the handled kinds and their services."""
        return f"ChainRouting({', '.join(f'{k}={type(v).__name__}' for k, v in self._handlers.items())})"
