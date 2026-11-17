"""The second plugin of the boot test: argument-free verbs, recorded like the first's."""

from tests.udan_plugins_boot.recording import RECORD
from udan.decompof import Plugin

DOMAIN = "boot_beta"


class BetaPlugin(Plugin):
    """Records its verbs, contributing no services."""

    def attach(self) -> None:
        RECORD.append("beta")

    def detach(self) -> None:
        RECORD.append("-beta")


PLUGIN = BetaPlugin
