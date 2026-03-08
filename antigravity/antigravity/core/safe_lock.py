"""
core/safe_lock.py — Deadlock-safe lock with mandatory timeout.

Drop-in replacement for threading.Lock. Every acquire() has a timeout
and logs a warning if it expires — protecting against deadlocks.

Lock Hierarchy (strict ordering, never violate):
  Level 1 (lowest): AudioBuffer._lock
  Level 2:          TranscriptionWorker._lock
  Level 3:          LLMWorker._lock
  Level 4 (highest): AppState._lock

A thread holding lock level N must NEVER acquire lock level >= N.
"""

from __future__ import annotations

import threading
import logging

logger = logging.getLogger(__name__)


class SafeLock:
    """
    threading.Lock wrapper with mandatory timeout.

    Usage:
        lock = SafeLock("AppState", timeout=3.0)
        with lock:
            ...
        # or:
        if lock.acquire():
            try: ...
            finally: lock.release()
    """

    def __init__(self, name: str, timeout: float = 5.0) -> None:
        self._lock   = threading.Lock()
        self.name    = name
        self.timeout = timeout

    def acquire(self, timeout: float | None = None) -> bool:
        t = timeout if timeout is not None else self.timeout
        acquired = self._lock.acquire(timeout=t)
        if not acquired:
            logger.warning(
                "[DEADLOCK_GUARD] Lock '%s' timed out after %.1fs",
                self.name, t,
            )
        return acquired

    def release(self) -> None:
        try:
            self._lock.release()
        except RuntimeError:
            logger.error(
                "[DEADLOCK_GUARD] Double-release on lock '%s'", self.name
            )

    def __enter__(self) -> "SafeLock":
        self.acquire()
        return self

    def __exit__(self, *args) -> None:
        self.release()

    def locked(self) -> bool:
        return self._lock.locked()


class SafeRLock:
    """Reentrant version of SafeLock (for code that nests same lock)."""

    def __init__(self, name: str, timeout: float = 5.0) -> None:
        self._lock   = threading.RLock()
        self.name    = name
        self.timeout = timeout

    def acquire(self, timeout: float | None = None) -> bool:
        t = timeout if timeout is not None else self.timeout
        acquired = self._lock.acquire(timeout=t)
        if not acquired:
            logger.warning(
                "[DEADLOCK_GUARD] RLock '%s' timed out after %.1fs",
                self.name, t,
            )
        return acquired

    def release(self) -> None:
        try:
            self._lock.release()
        except RuntimeError:
            logger.error(
                "[DEADLOCK_GUARD] Double-release on RLock '%s'", self.name
            )

    def __enter__(self) -> "SafeRLock":
        self.acquire()
        return self

    def __exit__(self, *args) -> None:
        self.release()
