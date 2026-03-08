"""
core/event_bus.py - Simple publish/subscribe event bus.

Decouples audio → transcription → LLM → UI layers.
Any thread can publish; any thread can subscribe.

Events used in this system:
  "transcript_ready"    payload: {"text": str}
  "llm_response_start"  payload: {"question": str}
  "llm_token"           payload: {"token": str}
  "llm_response_done"   payload: {"question": str, "response": str}
  "status_update"       payload: {"message": str, "recording": bool}
  "shutdown"            payload: {}
"""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any, Callable, Dict, List


Listener = Callable[[Dict[str, Any]], None]


class EventBus:
    """
    Thread-safe publish/subscribe event bus.

    Usage:
        bus = EventBus()
        bus.subscribe("transcript_ready", my_handler)
        bus.publish("transcript_ready", {"text": "Hello world"})
    """

    def __init__(self) -> None:
        self._lock:      threading.RLock                           = threading.RLock()
        self._listeners: Dict[str, List[Listener]]                 = defaultdict(list)

    # ── Subscription ──────────────────────────────────────────────────────────

    def subscribe(self, event: str, listener: Listener) -> None:
        """Register a callable to receive payloads for the given event name."""
        with self._lock:
            if listener not in self._listeners[event]:
                self._listeners[event].append(listener)

    def unsubscribe(self, event: str, listener: Listener) -> None:
        """Remove a previously registered listener."""
        with self._lock:
            try:
                self._listeners[event].remove(listener)
            except ValueError:
                pass

    # ── Publishing ────────────────────────────────────────────────────────────

    def publish(self, event: str, payload: Dict[str, Any] | None = None) -> None:
        """
        Dispatch an event to all registered listeners.

        Listeners are called synchronously in the publishing thread.
        Exceptions in listeners are caught and logged – they never propagate
        to the publisher so a bad subscriber cannot crash the pipeline.
        """
        if payload is None:
            payload = {}

        with self._lock:
            listeners = list(self._listeners.get(event, []))

        for fn in listeners:
            try:
                fn(payload)
            except Exception as exc:
                # Import lazily to avoid circular dependency at module level
                try:
                    from core.logger import get_logger
                    get_logger("event_bus").exception(
                        "Listener %s raised on event '%s': %s", fn, event, exc
                    )
                except Exception:
                    import traceback
                    traceback.print_exc()

    # ── Utility ───────────────────────────────────────────────────────────────

    def clear(self, event: str | None = None) -> None:
        """Remove all listeners for an event, or all events if event is None."""
        with self._lock:
            if event is None:
                self._listeners.clear()
            else:
                self._listeners.pop(event, None)


# ---------------------------------------------------------------------------
# Module-level singleton – shared across the entire process
# ---------------------------------------------------------------------------
_bus: EventBus | None = None
_bus_lock = threading.Lock()


def get_bus() -> EventBus:
    """Return the process-level singleton EventBus."""
    global _bus
    if _bus is None:
        with _bus_lock:
            if _bus is None:
                _bus = EventBus()
    return _bus
