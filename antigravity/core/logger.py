"""
core/logger.py - Thread-safe structured logger for all modules.

Writes to:
  logs/interview_log.txt  - conversation and status history
  logs/crash_debug.log    - exception traces and crash events

Usage:
    from core.logger import get_logger
    log = get_logger(__name__)
    log.info("Model loaded")
    log.error("API call failed", exc_info=True)
"""

from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path
from typing import Optional

_setup_lock   = threading.Lock()
_root_logger: Optional[logging.Logger] = None


def _setup_logging(base_dir: Path, log_file: str, crash_file: str) -> logging.Logger:
    """Configure root logger with file and console handlers (call once)."""
    root = logging.getLogger("interview_assistant")
    root.setLevel(logging.DEBUG)

    if root.handlers:          # Already configured
        return root

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)-30s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ── Main interview log (INFO+) ────────────────────────────────────────────
    log_path = base_dir / log_file
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(str(log_path), encoding="utf-8", errors="replace")
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # ── Crash / debug log (DEBUG+) ────────────────────────────────────────────
    crash_path = base_dir / crash_file
    crash_path.parent.mkdir(parents=True, exist_ok=True)
    ch = logging.FileHandler(str(crash_path), encoding="utf-8", errors="replace")
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    # ── Console (INFO+) ───────────────────────────────────────────────────────
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    sh.setFormatter(logging.Formatter("%(levelname)-7s | %(name)-25s | %(message)s"))
    root.addHandler(sh)

    return root


def init_logging(base_dir: Optional[Path] = None,
                 log_file: str = "logs/interview_log.txt",
                 crash_file: str = "logs/crash_debug.log") -> None:
    """
    Must be called once at startup (from main.py) before any get_logger() calls.
    Safe to call multiple times – subsequent calls are no-ops.
    """
    global _root_logger
    with _setup_lock:
        if _root_logger is not None:
            return
        if base_dir is None:
            base_dir = Path(__file__).resolve().parent.parent
        _root_logger = _setup_logging(base_dir, log_file, crash_file)


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the interview_assistant namespace."""
    with _setup_lock:
        if _root_logger is None:
            # Auto-init with defaults if not explicitly initialised
            base_dir = Path(__file__).resolve().parent.parent
            init_logging(base_dir)
    return logging.getLogger(f"interview_assistant.{name}")


def log_crash(header: str, text: str, base_dir: Optional[Path] = None) -> None:
    """Write a raw crash entry to crash_debug.log (bypasses logging framework)."""
    import time
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent.parent
    crash_path = base_dir / "logs" / "crash_debug.log"
    crash_path.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    entry = f"\n[{stamp}] {header}\n{text}\n{'='*60}\n"
    try:
        with crash_path.open("a", encoding="utf-8", errors="replace") as f:
            f.write(entry)
    except Exception:
        pass
    print(entry, file=sys.stderr)
