"""
utils/safe_thread.py - Thread wrapper with exception guard and optional restart.

SafeThread extends threading.Thread to:
  1. Catch and log ALL exceptions from the target function.
  2. Write crash info to crash_debug.log.
  3. Optionally restart the thread (up to MAX_RESTARTS times).
  4. Respect a shared stop_event for graceful shutdown.

Usage:
    from utils.safe_thread import SafeThread
    t = SafeThread(name="my-worker", target=my_fn, daemon=True)
    t.start()
"""

from __future__ import annotations

import threading
import time
import traceback
from typing import Callable, Optional


MAX_RESTARTS    = 5
RESTART_DELAY_S = 2.0


class SafeThread(threading.Thread):
    """
    A daemon thread that catches exceptions, logs them, and optionally restarts.
    """

    def __init__(
        self,
        name: str,
        target: Callable,
        args: tuple = (),
        kwargs: dict | None = None,
        daemon: bool = True,
        stop_event: Optional[threading.Event] = None,
        restart_on_crash: bool = False,
    ) -> None:
        super().__init__(name=name, daemon=daemon)
        self._target           = target
        self._args             = args
        self._kwargs           = kwargs or {}
        self._stop_event       = stop_event or threading.Event()
        self._restart_on_crash = restart_on_crash
        self._restart_count    = 0

    def run(self) -> None:
        """Thread entry point with exception guard and restart logic."""
        while True:
            try:
                self._target(*self._args, **self._kwargs)
                # Target returned normally
                break
            except Exception as exc:
                tb = traceback.format_exc()
                self._log_crash(exc, tb)

                if (
                    self._restart_on_crash
                    and self._restart_count < MAX_RESTARTS
                    and not self._stop_event.is_set()
                ):
                    self._restart_count += 1
                    print(
                        f"[SafeThread] '{self.name}' restarting "
                        f"({self._restart_count}/{MAX_RESTARTS}) in {RESTART_DELAY_S}s…"
                    )
                    time.sleep(RESTART_DELAY_S)
                    continue
                else:
                    if self._restart_on_crash:
                        print(
                            f"[SafeThread] '{self.name}' exhausted restarts – giving up."
                        )
                    break

    def _log_crash(self, exc: Exception, tb: str) -> None:
        """Write crash info to logger and crash_debug.log."""
        msg = (
            f"[SafeThread] Unhandled exception in thread '{self.name}': "
            f"{type(exc).__name__}: {exc}"
        )
        print(msg)
        try:
            from core.logger import get_logger, log_crash
            get_logger("safe_thread").error(
                "Thread '%s' crashed: %s", self.name, exc, exc_info=False
            )
            log_crash(
                f"Thread '{self.name}' crashed: {type(exc).__name__}",
                tb,
            )
        except Exception:
            print(tb)
