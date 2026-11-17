"""The chain context of a query whose value domains are not enabled.

Every value domain that computes is a plugin package's service. A host that
leaves them out runs queries with no value computation, and the walk still owes
the chain handlers a context - this is that context, the one the core factory
builds. Computing fails with the advice that says what is missing; storing and
store reads work over the context's own store, because the values a chain sets
itself (an operator's origin chain, the values tools mark as
precalculated) are known without a domain package.
"""

from typing import Any

from udan.core.api_chain_context import ChainContextAPI, ChainContextFactoryAPI
from udan.core.api_exceptions import ExceptionWithAdvice
from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_forests import Forest, Item
from udan.core_tools_loading.api_tools import ToolDescriptor
from udan.core_tools_loading.api_tools_registry import ToolsRegistryAPI

_NO_DOMAIN_ADVICE = (
    "Value computation is not enabled: this container was built without the "
    "computing context factory the value domains provide (udan.attributes, part "
    "of udan, provides it on every normal boot), so '{name}' cannot be resolved. "
    "Build the container through create_udan_container() to run queries that compute it."
)


class DummyChainContext(ChainContextAPI):
    """No value domain enabled: computing fails with advice, storing goes to the store.

    The context the core factory hands the chain handlers. The store keeps what the
    chain sets itself for the length of the query; the requested list stays empty,
    because nothing discovers descriptors without a domain package.
    """

    def __init__(self, registry: ToolsRegistryAPI, ctx: ExecContextAPI | None = None) -> None:
        """Initialize the context over the query's registry.

        Args:
            registry: Tools registry the handlers resolve through
            ctx: Execution context of the query
        """
        self.registry = registry
        self._ctx = ctx
        self.depth = 0
        # Descriptor -> item -> value, with the unhashable items keyed by identity
        self._values: dict[ToolDescriptor, dict[Item, Any]] = {}
        self._unhashable: dict[ToolDescriptor, dict[int, tuple[Item, Any]]] = {}

    def set_value(self, desc: ToolDescriptor, item: Item, value: Any) -> None:
        """Store the value under the descriptor."""
        try:
            hash(item)
            self._values.setdefault(desc, {})[item] = value
        except TypeError:
            self._unhashable.setdefault(desc, {})[id(item)] = (item, value)

    def get_requested(self) -> list[ToolDescriptor]:
        """Nothing was requested: discovery is a value domain's work."""
        return []

    def get_stored_value(self, desc: ToolDescriptor, item: Item) -> Any | None:
        """The stored value, or None when nothing stored one."""
        try:
            hash(item)
            return self._values.get(desc, {}).get(item)
        except TypeError:
            result = self._unhashable.get(desc, {}).get(id(item))
            return result[1] if result else None

    def get_value(self, desc: ToolDescriptor, item: Item) -> Any:
        """Refuse: computing is a value domain's work, and none is enabled.

        Raises:
            ExceptionWithAdvice: Always, with what is missing
        """
        raise ExceptionWithAdvice(_NO_DOMAIN_ADVICE.format(name=desc.name))

    def apply_values(self, forest: Forest, requested: list[ToolDescriptor], ctx: ExecContextAPI) -> None:
        """Nothing to apply: with no domain package nothing computes, and nothing asks for it."""


class DummyChainContextFactory(ChainContextFactoryAPI):
    """The core factory: the store-only context of a query with no value domain.

    Args:
        registry: Tools registry the contexts answer computes against, as
            the container wires it
    """

    def __init__(self, registry: ToolsRegistryAPI) -> None:
        self._registry = registry

    def create(
        self,
        requested: list[ToolDescriptor] | None = None,
        ctx: ExecContextAPI | None = None,
    ) -> DummyChainContext:
        """Build the store-only context of one query.

        Args:
            requested: Descriptors the resolved query requested (unused: nothing discovers them)
            ctx: Execution context of the query

        Returns:
            The per-query chain context
        """
        return DummyChainContext(registry=self._registry, ctx=ctx)
