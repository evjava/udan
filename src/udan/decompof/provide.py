"""The declaration half of udan.decompof: Provider and provide.

A Provider subclass names the factories it contributes with provide: the
method's return annotation is the key the factory provides, its parameter
annotations are what the factory needs. ``provide(source=SomeClass,
provides=Key)`` declares the same without writing a method - the source class's
``__init__`` supplies both the call and the annotations, which is how a class is
contributed under an interface it implements.

``decorate`` declares the same shape with the other meaning: its factory wraps
the instance another factory builds for the key it provides instead of building
one itself, so a decoration must ask for its own key among its parameters.

A declaration records, it does not resolve: the resolution engine is
udan.decompof.container. Keys are exact types; a parameter that annotates
something else - ``X | None``, ``list[str]``, nothing at all - is a definition
error, not a dependency that silently resolves to nothing.
"""

import inspect
from collections.abc import Callable
from functools import partial
from typing import Any, get_type_hints

BOUND_PARAMETER_NAMES = frozenset({"self", "cls"})
"""Parameter names that name the factory's receiver, never a dependency."""


class DeclarationError(TypeError):
    """A provide declaration cannot be read: no key to provide, or a parameter that names no key."""


def _key_name(key: object) -> str:
    """A key as an error message shows it: the type's name, or the value itself."""
    return getattr(key, "__name__", None) or str(key)


def _required_key(annotation: object, label: str, parameter_name: str) -> type:
    """The key a parameter annotation asks for: exactly the type written.

    Args:
        annotation: The annotation as written on the parameter.
        label: The factory's name, for the error message.
        parameter_name: The parameter's name, for the error message.

    Returns:
        The annotated type.

    Raises:
        DeclarationError: The annotation is not a bare type - a union of two
            types asks for neither in particular, and ``list[str]`` is not a key.
    """
    if not isinstance(annotation, type):
        raise DeclarationError(
            f"{label}: parameter {parameter_name!r} annotates {annotation!r}, which is not a type key"
        )
    return annotation


class Declaration:
    """A factory as declared on a Provider subclass.

    Read by the container when it builds the factory map, and by introspection
    (plugins_system's udan_ioc_deps): ``provides`` is the key the factory is
    registered under, ``parameters`` maps each parameter name to the key it asks
    for. A declaration holds no instances and resolves nothing.
    """

    def __init__(
        self, factory: Callable[..., Any] | type, provides: type | None = None, is_decorator: bool = False
    ) -> None:
        """Record a factory declaration.

        Args:
            factory: A provide-decorated method, or a source class whose ``__init__`` is the factory.
            provides: The key the factory provides; read from the return annotation when omitted.
            is_decorator: Whether the factory wraps another factory's instance instead of building one.

        Raises:
            DeclarationError: The factory names no key, a parameter names no key, or a
                decoration does not ask for the key it provides.
        """
        self._factory = factory
        self._target = factory.__init__ if isinstance(factory, type) else factory
        hints = get_type_hints(self._target)
        if provides is None:
            if "return" not in hints:
                raise DeclarationError(f"{self.label}: no return annotation, so no key to provide")
            provides = _required_key(hints["return"], self.label, "return")
        self._provides = provides
        self._is_decorator = is_decorator
        self._parameters: dict[str, type] = {}
        for name, parameter in inspect.signature(self._target).parameters.items():
            if name in BOUND_PARAMETER_NAMES:
                continue
            if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
                continue
            if name not in hints:
                raise DeclarationError(f"{self.label}: parameter {name!r} has no annotation, so it names no key")
            self._parameters[name] = _required_key(hints[name], self.label, name)
        if is_decorator and provides not in self._parameters.values():
            raise DeclarationError(
                f"{self.label}: a decoration does not ask for {_key_name(provides)}, so it looks like provide"
            )

    @property
    def provides(self) -> type:
        """The key the container registers the factory under."""
        return self._provides

    @property
    def is_decorator(self) -> bool:
        """Whether the factory wraps another factory's instance for the key instead of building one."""
        return self._is_decorator

    @property
    def parameters(self) -> dict[str, type]:
        """The keys the factory asks for, by parameter name."""
        return self._parameters

    @property
    def label(self) -> str:
        """The declaration's name as an error message shows it."""
        return getattr(self._target, "__qualname__", None) or str(self._factory)

    def bound_to(self, provider: Provider) -> Callable[..., Any]:
        """The callable to invoke with the resolved dependencies.

        A source class is its own factory; a method needs the provider instance
        it was declared on.

        Args:
            provider: The provider instance the declaration was read from.

        Returns:
            The callable the container calls with the resolved dependencies as keywords.
        """
        if isinstance(self._factory, type):
            return self._factory
        return partial(self._factory, provider)


class Provider:
    """A container contribution: a subclass names its factories with provide.

    The class is the declaration surface and an instance carries no state, so a
    provider is instantiated once, when the container is built.
    """

    def declarations(self) -> list[tuple[str, Declaration]]:
        """The declarations this provider contributes, base classes first.

        Returns:
            (attribute name, declaration) pairs, in definition order within each class.
        """
        found: list[tuple[str, Declaration]] = []
        for klass in reversed(type(self).__mro__):
            for name, value in vars(klass).items():
                if isinstance(value, Declaration):
                    found.append((name, value))
        return found

    def decorations(self) -> list[tuple[str, Declaration]]:
        """The decorations this provider contributes, base classes first.

        A decoration wraps the instance another factory builds for the key it
        provides; the container applies it once the factories are collected, in
        this order.

        Returns:
            (attribute name, declaration) pairs, in definition order within each class.
        """
        return [(name, declaration) for name, declaration in self.declarations() if declaration.is_decorator]


def _declared(
    name: str,
    factory: Callable[..., Any] | None,
    source: type | None,
    provides: type | None,
    is_decorator: bool,
) -> Declaration:
    """The declaration a provide or decorate call stands for, with its argument rules applied.

    Args:
        name: The entry point's name, as the error messages show it.
        factory: The decorated method, when used as a bare decorator.
        source: A class to contribute through its ``__init__``.
        provides: The key a source class is registered under.
        is_decorator: Whether the declaration wraps another factory's instance.

    Returns:
        The declaration, left in the Provider subclass for the container to read.

    Raises:
        DeclarationError: A source was given without its key, both a factory and
            a source were given, or neither was.
    """
    if source is not None:
        if provides is None:
            raise DeclarationError(f"{source.__name__}: {name}(source=...) needs provides=<key>")
        if factory is not None:
            raise DeclarationError(f"{name} takes a decorated method or source=<class>, not both")
        return Declaration(source, provides, is_decorator=is_decorator)
    if factory is None:
        raise DeclarationError(f"{name} takes a decorated method or source=<class>, not neither")
    return Declaration(factory, is_decorator=is_decorator)


def provide(
    factory: Callable[..., Any] | None = None, *, source: type | None = None, provides: type | None = None
) -> Any:
    """Declare a container factory.

    As a decorator on a method, the method's return annotation is the key it
    provides and its parameter annotations are its dependencies. With
    ``source=SomeClass`` and ``provides=Key``, the class's ``__init__`` is the
    factory and the declaration registers it under Key.

    Args:
        factory: The provide-decorated method, when used as a bare decorator.
        source: A class to contribute through its ``__init__``.
        provides: The key a source class is registered under.

    Returns:
        The declaration, left in the Provider subclass for the container to read.

    Raises:
        DeclarationError: A source was given without its key, both a factory and
            a source were given, or neither was.
    """
    return _declared("provide", factory, source, provides, is_decorator=False)


def decorate(
    factory: Callable[..., Any] | None = None, *, source: type | None = None, provides: type | None = None
) -> Any:
    """Declare a decoration: a factory that wraps the instance another factory builds.

    The declaration is read the way provide reads it, but the factory is called
    with the already built instance handed back as the parameter that asks for
    the key it provides - so that key must be among its parameters, and it is
    an error to declare one that builds fresh instead of wrapping.

    Args:
        factory: The decorate-decorated method, when used as a bare decorator.
        source: A class to contribute through its ``__init__``.
        provides: The key a source class is registered under.

    Returns:
        The declaration, left in the Provider subclass for the container to read.

    Raises:
        DeclarationError: A source was given without its key, both a factory and
            a source were given, or neither was.
    """
    return _declared("decorate", factory, source, provides, is_decorator=True)
