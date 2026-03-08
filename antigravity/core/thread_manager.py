"""
core/thread_manager.py - Registry and lifecycle manager for all daemon threads.

Replaces scattered threading.Thread calls. Provides:
  • start_thread()   - register + start a SafeThread
  • stop_all()       - signal all threads to stop (graceful shutdown)
  • health_check()   - returns list of dead threads with their names
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Dict, List, Optional


class ThreadRegistry:
    """
    Manages the lifecycle of all application worker threads.
    Thread-safe. Call start_thread() to register and start each worker.
    """

    def __init__(self) -> None:
        self._lock:    threading.Lock             = threading.Lock()
        self._threads: Dict[str, threading.Thread] = {}
        self._stop_event = threading.Event()

    @property
    def stop_event(self) -> threading.Event:
        """Shared stop event – set this to signal all threads to exit."""
        return self._stop_event

    def start_thread(
        self,
        name: str,
        target: Callable,
        args: tuple = (),
        kwargs: dict | None = None,
        daemon: bool = True,
        restart_on_crash: bool = False,
    ) -> threading.Thread:
        """
        Wrap target in a SafeThread, register it, and start it.

        Args:
            name:             Human-readable thread name (used in logs).
            target:           Callable to run.
            args:             Positional args for target.
            kwargs:           Keyword args for target.
            daemon:           Whether thread should be a daemon.
            restart_on_crash: If True, the thread will be restarted on exception.
        """
        from utils.safe_thread import SafeThread

        t = SafeThread(
            name=name,
            target=target,
            args=args,
            kwargs=kwargs or {},
            daemon=daemon,
            stop_event=self._stop_event,
            restart_on_crash=restart_on_crash,
        )
        with self._lock:
            self._threads[name] = t
        t.start()
        return t

    def stop_all(self, wait_secs: float = 3.0) -> None:
        """Signal all threads to stop and wait up to wait_secs for each."""
        self._stop_event.set()
        with self._lock:
            threads = list(self._threads.values())
        for t in threads:
            try:
                t.join(timeout=wait_secs)
            except Exception:
                pass

    def health_check(self) -> List[str]:
        """Return names of threads that should be alive but are not."""
        dead = []
        with self._lock:
            for name, t in self._threads.items():
                if not t.is_alive():
                    dead.append(name)
        return dead

    def list_threads(self) -> Dict[str, bool]:
        """Return {name: is_alive} for all registered threads."""
        with self._lock:
            return {name: t.is_alive() for name, t in self._threads.items()}


# ── Module-level singleton ────────────────────────────────────────────────────
_registry: Optional[ThreadRegistry] = None
_reg_lock  = threading.Lock()


def get_registry() -> ThreadRegistry:
    """Return the process-level singleton ThreadRegistry."""
    global _registry
    if _registry is None:
        with _reg_lock:
            if _registry is None:
                _registry = ThreadRegistry()
    return _registry
