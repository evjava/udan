"""Symbols environment API.

This module defines the symbol environment (variable management) interface.
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from udan.core.api_exec_context import ExecContextAPI


class SymbolsEnvAPI:
    """API interface for symbol environment (variable management).

    This class defines the public API for managing variables and symbols
    in the execution context with type information.
    """

    def set_variable(self, name: str, value: Any, type: str = "query", ctx: ExecContextAPI | None = None) -> None:
        """Store a variable with its type.

        Args:
            name: Variable name
            value: Value to store (Forest, str, int, etc.)
            type: Variable type (defaults to "query" for tool results)
            ctx: Execution context for query-time logging. When None (startup
                 loading or direct API usage), the call is not logged.
        """
        raise NotImplementedError

    def get_variable_with_type(self, name: str) -> tuple[Any, str]:
        """Get a variable with its type information.

        Args:
            name: Variable name

        Returns:
            Tuple of (value, type)

        Raises:
            KeyError: If variable not found
        """
        raise NotImplementedError

    def has_variable(self, name: str) -> bool:
        """Check if a variable exists.

        Args:
            name: Variable name

        Returns:
            True if variable exists, False otherwise
        """
        raise NotImplementedError

    def list_variables(self) -> list[str]:
        """List all defined variable names.

        Returns:
            List of variable names
        """
        raise NotImplementedError

    def clear_variables(self) -> None:
        """Clear all defined variables."""
        raise NotImplementedError
