"""Debug logging for execution context."""

import time
from typing import Literal

from udan.core.api_logger import LoggerAPI


def _format_time_prefix(t: float) -> str:
    millis = int((t - int(t)) * 1000)
    parts = time.localtime(t)
    hours = parts.tm_hour
    minutes = parts.tm_min
    return f"[{hours:02d}:{minutes:02d}.{millis:03d}]"


LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class DebugLogger(LoggerAPI):
    """Handles debug logging for execution context."""

    def __init__(self, log_time: bool = False) -> None:
        """Initialize debug logger.

        Args:
            log_time: Whether to include timestamp prefix in log messages.
        """
        self.is_debug: bool = False
        self.is_time: bool = False
        self._log: list[tuple[float, str]] = []
        self._log_time: bool = log_time

    def _append_log(self, level: LogLevel, msg: str) -> None:
        # The timestamp is captured per line; whether it is rendered as a prefix
        # is decided by get_log, so lines logged before `debug-time` is
        # interpreted get their prefix too.
        self._log.append((time.time(), f"[{level}] {msg}"))

    def debug(self, msg: str) -> None:
        self._append_log("DEBUG", msg)

    def info(self, msg: str) -> None:
        self._append_log("INFO", msg)

    def warning(self, msg: str) -> None:
        self._append_log("WARNING", msg)

    def error(self, msg: str) -> None:
        self._append_log("ERROR", msg)

    def get_debug_log(self) -> str:
        if self.is_debug:
            return self.get_log()
        else:
            return ""

    def get_log(self, show_time: bool = False) -> str:
        # Timestamp prefixes are shown when enabled via config (udan_log_time),
        # via the `debug-time` marker (is_time) for this query's log only, or
        # when the caller asks for them (shared app logger rendered for a
        # `debug-time` query).
        if show_time or self._log_time or self.is_time:
            return "\n".join([f"# {_format_time_prefix(t)} {msg}" for t, msg in self._log])
        return "\n".join([f"# {msg}" for _, msg in self._log])

    def set_debug_mode(self, enabled: bool) -> None:
        """Enable or disable debug mode."""
        self.is_debug = enabled
