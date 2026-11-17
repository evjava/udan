"""Execution context for query execution.

This module provides the ExecContext class that implements ExecContextAPI.
This is a per-query execution context that provides logging.

The ExecContext is created for each query execution and passed to the
applicators applying the chain, for logging purposes.
"""

from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_logger import LoggerAPI
from udan.core.api_symbols_env import SymbolsEnvAPI


class ExecContext(ExecContextAPI):
    """Execution context implementation for query execution.

    This provides logging capabilities for the applicators applying the chain.
    Instances are created per-query and passed to those applicators.

    The ExecContext stores only query-specific state (symbols_env).
    Global dependencies are managed by the injector (udan.core_tools_loading.api_function_injector,
    composed in impl_ioc).
    """

    def __init__(
        self,
        logger: LoggerAPI,
        symbols_env: SymbolsEnvAPI | None = None,
    ) -> None:
        """Initialize the execution context.

        Args:
            logger: Logger for debug/info/warning/error messages.
            symbols_env: Symbols environment for this query.
        """
        self._logger = logger
        self._symbols_env = symbols_env
        # Named cattr column names claimed by this query (query-local namespace)
        self._claimed_named_columns: set[str] = set()

    def claim_named_column(self, name: str) -> bool:
        """Claim a named cattr column for this query; False if already claimed here."""
        if name in self._claimed_named_columns:
            return False
        self._claimed_named_columns.add(name)
        return True

    @property
    def symbols_env(self) -> SymbolsEnvAPI | None:
        """Get the symbols environment for this execution context.

        Returns:
            SymbolsEnvAPI instance if available, None otherwise
        """
        return self._symbols_env

    def debug(self, msg: str) -> None:
        """Log a debug message."""
        self._logger.debug(msg)

    def info(self, msg: str) -> None:
        """Log an info message."""
        self._logger.info(msg)

    def warning(self, msg: str) -> None:
        """Log a warning message."""
        self._logger.warning(msg)

    def error(self, msg: str) -> None:
        """Log an error message."""
        self._logger.error(msg)

    def get_debug_log(self) -> str:
        """Get the debug log as a string."""
        return self._logger.get_debug_log()

    def set_debug_mode(self, enabled: bool) -> None:
        """Enable or disable debug mode."""
        self._logger.set_debug_mode(enabled)

    @property
    def is_debug(self) -> bool:
        """Check if debug mode is enabled."""
        return self._logger.is_debug

    @is_debug.setter
    def is_debug(self, value: bool) -> None:
        """Set debug mode.

        Args:
            value: True to enable debug mode, False to disable
        """
        self._logger.set_debug_mode(value)

    @property
    def is_time(self) -> bool:
        """Check if time-showing mode (debug-time token) is enabled."""
        return self._logger.is_time

    @is_time.setter
    def is_time(self, value: bool) -> None:
        """Set time-showing mode.

        Args:
            value: True to show the elapsed execution time, False to hide it
        """
        self._logger.is_time = value
