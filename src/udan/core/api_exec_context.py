"""Execution context API.

This module defines the execution context interfaces that tools can use.
"""

from udan.core.api_logger import LoggerAPI
from udan.core.api_symbols_env import SymbolsEnvAPI


class ExecContextAPI(LoggerAPI):
    """API interface for execution context.

    This class defines the public API that tools can use to interact
    with the execution context. Implementations should provide concrete
    implementations of these methods.
    """

    @property
    def symbols_env(self) -> SymbolsEnvAPI | None:
        """Get the symbols environment for this execution context.

        Returns:
            SymbolsEnvAPI instance if available, None otherwise
        """
        raise NotImplementedError

    def claim_named_column(self, name: str) -> bool:
        """Claim a named cattr column for this query.

        Column names are query-local: a name claimed here records that THIS query
        defines it, so a second definition within the same query is a conflict,
        while a name defined only by earlier queries stays free to (re)define.

        Args:
            name: Column name to claim

        Returns:
            True if the name was not claimed earlier in this query, False if
            this query already claimed it
        """
        raise NotImplementedError
