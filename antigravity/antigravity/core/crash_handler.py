"""
core/crash_handler.py — Global exception handlers + crash log writer.

install() MUST be called as the second step in main_gui.py
(immediately after apply_gc_guard()).

Handles:
  - Uncaught exceptions in the main thread (sys.excepthook)
  - Uncaught exceptions in any daemon thread (threading.excepthook)
  - Writes timestamped crash log to logs/crash_<thread>_<ts>.log
"""

from __future__ import annotations

import datetime
import logging
import os
import sys
import threading
import traceback

logger = logging.getLogger(__name__)


def _format_crash(exc_type, exc_value, exc_tb) -> str:
    return "".join(traceback.format_exception(exc_type, exc_value, exc_tb))


def _write_crash_log(text: str, thread: str = "main") -> None:
    os.makedirs("logs", exist_ok=True)
    ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"logs/crash_{thread}_{ts}.log"
    try:
        with open(path, "w", encoding="utf-8", errors="replace") as f:
            f.write(text)
        logger.info("[CRASH] Written to %s", path)
    except Exception as e:
        print(f"[CRASH] Could not write crash log: {e}", file=sys.stderr)
    print(text, file=sys.stderr)


def global_exception_handler(exc_type, exc_value, exc_tb) -> None:
    """Handles uncaught exceptions in the MAIN thread."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    crash_text = _format_crash(exc_type, exc_value, exc_tb)
    logger.critical("[CRASH] Uncaught exception:\n%s", crash_text)
    _write_crash_log(crash_text, thread="main")


def thread_exception_handler(args) -> None:
    """Handles uncaught exceptions in WORKER threads."""
    name       = getattr(args.thread, "name", "unknown")
    crash_text = _format_crash(args.exc_type, args.exc_value, args.exc_traceback)
    logger.critical("[CRASH] Thread '%s' uncaught:\n%s", name, crash_text)
    _write_crash_log(crash_text, thread=name)


def install() -> None:
    """Install both exception hooks. Call SECOND in main_gui.py."""
    sys.excepthook      = global_exception_handler
    threading.excepthook = thread_exception_handler
    logger.info("[CRASH_GUARD] Exception handlers installed")
