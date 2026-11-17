"""The first plugin of the boot test: attach takes the core config, detach takes nothing."""

from tests.udan_plugins_boot.recording import RECORD
from udan.core.config import UdanConfig
from udan.decompof import Plugin

DOMAIN = "boot_alpha"


class AlphaPlugin(Plugin):
    """Records its verbs, and asks the container for the boot's config."""

    def attach(self, config: UdanConfig) -> None:
        RECORD.append(f"alpha:{type(config).__name__}")

    def detach(self) -> None:
        RECORD.append("-alpha")


PLUGIN = AlphaPlugin
