"""A plugin whose attach asks for a key nothing provides."""

from udan.decompof import Plugin


class Unprovided:
    """A service no provider in the boot declares."""


class UnresolvedPlugin(Plugin):
    """Names a dependency the wiring does not declare."""

    def attach(self, service: Unprovided) -> None:
        raise AssertionError("a verb asking for an unprovided key must fail the build, not run")


PLUGIN = UnresolvedPlugin
