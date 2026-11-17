"""Symbols environment for managing Udan variables.

This module provides the SymbolsEnv class which manages variables
with type information.
"""

from pathlib import Path
from typing import Any

from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_forests import Forest
from udan.core.api_logger import LoggerAPI
from udan.core.api_symbols_env import SymbolsEnvAPI


class SymbolsEnv(SymbolsEnvAPI):
    """Environment for managing Udan variables.

    This class handles variable storage with type information
    and loading from environment files.
    """

    def __init__(self, vars_path: str, logger: LoggerAPI) -> None:
        """Initialize symbols environment.

        Args:
            vars_path: Path to variables file
            logger: Debug logger instance
        """
        self._vars_path = vars_path
        self._logger = logger
        # Single dict storing (value, type) tuples
        self.symbols: dict[str, tuple[Any, str]] = {}
        # Load variables from .env file
        self._load_env_variables()

    def _load_env_variables(self) -> None:
        """Load variables from vars_path file into the symbols dict.

        Parses the variables file (if it exists) and loads key=value pairs as variables.
        Lines starting with # are treated as comments and ignored.
        Empty lines are ignored.

        Example vars file:
            # Project variables
            udan_src=src/udan
            test_dir=tests/resources
            fruit=apple
        """
        env_path = Path(self._vars_path).expanduser()
        if not env_path.exists():
            return

        try:
            for line in env_path.read_text().splitlines():
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith("#"):
                    continue
                # Parse key=value
                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    # Create Forest with the value as a single string item
                    forest = Forest.from_items([value])
                    self.set_variable(key, forest, type="str")
                    self._logger.debug(f"Loaded variable from {env_path}: {key}={value}")
        except Exception as e:
            self._logger.debug(f"Error loading variables file {env_path}: {e}")

    def set_variable(self, name: str, value: Any, type: str = "query", ctx: ExecContextAPI | None = None) -> None:
        """Store a variable with its type.

        Args:
            name: Variable name
            value: Value to store (Forest, str, int, etc.)
            type: Variable type (defaults to "query" for tool results)
            ctx: Execution context for query-time logging. When None (startup
                 loading or direct API usage), the call is not logged.
        """
        self.symbols[name] = (value, type)
        if ctx is not None:
            ctx.debug(f"Set variable '{name}' with type '{type}'")

    def get_variable_with_type(self, name: str) -> tuple[Any, str]:
        """Get a variable with its type information.

        Args:
            name: Variable name

        Returns:
            Tuple of (value, type)

        Raises:
            KeyError: If variable is not defined
        """
        if name not in self.symbols:
            raise KeyError(f"Variable '{name}' is not defined. Available variables: {list(self.symbols.keys())}")
        return self.symbols[name]

    def has_variable(self, name: str) -> bool:
        """Check if a variable is defined.

        Args:
            name: Variable name

        Returns:
            True if variable exists, False otherwise
        """
        return name in self.symbols

    def clear_variables(self) -> None:
        """Clear all variables from the symbols dict."""
        self.symbols.clear()
        self._logger.debug("Cleared all variables")

    def list_variables(self) -> list[str]:
        """List all defined variable names.

        Returns:
            List of variable names
        """
        return list(self.symbols.keys())
