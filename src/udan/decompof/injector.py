"""Resolving what a component needs by the type it asks for.

A factory names its dependencies by annotating its parameters; the injector
holds the instances the host already has and hands over the one whose type
satisfies the annotation. Nothing is passed by name, and nothing is constructed
here -- so what a component receives is the caller's own object rather than a
copy of it. Ask for a type the caller provided and you get *that* instance; ask
for a protocol you declared yourself and you get whichever provided instance
offers that surface.

When the provided instances do not satisfy a parameter, and the injector was
:meth:`Injector.served_by` a source -- the IoC container, typically -- the
source is asked for the bare type before the parameter counts as unresolvable.
The host names the things it has; the source covers the things it builds; the
component says what it needs and never learns which was which.
"""

import inspect
import types
from collections.abc import Callable, Mapping
from typing import Any, Union, get_args, get_origin

Factory = Callable[..., Any]


def unwrap_optional(annotation: Any) -> Any:
    """The type ``X | None`` asks for, or the annotation unchanged.

    A union of two real types asks for neither in particular, so it resolves to
    nothing -- and raises, when the parameter has no default to fall back to.
    """
    if isinstance(annotation, types.UnionType) or get_origin(annotation) is Union:
        members = [member for member in get_args(annotation) if member is not types.NoneType]
        return members[0] if len(members) == 1 else None
    return annotation


class DependencyError(RuntimeError):
    """A factory's dependencies cannot be satisfied."""


class UnresolvableDependencyError(DependencyError):
    """A factory asks for a type nothing provides."""


class AmbiguousDependencyError(DependencyError):
    """More than one provided instance satisfies a factory's annotation."""


class Injector:
    """The instances a host offers, resolved from the types a factory annotates.

    A parameter is resolved by its annotation: exactly, when an instance was
    provided as that type, otherwise structurally, otherwise -- when the
    injector was served by one -- from the source. Two candidates for one
    annotation is not a resolution -- it is a wiring mistake, and it raises.
    """

    def __init__(self) -> None:
        self._instances: dict[type[Any], Any] = {}
        self._source: Callable[[type[Any]], Any] | None = None

    def provide(self, *instances: Any) -> Injector:
        """Offer instances, each keyed by its own type; the last of a type wins."""
        for instance in instances:
            self._instances[type(instance)] = instance
        return self

    def served_by(self, source: Callable[[type[Any]], Any]) -> Injector:
        """Also ask ``source`` for a bare type the provided instances do not satisfy.

        The source is what builds services -- the IoC container's ``get``,
        typically -- and it is handed a callable, not an import, so this module
        stays framework-free. What the source raises propagates untouched: a
        missing factory says more than a wrapper would, and the mount fails
        either way, which is the contract.
        """
        self._source = source
        return self

    def resolve(self, annotation: Any, instances: Mapping[type[Any], Any] | None = None) -> Any | None:
        """The instance satisfying ``annotation``, or None.

        Looked up in ``instances`` when given -- the per-component scope -- and in
        this injector otherwise. An annotation need not be the providing class:
        a protocol declared by a component matches whatever instance offers its
        surface, which is what lets the component stay ignorant of the class it
        is handed. A parameterised annotation such as ``list[str]`` resolves by
        its origin, since ``list[str]`` is not itself a type and a caller who
        wrote it meant a list.
        """
        candidates = self._instances if instances is None else instances
        annotation = unwrap_optional(annotation)
        if (instance := candidates.get(annotation)) is not None:
            return instance
        origin = get_origin(annotation)
        if isinstance(annotation, type) or origin is not None:
            matches = [instance for instance in candidates.values() if isinstance(instance, origin or annotation)]
            if len(matches) > 1:
                msg = f"{annotation} is satisfied by {len(matches)} provided instances"
                raise AmbiguousDependencyError(msg)
            return matches[0] if matches else None
        return None

    def _from_source(self, annotation: Any) -> Any | None:
        """The source's answer to a bare-type annotation, or None.

        Only a bare type can be a source's key: a union of two types asks for
        neither in particular, and an unannotated parameter has no type to ask
        for -- both fall through, to the default or the raise. What the source
        raises is what the caller sees.
        """
        if self._source is None:
            return None
        annotation = unwrap_optional(annotation)
        if not isinstance(annotation, type):
            return None
        return self._source(annotation)

    def arguments(self, factory: Factory, scope: Mapping[type[Any], Any] | None = None) -> dict[str, Any]:
        """The keyword arguments to call ``factory`` with.

        The scope wins over the provided instances, which is how each component
        is offered a plugin of its own while the host and the rest come from
        this one injector; the provided instances win over the source, because
        what the host holds is what the host means to hand over. The scope and
        the instances are matched the same way, structurally included, so a
        component can be typed by a protocol of its own. A parameter that
        resolves to nothing raises unless it has a default -- the documented
        way for a component to say a dependency is optional.
        """
        resolved: dict[str, Any] = {}
        for name, parameter in inspect.signature(factory).parameters.items():
            if parameter.kind not in (parameter.POSITIONAL_OR_KEYWORD, parameter.KEYWORD_ONLY):
                continue
            if (instance := self.resolve(parameter.annotation, scope)) is None:
                instance = self.resolve(parameter.annotation)
            if instance is None:
                instance = self._from_source(parameter.annotation)
            if instance is not None:
                resolved[name] = instance
            elif parameter.default is parameter.empty:
                module = getattr(factory, "__module__", "<unknown>")
                msg = f"{module} asks for {name!r} of {parameter.annotation!r}, which nothing provides"
                raise UnresolvableDependencyError(msg)
        return resolved

    def call(self, factory: Factory, scope: Mapping[type[Any], Any] | None = None) -> Any:
        """Call ``factory`` with its annotated dependencies."""
        return factory(**self.arguments(factory, scope))
