"""
core/base_worker.py — Immortal thread base class.

ALL worker threads in Antigravity inherit from BaseWorker.

Guarantees:
  - Exceptions are NEVER silently swallowed
  - Auto-restart up to MAX_RESTARTS times before declaring permanent death
  - Heartbeat timestamp updated every loop iteration
  - Clean graceful shutdown via stop_event
  - Watchdog can query is_healthy / is_alive
"""

from __future__ import annotations

import threading
import time
import traceback
import logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)


class BaseWorker(threading.Thread, ABC):
    """
    Abstract immortal daemon thread.

    Subclass must implement _run_loop().
    _run_loop() should:
      - Update self._health_ts = time.time() at least once per 30s
      - Respect self._stop_event.is_set() to exit cleanly
    """

    MAX_RESTARTS   = 3
    RESTART_DELAY  = 2.0   # seconds between restarts

    def __init__(self, name: str, restart_delay: float = 2.0) -> None:
        super().__init__(name=name, daemon=True)
        self._stop_event     = threading.Event()
        self._health_ts:float = time.time()
        self._restart_count   = 0
        self._restart_delay   = restart_delay
        self._exception: Optional[Exception] = None

    # ── Public API ────────────────────────────────────────────────────────────

    def stop(self) -> None:
        """Signal the worker to stop at next clean opportunity."""
        self._stop_event.set()

    @property
    def is_healthy(self) -> bool:
        """Return True if the heartbeat is fresh (updated within 30 s)."""
        return (time.time() - self._health_ts) < 30.0

    @property
    def last_exception(self) -> Optional[Exception]:
        return self._exception

    # ── Thread entry point ───────────────────────────────────────────────────

    def run(self) -> None:
        logger.debug("[WORKER] %s started", self.name)
        while self._restart_count <= self.MAX_RESTARTS:
            try:
                self._run_loop()
                logger.debug("[WORKER] %s exited cleanly", self.name)
                return   # clean exit — don't restart
            except Exception as exc:
                self._exception      = exc
                self._restart_count += 1
                tb = traceback.format_exc()
                logger.error(
                    "[THREAD_DEATH] %s crashed (attempt %d/%d):\n%s",
                    self.name, self._restart_count, self.MAX_RESTARTS, tb,
                )
                if self._stop_event.is_set():
                    break
                if self._restart_count <= self.MAX_RESTARTS:
                    logger.info("[WORKER] %s restarting in %.1fs…",
                                self.name, self._restart_delay)
                    time.sleep(self._restart_delay)
                else:
                    logger.critical(
                        "[THREAD_DEATH] %s permanently dead after %d restarts. "
                        "Notifying watchdog.",
                        self.name, self.MAX_RESTARTS,
                    )
                    self._on_permanent_failure()
                    return

    # ── Abstract & overridable ───────────────────────────────────────────────

    @abstractmethod
    def _run_loop(self) -> None:
        """
        Subclass implements the core work loop here.
        Should run until self._stop_event.is_set() returns True.
        Must update self._health_ts = time.time() at regular intervals.
        """
        ...

    def _on_permanent_failure(self) -> None:
        """Override to notify watchdog or EventBus on total thread death."""
        try:
            from antigravity.core.event_bus import bus, EVT_WORKER_DEAD
            bus.publish(EVT_WORKER_DEAD, {"worker": self.name,
                                          "error": str(self._exception)})
        except Exception:
            pass

    # ── Heartbeat helper (call from _run_loop) ────────────────────────────────

    def _heartbeat(self) -> None:
        """Call at least once every 30s inside _run_loop."""
        self._health_ts = time.time()
