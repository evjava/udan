"""A minimal dependency-injection container and the plugin framework over it.

Five modules, none of which imports anything of udan:

:mod:`udan.decompof.provide`
    The declaration surface: :class:`udan.decompof.provide.Provider`,
    :func:`udan.decompof.provide.provide` and
    :func:`udan.decompof.provide.decorate`.

:mod:`udan.decompof.container`
    The resolution engine: :func:`udan.decompof.container.make_container`,
    :class:`udan.decompof.container.Container` and the errors a wiring
    mistake raises.

:mod:`udan.decompof.plugin`
    The :class:`udan.decompof.plugin.Plugin` base class: a Provider plus the
    two verbs, ``attach`` and ``detach``, and a plugin's own ``config``.

:mod:`udan.decompof.injector`
    The :class:`udan.decompof.injector.Injector`: resolves what a factory asks
    for by the type it annotates -- the host-side resolution, for a mount that
    happens outside the container.

:mod:`udan.decompof.loader`
    Loading the plugins a module declares under ``PLUGIN``, and calling them
    through the injector.

The public API is re-exported here, so a declaration site reads
``from udan.decompof import Provider, provide, make_container, Plugin``
(``decorate`` for a provider that adds behaviour around an existing service).
The root used to stay import-free while the plugin framework had no in-tree
consumer; now that the container lives here and every consumer imports this
root, the re-export is the point -- a host that vendors the package keeps the
same five-module rule: nothing here imports anything outside the package.
"""

from udan.decompof.container import (
    Container,
    ContainerError,
    DependencyCycleError,
    DuplicateProviderError,
    UnresolvableKeyError,
    make_container,
)
from udan.decompof.plugin import Plugin
from udan.decompof.provide import Declaration, DeclarationError, Provider, decorate, provide

__all__ = [
    "Container",
    "ContainerError",
    "Declaration",
    "DeclarationError",
    "DependencyCycleError",
    "DuplicateProviderError",
    "Plugin",
    "Provider",
    "UnresolvableKeyError",
    "decorate",
    "make_container",
    "provide",
]
