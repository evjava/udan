"""Logger API.

This module defines the logger interface for logging debug messages.
"""


class LoggerAPI:
    """API interface for logger.

    This class defines the public API for logging debug messages.
    """

    is_debug: bool
    is_time: bool

    def debug(self, msg: str) -> None:
        """Log a debug message."""
        raise NotImplementedError

    def info(self, msg: str) -> None:
        """Log an info message."""
        raise NotImplementedError

    def warning(self, msg: str) -> None:
        """Log a warning message."""
        raise NotImplementedError

    def error(self, msg: str) -> None:
        """Log an error message."""
        raise NotImplementedError

    def get_debug_log(self) -> str:
        """Get the debug log as a string (empty unless debug mode is enabled)."""
        raise NotImplementedError

    def get_log(self, show_time: bool = False) -> str:
        """Get the accumulated log as a string regardless of debug mode.

        Args:
            show_time: Force timestamp prefixes (a `debug-time` query showing a
                log captured by a shared logger with no is_time of its own).
        """
        raise NotImplementedError

    def set_debug_mode(self, enabled: bool) -> None:
        """Enable or disable debug mode."""
        raise NotImplementedError
