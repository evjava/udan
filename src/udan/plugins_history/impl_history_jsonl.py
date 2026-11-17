"""Command history logging for udan.

This module provides functionality to log command execution history to a JSONL file.
"""

import json
import os
import re
from collections.abc import Iterable
from datetime import datetime
from itertools import islice
from pathlib import Path
from typing import Any

from udan.core.api_forests import Forest
from udan.plugins_history.api_history import HistoryLoggerAPI

# Bytes read per step when scanning the history file backwards
_REVERSE_READ_CHUNK_SIZE = 8192


def _iter_lines_reversed(path: Path, chunk_size: int = _REVERSE_READ_CHUNK_SIZE) -> Iterable[str]:
    """Yield the lines of a file from the last line to the first.

    Reads backwards in chunks, so a consumer that stops early never reads the
    whole file. Lines are yielded without their terminating newline.

    Args:
        path: Path to the file to read
        chunk_size: Number of bytes read per step

    Yields:
        File lines in reverse order
    """
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        pos = f.tell()
        pending = b""
        while pos > 0:
            step = min(chunk_size, pos)
            pos -= step
            f.seek(pos)
            # The first part belongs to a line whose end was read earlier; keep
            # it for the next step. The rest are complete lines.
            parts = (f.read(step) + pending).split(b"\n")
            pending = parts.pop(0)
            for line in reversed(parts):
                yield line.decode("utf-8")
        if pending:
            yield pending.decode("utf-8")


class HistoryLogger(HistoryLoggerAPI):
    """Logger for udan command execution history.

    Logs each command execution with timestamp, command, success status,
    and statistics about the results (total items, depth-0 items).
    """

    def __init__(self, history_path: str | None = None) -> None:
        """Initialize history logger.

        Args:
            history_path: Path to history JSONL file. If None, history logging is disabled.
        """
        self._history_path = Path(history_path).expanduser() if history_path else None

    @property
    def history_path(self) -> Path | None:
        """Get the history file path.

        Returns:
            Path to history file, or None if history is disabled
        """
        return self._history_path

    def log(
        self,
        command: str,
        success: bool,
        forest: Forest,
        error: str | None = None,
        comment: str | None = None,
    ) -> None:
        """Log a command execution to history.

        Args:
            command: The query/command that was executed
            success: Whether the command executed successfully
            forest: The resulting Forest (even on error, may be partial)
            error: Error message if command failed, None otherwise
            comment: Optional comment describing the purpose/goal of the command
        """
        if not self._history_path:
            return

        # Calculate statistics
        total_items = len(forest.items)
        depth_zero_items = sum(1 for depth, _ in forest.as_pairs() if depth == 0)

        # Create history entry
        entry = {
            "timestamp": datetime.now().isoformat(),
            "command": command,
            "success": success,
            "total_items": total_items,
            "depth_zero_items": depth_zero_items,
        }

        if error:
            entry["error"] = error

        if comment:
            entry["comment"] = comment

        # Append to history file
        try:
            self._history_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._history_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            # Fail silently if history write fails
            pass

    def get_history(
        self,
        pattern: str | None = None,
        limit: int | None = None,
        success: bool | None = None,
        min_command_length: int | None = None,
    ) -> Iterable[dict[str, Any]]:
        """Read recent history entries, newest first.

        Entries are read from the end of the file backwards (the log is
        append-only, so file order is oldest to newest). The returned iterable
        is lazy: iteration stops as soon as `limit` matching entries have been
        produced, and entries beyond it are never read or parsed.

        Args:
            limit: Maximum number of entries to return (most recent first).
                   If None, returns all entries. A negative value is treated as
                   no limit.
            pattern: Optional regex pattern to filter entries by command text.
                     Only entries whose command matches the pattern are returned.
            success: Optional success status to filter by; only entries with this
                     status are returned (default: None = any status).
            min_command_length: Optional minimum command length; only entries whose
                     command is at least this many characters are returned
                     (default: None = no minimum).

        Returns:
            Iterable of history entry dictionaries, newest first
        """
        history_path = self._history_path
        if not history_path or not history_path.exists():
            return []

        # Compile pattern here so an invalid regex raises at call time
        regex = re.compile(pattern, re.IGNORECASE) if pattern is not None else None
        if limit is not None and limit < 0:
            limit = None

        def generate() -> Iterable[dict[str, Any]]:
            for line in _iter_lines_reversed(history_path):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    entry = json.loads(stripped)
                except json.JSONDecodeError:
                    # Skip lines that are not valid JSON, e.g. a partially written entry
                    continue
                if not isinstance(entry, dict):
                    continue
                if regex is not None and not regex.search(entry.get("command", "")):
                    continue
                if success is not None and entry.get("success", True) != success:
                    continue
                if min_command_length is not None and len(str(entry.get("command", ""))) < min_command_length:
                    continue
                yield entry

        entries = generate()
        return islice(entries, limit) if limit is not None else entries
