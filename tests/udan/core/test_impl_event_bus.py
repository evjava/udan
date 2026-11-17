"""Tests for the event bus and the history subscription to command events."""

import json
from pathlib import Path

from udan.core.api_event_bus import CommandExecutedEvent, EventBusAPI
from udan.core.api_forests import EMPTY_FOREST
from udan.core.config import UdanConfig
from udan.core.impl_event_bus import EventBus
from udan.core.impl_ioc import create_udan_container
from udan.core.impl_udan_context import UdanContext


def test_event_bus_dispatches_to_subscriber():
    """Test that emit passes the event to the subscribed handler."""
    bus = EventBus()
    received = []
    bus.subscribe(CommandExecutedEvent, received.append)

    event = CommandExecutedEvent(command="vars", success=True, forest=EMPTY_FOREST)
    bus.emit(event)

    assert received == [event]


def test_event_bus_calls_handlers_in_subscription_order():
    """Test that handlers registered for the same event type run in order."""
    bus = EventBus()
    calls = []
    bus.subscribe(CommandExecutedEvent, lambda event: calls.append("first"))
    bus.subscribe(CommandExecutedEvent, lambda event: calls.append("second"))

    bus.emit(CommandExecutedEvent(command="vars", success=True, forest=EMPTY_FOREST))

    assert calls == ["first", "second"]


def test_event_bus_dispatches_only_to_matching_type():
    """Test that handlers of other event types are not called."""
    bus = EventBus()
    received = []
    bus.subscribe(CommandExecutedEvent, received.append)

    class OtherEvent:
        pass

    bus.emit(OtherEvent())

    assert received == []


def test_event_bus_emit_without_subscribers_is_noop():
    """Test that emitting with no subscribers does not raise."""
    bus = EventBus()

    bus.emit(CommandExecutedEvent(command="vars", success=True, forest=EMPTY_FOREST))


def test_event_bus_satisfies_api():
    """Test that EventBus implements the EventBusAPI interface."""
    assert isinstance(EventBus(), EventBusAPI)


def test_ioc_event_bus_subscribes_history_logger(tmp_path, monkeypatch):
    """Test that the IOC-provided bus writes history entries on command events."""
    history_path = tmp_path / "history.jsonl"
    monkeypatch.setenv("UDAN_HISTORY_PATH", str(history_path))
    container = create_udan_container(UdanConfig())
    ctx = container.get(UdanContext)
    ctx.container = container
    ctx._register_dependency_providers_from_module("udan.plugins_history.plugins_history")

    bus = container.get(EventBusAPI)
    bus.emit(CommandExecutedEvent(command="vars", success=True, forest=EMPTY_FOREST))

    with open(history_path) as f:
        entry = json.loads(f.readline().strip())
    assert entry["command"] == "vars"
    assert entry["success"] is True


def test_udan_context_logs_history_via_event_bus(tmp_path, monkeypatch):
    """Test that UdanContext.log_history reaches history storage through the bus."""
    history_path = tmp_path / "history.jsonl"
    monkeypatch.setenv("UDAN_HISTORY_PATH", str(history_path))
    container = create_udan_container(UdanConfig())
    ctx = container.get(UdanContext)
    ctx.container = container
    ctx._register_dependency_providers_from_module("udan.plugins_history.plugins_history")

    ctx._log_history("raiser", success=False, forest=EMPTY_FOREST, error="boom", comment="testing")

    with open(history_path) as f:
        entry = json.loads(f.readline().strip())
    assert entry["command"] == "raiser"
    assert entry["success"] is False
    assert entry["error"] == "boom"
    assert entry["comment"] == "testing"
    assert Path(history_path).exists()


def test_re_registering_plugin_module_does_not_duplicate_subscription(tmp_path, monkeypatch):
    """Test that SUBSCRIBE wiring happens once per module, not once per registration."""
    history_path = tmp_path / "history.jsonl"
    monkeypatch.setenv("UDAN_HISTORY_PATH", str(history_path))
    container = create_udan_container(UdanConfig())
    ctx = container.get(UdanContext)
    ctx.container = container
    module_name = "udan.plugins_history.plugins_history"

    ctx._register_dependency_providers_from_module(module_name)
    ctx._register_dependency_providers_from_module(module_name)

    bus = container.get(EventBusAPI)
    bus.emit(CommandExecutedEvent(command="vars", success=True, forest=EMPTY_FOREST))

    entries = history_path.read_text().strip().splitlines()
    assert len(entries) == 1


def test_detach_unwires_the_boot_subscriptions(tmp_path, monkeypatch):
    """Test that detach takes back off the bus what load_core wired, so nothing records after it."""
    history_path = tmp_path / "history.jsonl"
    monkeypatch.setenv("UDAN_HISTORY_PATH", str(history_path))
    container = create_udan_container(UdanConfig())
    ctx = container.get(UdanContext)
    ctx.container = container
    ctx.load_core()

    ctx.detach()
    container.get(EventBusAPI).emit(CommandExecutedEvent(command="vars", success=True, forest=EMPTY_FOREST))

    assert not history_path.exists()


def test_detach_of_a_context_that_wired_nothing_is_quiet():
    """Test that unwinding an empty wiring does not raise."""
    EventBus().unsubscribe(CommandExecutedEvent, lambda event: None)

    bus = EventBus()
    bus.unsubscribe(CommandExecutedEvent, lambda event: None)

    assert isinstance(bus, EventBusAPI)
