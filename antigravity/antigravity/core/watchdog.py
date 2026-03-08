"""
core/watchdog.py — Health monitor for all worker threads.

Periodically queries all registered BaseWorkers.
If a worker's is_healthy property returns False (heartbeat stale > 30s) or
if the thread has died entirely, it publishes EVT_WORKER_DEAD to the EventBus.
"""

from __future__ import annotations

import logging
import threading
import time

from antigravity.core.base_worker import BaseWorker
from antigravity.core.event_bus import EVT_WORKER_DEAD, bus

logger = logging.getLogger(__name__)


class Watchdog:
    """
    Background daemon that monitors worker health.
    """

    def __init__(self, check_interval: float = 10.0) -> None:
        self._workers: list[BaseWorker] = []
        self._interval = check_interval
        self._stop_event = threading.Event()
        self._thread   = threading.Thread(
            target=self._loop, daemon=True, name="Watchdog"
        )

    def register(self, worker: BaseWorker) -> None:
        """Register a BaseWorker subclass to be monitored."""
        self._workers.append(worker)

    def start(self) -> None:
        """Start the watchdog monitor loop."""
        self._thread.start()
        logger.debug("[WATCHDOG] Started (interval=%.1fs)", self._interval)

    def stop(self) -> None:
        """Signal the watchdog to stop."""
        self._stop_event.set()

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            # Use wait() on stop_event instead of sleep for faster shutdown
            if self._stop_event.wait(timeout=self._interval):
                break
            for w in self._workers:
                if w.is_alive():
                    if not w.is_healthy:
                        logger.warning("[WATCHDOG] '%s' heartbeat stale", w.name)
                        bus.publish(
                            EVT_WORKER_DEAD,
                            {"worker": w.name, "reason": "heartbeat stale"}
                        )
                else:
                    logger.error("[WATCHDOG] '%s' is dead (not alive)", w.name)
                    bus.publish(
                        EVT_WORKER_DEAD,
                        {"worker": w.name, "reason": "thread dead"}
                    )
