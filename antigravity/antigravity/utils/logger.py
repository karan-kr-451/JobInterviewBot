"""
utils/logger.py — Structured logging to file + console.

Automatically creates logs/ directory and rotates logs daily via renaming
at startup (keeps previous run).
"""

from __future__ import annotations

import datetime
import logging
import os
import sys

_INITIALIZED = False


def init_logging(base_dir: str, level: str = "INFO") -> None:
    """Initialize root logger with file + console handlers."""
    global _INITIALIZED
    if _INITIALIZED:
        return

    os.makedirs(os.path.join(base_dir, "logs"), exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d")
    log_file = os.path.join(base_dir, "logs", f"interview_{ts}.log")

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()

    # Format: [2024-01-01 12:00:00] [INFO] [module.name] Message
    fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    # File (append)
    try:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except Exception as e:
        print(f"Failed to create file logger: {e}", file=sys.stderr)

    # Suppress noisy external logs
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("faster_whisper").setLevel(logging.WARNING)

    _INITIALIZED = True
