"""
core/gc_guard.py — GC crash prevention (Rule 1 of the zero-crash contract).

MUST be the FIRST module imported in main_gui.py, BEFORE any C-extension import.

Root cause:
  Python's cyclic GC triggers inside C-extension finalizers (tqdm, torch, pyaudio)
  causing SIGSEGV / ACCESS_VIOLATION. Disabling auto-collection entirely prevents
  this class of crash. We run manual gen-0/gen-1 collection from a dedicated safe
  thread — never from audio, torch, or Qt callbacks.
"""

from __future__ import annotations

import gc
import threading
import time
import logging

logger = logging.getLogger(__name__)

_gc_thread: threading.Thread | None = None
_gc_stop   = threading.Event()


def apply_gc_guard() -> None:
    """
    Disable Python's automatic garbage collector.

    Call as FIRST action in main_gui.py, before any import of torch,
    sounddevice, tqdm, or PyQt6.

    Gen-0 and Gen-1 are still collected manually from GCSafeThread.
    Gen-2 (which triggers C-extension finalizers) is NEVER triggered.
    """
    gc.disable()
    gc.set_threshold(0, 0, 0)
    logger.debug("[GC_GUARD] Automatic GC disabled")


def start_safe_gc_thread(interval_seconds: float = 60.0) -> threading.Thread:
    """
    Start a background thread that periodically runs gen-0 and gen-1 GC.
    SAFE: This thread never runs during audio callbacks or torch inference.
    """
    global _gc_thread

    def _run():
        while not _gc_stop.wait(timeout=interval_seconds):
            try:
                gc.collect(0)   # gen-0: short-lived objects (fast, safe)
                gc.collect(1)   # gen-1: medium-lived objects (safe)
                # NEVER gc.collect(2) — triggers C-extension finalizers → CRASH
            except Exception as e:
                logger.error("[GC_GUARD] collect error: %s", e)

    _gc_thread = threading.Thread(
        target=_run, daemon=True, name="GCSafeThread"
    )
    _gc_thread.start()
    logger.debug("[GC_GUARD] GCSafeThread started (interval=%.0fs)", interval_seconds)
    return _gc_thread


def stop_safe_gc_thread() -> None:
    _gc_stop.set()
