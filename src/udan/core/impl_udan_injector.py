"""The udan half of dependency injection: the sources over what udan holds.

udan.core_tools_loading's FunctionInjector is the generic injector; what udan adds is the
sources it resolves through - the container (the app-scoped services, answered
lazily into its one memo), the dependency registry's @annotated_dependency
providers (the per-query and plugins_only providers that stay registry-side),
and the keys that count as injected although nothing answers them yet (the
chain context the engine serves per query). The composition that wires them is
the container's own (impl_ioc), and the udan flavor is in the sources, not in a
subclass: with_global_dependency passes the sources through, so a plugin
decoration that extends the globals re-uses the same resolution layers.
"""

from collections.abc import Iterable
from typing import Any

from udan.core.api_chain_context import ChainContextAPI
from udan.core.api_dependencies_registry import DependenciesRegistryAPI
from udan.core_tools_loading.api_function_injector import MISSING
from udan.decompof import Container

# The chain context the engine serves per query (impl_udan_context.set_dependency):
# declared so a tool annotating it stays out of the schema for the whole
# run, though nothing answers it until the walk hands the context over
PER_QUERY_KEY = ChainContextAPI


class ContainerSource:
    """The container's services, by the key each provides.

    Prepended ahead of the registry source: a key the container serves is
    answered by the container's own singleton, and the registry keeps only the
    keys nothing in the wiring declares.
    """

    def __init__(self, container: Container) -> None:
        self._container = container
        self._keys = set(container.provided_keys())

    def keys(self) -> set[type]:
        """The keys the container's wiring declares; see DependencySource."""
        return set(self._keys)

    def get(self, dep_type: type) -> Any:
        """Resolve from the container; a key the wiring does not declare is not answered here.

        The container is strict - a key nothing provides raises rather than
        answering - so the source asks before it resolves, the way the
        registry source does.
        """
        if dep_type not in self._keys:
            return MISSING
        return self._container.get(dep_type)


class RegistrySource:
    """The dependency registry's providers, by the type each provides."""

    def __init__(self, registry: DependenciesRegistryAPI) -> None:
        self._registry = registry

    def keys(self) -> set[type]:
        """The types the registered providers answer; see DependencySource."""
        return self._registry.provided_types()

    def get(self, dep_type: type) -> Any:
        """Resolve from the registry; a type with no provider is not answered here.

        A provider's own error (a missing dependency of its own, a cycle)
        propagates.
        """
        if not self._registry.has_provider(dep_type):
            return MISSING
        return self._registry.resolve(dep_type)


class DeclaredKeysSource:
    """Keys that count as injected although nothing here answers them.

    The container serves some of them (a tool annotating them stays out
    of the schema, and its declared default stands); the engine's set_dependency
    answers the rest, later, per query.
    """

    def __init__(self, keys: Iterable[type]) -> None:
        self._keys = set(keys)

    def keys(self) -> set[type]:
        """The declared keys; see DependencySource."""
        return set(self._keys)

    def get(self, dep_type: type) -> Any:
        """Nothing: a declared key is a classification, not an answer."""
        return MISSING
