"""Public API for the tool kind vocabulary.

This module defines the kind contract the loader and the registry read: what a
kind service declares, and the vocabulary interface the container builds.
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Iterator, Mapping
from types import ModuleType

from udan.core_tools_loading.api_tools import ToolKind


class ToolKindService:
    """A service that owns tool kinds: it declares them as its `KINDS`.

    The service that processes a kind is the one that defines it: the chain-step engine
    declares the chain-forming kinds, the attribute runtime the attribute kind, and a
    plugin module's service declares the module's own. Declaring -
    not registering - is the service's whole job: the container registers the core
    declarations when it builds the vocabulary, and ToolsRegistry.load_plugins
    registers a plugin module's before its tools are loaded.

    Subclassing this base is what makes a class a kind service: ToolKindsService
    harvesting is by subclass, so the contract above is checked by the type system.
    """

    KINDS: tuple[ToolKind, ...] = ()
    """The kinds this service owns."""


def get_kind_services(module: ModuleType) -> list[type[ToolKindService]]:
    """Harvest a module's tool-kind services.

    Only classes defined in the module itself are returned, to avoid harvesting a
    service imported from another module.

    Args:
        module: Python module to harvest kind services from

    Returns:
        The module's kind services, in definition order
    """
    module_name = module.__name__
    return [
        attr_val
        for attr_val in module.__dict__.values()
        if isinstance(attr_val, type) and issubclass(attr_val, ToolKindService) and attr_val.__module__ == module_name
    ]


class ToolKindsRegistryAPI(Mapping):
    """API interface for the tool kind vocabulary.

    A container component like every other registry: the IoC container builds it filled,
    from the `KINDS` the kind services declare (the chain-step engine the chain-forming
    kinds, the attribute runtime the attribute kind); plugin kinds are registered into
    it by ToolsRegistry.load_plugins.

    Reading it is the mapping protocol over kind names: `"render" in kinds`,
    `kinds["render"]`, iteration over the names - so a kind a service declared is
    visible everywhere a mapping of kinds is taken.
    """

    def register(self, kind: ToolKind) -> ToolKind:
        """Register a kind, filling in what an earlier registration left open.

        Args:
            kind: The kind to register

        Returns:
            The stored kind (the merged one when the kind was already known)

        Raises:
            ValueError: If the kind contradicts a field already set for its name
        """
        raise NotImplementedError

    def default_kind(self) -> ToolKind | None:
        """The kind a tool with no declared kind resolves to.

        Whichever registered kind declares `is_default` - the package owning the
        kind decides what the default of the language is. None when no registered
        kind claims it: every undeclared tool then gets the bare default
        kind, which declares no rules.

        Returns:
            The default kind, or None when none declares itself the default
        """
        raise NotImplementedError

    @abstractmethod
    def __getitem__(self, name: str) -> ToolKind: ...

    @abstractmethod
    def __iter__(self) -> Iterator[str]: ...

    @abstractmethod
    def __len__(self) -> int: ...
