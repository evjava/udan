"""Public API for the application event bus.

This module defines the event bus extension point. Publishers emit typed
events instead of calling concrete consumers directly; consumers subscribe
to the event types they care about (e.g. history logging subscribes to
CommandExecutedEvent to record command executions).
"""

from collections.abc import Callable
from typing import Protocol, TypeVar

from pydantic import BaseModel

from udan.core.api_forests import Forest

E = TypeVar("E")


class CommandExecutedEvent(BaseModel):
    """Event emitted after a command (query) execution has finished.

    Fields mirror the arguments of HistoryLoggerAPI.log; the history loggers
    subscribe to this event type and store the entries.
    """

    command: str
    success: bool
    forest: Forest
    error: str | None = None
    comment: str | None = None


class CommandLogSink(Protocol):
    """Service that can record a command execution.

    Structural type for services subscribed to CommandExecutedEvent: their
    log() accepts exactly the event's fields. Implemented by the history
    loggers; declared via a plugin module's SUBSCRIBE.
    """

    def log(
        self,
        command: str,
        success: bool,
        forest: Forest,
        error: str | None = None,
        comment: str | None = None,
    ) -> None:
        """Record one command execution.

        Args:
            command: The query/command that was executed.
            success: Whether the command executed successfully.
            forest: The resulting Forest (even on error, may be partial).
            error: Error message if the command failed, None otherwise.
            comment: Optional comment describing the purpose of the command.
        """
        ...


class EventBusAPI:
    """API interface for the application event bus.

    This class defines the public API for emitting and receiving application
    events. Publishers call emit() with an event instance; subscribers register
    handlers for concrete event types.
    """

    def subscribe(self, event_type: type[E], handler: Callable[[E], None]) -> None:
        """Register a handler for an event type.

        Args:
            event_type: Type of events the handler is interested in.
            handler: Callable invoked with the event instance.
        """
        raise NotImplementedError

    def unsubscribe(self, event_type: type[E], handler: Callable[[E], None]) -> None:
        """Take one handler back off an event type.

        Args:
            event_type: The type the handler was registered for.
            handler: The registered callable; an unknown one is ignored, so a
                teardown of a wiring that was never made stays quiet.
        """
        raise NotImplementedError

    def emit(self, event: object) -> None:
        """Dispatch an event to handlers registered for its type.

        Args:
            event: Event instance to dispatch; its exact type selects the handlers.
        """
        raise NotImplementedError
