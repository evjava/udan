"""udan.plugins_history: command history and saved queries.

Owns everything history-related that core does not need to know about:
the API interfaces with their no-op dummies (``api_history``), the plugin
tools, the storage implementations (JSONL and SQLite), the storage
selection factories, and the plugin configuration (``HistoryConfig``).

The plugin module declares ``CONFIG = HistoryConfig``, which is how the
config system discovers and displays this plugin's configuration section
(see ``udan config``).

The package is part of udan, so Plugins discovers it on every boot the way
it discovers udan.operator*: the history inserters, the storages behind them
and the CommandExecutedEvent subscription are always composed.
"""
