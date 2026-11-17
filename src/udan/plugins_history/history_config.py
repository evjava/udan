"""Configuration for the history plugin.

The schema lives next to the plugin that consumes it (plugin-owned config).
It is registered into the config system by declaring ``CONFIG`` in the
plugin module, which is how ``udan config`` discovers and shows this section.

Environment variables (prefix ``UDAN_HISTORY_``, so every knob of this
plugin is namespaced under the plugin name):
    UDAN_HISTORY_PATH: Path to the history storage file
        (default: "./.udan/history.db"; ".jsonl" and ".db" extensions select
        the JSONL and SQLite storage implementations)
    UDAN_HISTORY_SAVED_PATH: Path to the saved queries storage file
        (default: "./.udan/saved.db"; same extension rules; a legacy
        favorites.db next to it is migrated on first open)

Precedence is pydantic-settings' own: init kwargs > environment variables
> .env file > field defaults.
"""

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from udan.core.utils_pydantic import ConfigBaseSettings, ExpandedPath


class HistoryConfig(ConfigBaseSettings):
    """Configuration for the history and saved queries storages.

    Field names carry no "history" prefix: the env prefix and the
    "history" config section already provide the namespace.

    Unknown keys raise a ValidationError (extra="forbid"), so typos in
    overrides are loud instead of silently ignored.
    """

    model_config = SettingsConfigDict(
        env_prefix="UDAN_HISTORY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
        populate_by_name=True,
    )

    path: ExpandedPath = Field(
        default="./.udan/history.db",
        description="History storage file path (.jsonl or .db selects the implementation)",
    )
    saved_path: ExpandedPath = Field(
        default="./.udan/saved.db",
        description="Saved queries storage file path (.jsonl or .db selects the implementation)",
    )
