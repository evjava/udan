"""The resolution half of udan.decompof: make_container and Container.

A container is built from provider instances and context values. Every service
is a lazy singleton keyed by the exact type its factory provides: get() builds a
service the first time it is asked for and hands back that instance from then on,
so construction order follows the requests rather than the declarations. Context
values - the instances a caller brings to make_container - are seeded into the
same memo, so they win over any factory claiming the same key, which is how the
composition root hands one UdanConfig to every component.

A key can also carry decorations: factories that wrap the instance another
factory builds instead of building one themselves. get() walks the key's chain
in declaration order - base factory first, then each decoration handing the
previous instance back as the parameter that asks for the key - and memoizes
only the last instance, so callers and dependent factories cannot tell that a
service is decorated.

The container validates its wiring when it is built: two providers claiming one
key, a decoration with nothing to decorate, or a factory asking for a key
nothing provides, fail the build instead of surfacing later as a get() that
happens to be called.
"""

import inspect
from collections.abc import Callable
from typing import Any, get_type_hints

from udan.decompof.provide import (
    BOUND_PARAMETER_NAMES,
    Declaration,
    DeclarationError,
    Provider,
    _key_name,
    _required_key,
)


class ContainerError(RuntimeError):
    """The container cannot be built, or cannot serve a key."""


class DuplicateProviderError(ContainerError):
    """Two providers declare a factory for one key."""


class UnresolvableKeyError(ContainerError):
    """A key nothing provides was asked for, or a factory asks for one."""


class DependencyCycleError(ContainerError):
    """A factory asks, transitively, for the key it provides."""


def _verb_name(fn: Callable[..., Any]) -> str:
    """A verb as an error message shows it: its qualified name, or the value itself."""
    return getattr(fn, "__qualname__", None) or str(fn)


def _verb_parameters(fn: Callable[..., Any]) -> dict[str, type]:
    """The dependencies a verb asks for, by parameter name.

    A verb - a plugin's attach or detach - names its dependencies by annotating
    its parameters, exactly as a factory does; the receiver is not one of them,
    and a variadic parameter names no key either.

    Args:
        fn: The verb, bound to the instance that declares it.

    Returns:
        The keys the verb asks for, by parameter name.

    Raises:
        DeclarationError: A parameter has no annotation, or annotates something
            that is not a type key - the same reading rules a factory's
            declaration applies, so a verb is no looser than a factory.
    """
    hints = get_type_hints(fn)
    parameters: dict[str, type] = {}
    for name, parameter in inspect.signature(fn).parameters.items():
        if name in BOUND_PARAMETER_NAMES:
            continue
        if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            continue
        if name not in hints:
            raise DeclarationError(f"{_verb_name(fn)}: parameter {name!r} has no annotation, so it names no key")
        parameters[name] = _required_key(hints[name], _verb_name(fn), name)
    return parameters


class Factory:
    """A declaration bound to the provider instance that declared it."""

    def __init__(self, declaration: Declaration, provider: Provider) -> None:
        self._provides = declaration.provides
        self._parameters = declaration.parameters
        self._make = declaration.bound_to(provider)

    @property
    def provides(self) -> type:
        """The key the factory is registered under."""
        return self._provides

    @property
    def parameters(self) -> dict[str, type]:
        """The keys the factory asks for, by parameter name."""
        return self._parameters

    def build(self, resolved: dict[str, Any]) -> Any:
        """Call the factory with its resolved dependencies.

        Args:
            resolved: The dependencies by parameter name.

        Returns:
            The factory's instance.
        """
        return self._make(**resolved)


class Container:
    """The services a set of providers declare, resolved lazily by exact type."""

    def __init__(self, providers: list[Provider], context: dict[type, Any] | None = None) -> None:
        """Build the factory map, collect the decoration chains and validate the wiring.

        Args:
            providers: The providers whose declarations compose the container.
            context: Instances the caller brings; each wins over any factory claiming its type.

        Raises:
            DuplicateProviderError: Two providers claim one key.
            ContainerError: A decoration claims a key the caller supplied as context.
            UnresolvableKeyError: A factory asks for a key no factory or context value
                provides, or a decoration claims a key no factory provides.
        """
        self._context = dict(context or {})
        self._factories: dict[type, Factory] = {}
        owners: dict[type, str] = {}
        for provider in providers:
            for attribute, declaration in provider.declarations():
                if declaration.is_decorator:
                    continue
                factory = Factory(declaration, provider)
                if factory.provides in self._factories:
                    raise DuplicateProviderError(
                        f"{_key_name(factory.provides)} is provided by both "
                        f"{owners[factory.provides]} ({attribute}) and {type(provider).__name__}"
                    )
                self._factories[factory.provides] = factory
                owners[factory.provides] = type(provider).__name__
        self._decorations: dict[type, list[Factory]] = {}
        for provider in providers:
            for _attribute, declaration in provider.decorations():
                self._decorations.setdefault(declaration.provides, []).append(Factory(declaration, provider))
        self._instances: dict[type, Any] = dict(self._context)
        self._building: list[type] = []
        self._validate_decorations()
        self._validate()

    def get(self, key: type) -> Any:
        """The service for a key, built on first request and handed back unchanged after.

        A key carrying decorations comes back fully wrapped: the base factory is
        called first, then each decoration wraps what came before it.

        The container is a service of itself: a factory or a verb that asks for
        Container receives the container it resolves from, which is how a
        component reaches the wiring it was composed from without the
        composition threading itself through by hand.

        Args:
            key: The exact type a factory provides.

        Returns:
            The context value, or the factory's instance for the key with its decorations applied.

        Raises:
            UnresolvableKeyError: No factory provides the key.
            DependencyCycleError: The key is, transitively, its own dependency.
        """
        if key is Container:
            return self
        if key in self._instances:
            return self._instances[key]
        factory = self._factories.get(key)
        if factory is None:
            raise UnresolvableKeyError(self._unresolvable_message(key))
        if key in self._building:
            chain = " -> ".join(_key_name(k) for k in [*self._building, key])
            raise DependencyCycleError(f"circular dependencies: {chain}")
        self._building.append(key)
        try:
            resolved = {name: self.get(dep) for name, dep in factory.parameters.items()}
            instance = factory.build(resolved)
            for decoration in self._decorations.get(key, ()):
                instance = self._apply(decoration, key, instance)
        finally:
            self._building.pop()
        self._instances[key] = instance
        return instance

    def _apply(self, decoration: Factory, key: type, instance: object) -> object:
        """One decoration around the instance built so far.

        The parameter asking for the decorated key receives the instance; every
        other parameter resolves as a factory's does, so a decoration can ask
        for unrelated services too.

        Args:
            decoration: The decoration to wrap the instance with.
            key: The key the instance was built under, whose parameter receives it.
            instance: The instance built so far, base factory first.

        Returns:
            The wrapped instance.
        """
        resolved = {
            name: instance if dependency is key else self.get(dependency)
            for name, dependency in decoration.parameters.items()
        }
        return decoration.build(resolved)

    def provided_keys(self) -> list[type]:
        """The keys the wiring declares, factories first, then the context values, the container last.

        The keys a get() answers without failing - a factory's key, a key the
        caller supplied, and the container's own (get answers it with the
        container). Everything that classifies a parameter as a dependency
        rather than an argument reads this: an injector that resolves through
        the container, the tool loader that keeps service parameters out of a
        tool's schema.

        Returns:
            The served keys, in declaration order
        """
        keys = list(self._factories)
        keys.extend(key for key in self._context if key not in self._factories)
        keys.append(Container)
        return keys

    def check(self, fn: Callable[..., Any]) -> None:
        """Fail the build when a verb asks for a key nothing provides.

        A verb's annotated parameters are dependencies like a factory's, so
        they join the wiring validation: a plugin whose attach or detach names
        a key the wiring does not declare fails the build, before the verb
        runs and before the service it asks for is ever needed.

        Args:
            fn: The verb, bound to the plugin instance that declares it.

        Raises:
            UnresolvableKeyError: A parameter annotates a key no factory
                provides and no context value supplies.
        """
        for name, dependency in _verb_parameters(fn).items():
            if dependency is Container or dependency in self._factories or dependency in self._context:
                continue
            raise UnresolvableKeyError(
                f"nothing provides {_key_name(dependency)}: {name!r} of {_verb_name(fn)} asks for it"
            )

    def call(self, fn: Callable[..., Any]) -> Any:
        """Resolve a verb's annotated parameters from the container and invoke it.

        The same resolution walk a factory's dependencies take, so the
        instance a verb receives is the container's own singleton for the key,
        built on this call if nothing asked for it before.

        Args:
            fn: The verb, bound to the plugin instance that declares it.

        Returns:
            The verb's return value.
        """
        resolved = {name: self.get(dependency) for name, dependency in _verb_parameters(fn).items()}
        return fn(**resolved)

    def _unresolvable_message(self, key: type) -> str:
        """Why a key cannot be served, and who the asker must be.

        A get() can only miss for a key the wiring never declares: the build
        fails when a factory's dependency is missing, so the asker here is the
        code calling get(), not a factory.
        """
        provided = ", ".join(sorted(_key_name(k) for k in self._factories))
        return (
            f"nothing provides {_key_name(key)}: nothing in the wiring asks for it, "
            f"so a get() call asked for it directly; the container provides: {provided}"
        )

    def _wanted_by(self, key: type) -> list[type]:
        """The keys that need a key, directly or through other factories, in composition order.

        Args:
            key: The key whose dependents are wanted.

        Returns:
            The keys whose factories ask for it, nearest first.
        """
        wanted: list[type] = []
        pending = [key]
        while pending:
            wanted_key = pending.pop()
            for candidate, factory in self._factories.items():
                if wanted_key in factory.parameters.values() and candidate not in wanted:
                    wanted.append(candidate)
                    pending.append(candidate)
        return wanted

    def _validate_decorations(self) -> None:
        """Fail the build when a decoration has nothing to decorate.

        A decoration wraps the instance another factory builds: its key must
        have a factory, and it must not be one the caller supplied as context,
        whose instance is already built and cannot be rewrapped. A decoration's
        own key resolves through its factory either way, so the dependency
        check below reads its other parameters like a factory's.
        """
        for key, chain in self._decorations.items():
            if key in self._context:
                raise ContainerError(
                    f"cannot decorate {_key_name(key)}: it is a context value, not a factory's instance"
                )
            if key not in self._factories:
                raise UnresolvableKeyError(f"nothing provides {_key_name(key)}: nothing for the decoration to wrap")

    def _validate(self) -> None:
        """Fail the build when a factory or a decoration asks for a key nothing provides.

        Strict validation is the only mode: a wiring mistake is a build error,
        not a get() that may or may not happen.
        """
        wired: list[tuple[type, Factory]] = list(self._factories.items())
        wired.extend((decoration.provides, decoration) for chain in self._decorations.values() for decoration in chain)
        for key, factory in wired:
            for name, dependency in factory.parameters.items():
                if dependency is Container or dependency in self._factories or dependency in self._context:
                    continue
                wanted_by = ", ".join(_key_name(k) for k in self._wanted_by(key))
                raise UnresolvableKeyError(
                    f"nothing provides {_key_name(dependency)}: {name!r} of {_key_name(key)} asks for it"
                    + (f"; {_key_name(key)} is wanted by {wanted_by}" if wanted_by else "")
                )


def make_container(*providers: Provider, context: dict[type, Any] | None = None) -> Container:
    """Build a container from providers, with context instances taking precedence.

    Args:
        providers: The providers whose declarations compose the container.
        context: Instances the caller brings; each wins over any factory claiming its type.

    Returns:
        The container, ready for get().
    """
    return Container(providers=list(providers), context=context)
