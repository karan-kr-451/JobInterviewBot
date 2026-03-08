"""
core/event_bus.py — Decoupled inter-module publish/subscribe messaging.

Modules communicate via events — NEVER via direct references.
Eliminates circular imports and tight coupling between layers.

Usage:
    from antigravity.core.event_bus import bus, EVT_TRANSCRIPT_READY
    bus.subscribe(EVT_TRANSCRIPT_READY, my_handler)
    bus.publish(EVT_TRANSCRIPT_READY, "Hello world")
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from typing import Callable, Any

logger = logging.getLogger(__name__)

# ── Event name constants (never use magic strings) ────────────────────────────
EVT_TRANSCRIPT_READY = "transcript.ready"
EVT_RESPONSE_READY   = "response.ready"
EVT_RECORDING_START  = "recording.start"
EVT_RECORDING_STOP   = "recording.stop"
EVT_ERROR            = "app.error"
EVT_WORKER_DEAD      = "worker.dead"
EVT_BACKEND_SWITCHED = "backend.switched"
EVT_STATUS_UPDATE    = "status.update"
EVT_DOCUMENTS_UPDATED= "documents.updated"
EVT_TOKEN_USAGE_READY= "token_usage.ready"
EVT_CLASSIFICATION_READY = "classification.ready"
EVT_SHUTDOWN         = "app.shutdown"


class EventBus:
    """
    Thread-safe publish/subscribe event bus.
    Exceptions from listeners are caught and logged — never propagate.
    """

    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable]] = defaultdict(list)
        self._lock = threading.Lock()

    def subscribe(self, event: str, callback: Callable) -> None:
        with self._lock:
            if callback not in self._listeners[event]:
                self._listeners[event].append(callback)

    def unsubscribe(self, event: str, callback: Callable) -> None:
        with self._lock:
            try:
                self._listeners[event].remove(callback)
            except ValueError:
                pass

    def publish(self, event: str, data: Any = None) -> None:
        with self._lock:
            callbacks = list(self._listeners.get(event, []))
        for cb in callbacks:
            try:
                cb(data)
            except Exception as e:
                logger.error("[EVENTBUS] %s handler %s error: %s", event, cb, e)

    def clear(self, event: str | None = None) -> None:
        with self._lock:
            if event is None:
                self._listeners.clear()
            else:
                self._listeners.pop(event, None)


# ── Process-level singleton ───────────────────────────────────────────────────
bus = EventBus()
