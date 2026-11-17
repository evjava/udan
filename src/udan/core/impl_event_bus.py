"""In-process event bus.

Implements the EventBusAPI extension point: synchronous dispatch of typed
events to handlers registered per event type.
"""

from collections.abc import Callable
from typing import TypeVar

from udan.core.api_event_bus import EventBusAPI

E = TypeVar("E")


class EventBus(EventBusAPI):
    """Synchronous in-process event bus.

    Handlers are called in subscription order on the emitter's thread. Events
    are dispatched only to handlers registered for their exact type, and
    exceptions raised by a handler propagate to the emitter.
    """

    def __init__(self) -> None:
        self._handlers: dict[type, list[Callable]] = {}

    def subscribe(self, event_type: type[E], handler: Callable[[E], None]) -> None:
        """Register a handler for an event type.

        Args:
            event_type: Type of events the handler is interested in.
            handler: Callable invoked with the event instance.
        """
        self._handlers.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type: type[E], handler: Callable[[E], None]) -> None:
        """Take one handler back off an event type.

        Args:
            event_type: The type the handler was registered for.
            handler: The registered callable; an unknown one is ignored, so
                unwinding a wiring that was never made stays quiet.
        """
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    def emit(self, event: object) -> None:
        """Dispatch an event to handlers registered for its type.

        Args:
            event: Event instance to dispatch; its exact type selects the handlers.
        """
        for handler in self._handlers.get(type(event), []):
            handler(event)
