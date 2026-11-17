"""A plugin: one component's presence in a host, and its contribution to the wiring.

A Plugin is a Provider: the factories and decorations a plugin declares with
provide join the wiring like any provider's (provide.py), and what a
declaration cannot say the two verbs say. ``attach`` and ``detach`` are
concrete no-ops on the base, so a plugin that only contributes declarations
owes nothing else; a plugin that puts something on a host overrides them and
names what it needs by annotating the verb's parameters -- writing ``def
attach(self, app)`` is how a plugin says what it attaches to; writing
``def attach(self, app, events)`` is how it asks for a second
thing. There is no other channel, and nothing is ever passed by name. Who
resolves those annotations is the caller's business: the container validates
them against the wiring and resolves them when the verb runs
(container.py's ``check``/``call``), and a host that mounts imperatively runs
them through the :class:`~udan.decompof.injector.Injector`.

A plugin is built from nothing: the loader passes no arguments, so what a
plugin needs from the world it takes in neither a constructor nor a module
attribute. Whatever a plugin reads to configure itself it stores on
:attr:`Plugin.config` -- or reads nothing, and leaves ``config`` at its
default. Neither verb returns anything, and whatever a plugin puts on a host
it takes back off by the same route it put it on: the plugin's own artifact,
which is why the routes a plugin builds are the plugin's and not the loader's.
"""

from typing import Any

from udan.decompof.provide import Provider


class Plugin(Provider):
    """The container contribution, and the two verbs.

    attach/detach are no-ops on the base, taking the plugin's services as one
    arbitrary set (`*args`/`**kwargs`, by name as the container passes them): a
    plugin that puts something on a host overrides a verb and names the services
    it wants as the override's annotated parameters, and the variadic base keeps
    every such override a valid one. Those annotated parameters are dependencies
    like a factory's: validated before any of them runs, and resolved when it
    does. Declarations must not read instance state; a registration belongs in a
    declaration unless it is something a declaration cannot say, which is what
    the verbs are for.
    """

    #: This plugin's configuration, if it has any. The loader builds a plugin
    #: from no arguments, so this is set by the plugin's own constructor from
    #: whatever sources it reads -- or not set at all, which is why it defaults
    #: to None here.
    config: Any = None

    def attach(self, *args: Any, **kwargs: Any) -> None:
        """Put what the factories opened in place. No-op on the base."""

    def detach(self, *args: Any, **kwargs: Any) -> None:
        """Take what attach put in place back off. No-op on the base."""
