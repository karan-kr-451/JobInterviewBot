"""
crash_detector.py - External supervisor that auto-restarts the main process.

This is the outermost safety net. It runs as a separate process that
launches main.py and watches for crash exits. On crash, it waits a
configurable delay and restarts.

Usage:
    python crash_detector.py [--delay 5] [--max-restarts 20]

Or build it as the outer EXE wrapper in PyInstaller.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_MAIN = _HERE / "main.py"

DEFAULT_RESTART_DELAY  = 5    # seconds between restarts
DEFAULT_MAX_RESTARTS   = 20   # times before giving up


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Interview Assistant crash supervisor")
    p.add_argument("--delay",        type=float, default=DEFAULT_RESTART_DELAY,
                   help="Seconds to wait before restarting after a crash")
    p.add_argument("--max-restarts", type=int,   default=DEFAULT_MAX_RESTARTS,
                   help="Maximum number of restart attempts")
    return p.parse_args()


def _is_crash(returncode: int) -> bool:
    """Return True if the exit code indicates an unexpected crash."""
    return returncode not in (0, -2, -15)   # 0=clean, -2=Ctrl-C, -15=SIGTERM


def run_supervised(delay: float, max_restarts: int) -> None:
    print(f"[Supervisor] Launching: {_MAIN}")
    restarts = 0

    while restarts <= max_restarts:
        start = time.time()
        print(f"[Supervisor] Start #{restarts + 1} at {time.strftime('%H:%M:%S')}")

        try:
            result = subprocess.run(
                [sys.executable, str(_MAIN)],
                cwd=str(_HERE),
            )
            rc = result.returncode
        except FileNotFoundError:
            print(f"[Supervisor] ERROR: Python not found at {sys.executable}")
            return
        except KeyboardInterrupt:
            print("\n[Supervisor] Ctrl+C – shutting down")
            return

        elapsed = time.time() - start

        if rc == 0:
            print("[Supervisor] Clean exit – not restarting.")
            return

        if not _is_crash(rc):
            print(f"[Supervisor] Exited with code {rc} – not restarting.")
            return

        restarts += 1
        print(
            f"[Supervisor] Crash detected (exit code {rc}, "
            f"uptime {elapsed:.0f}s) – restart {restarts}/{max_restarts}"
        )

        if restarts > max_restarts:
            print(f"[Supervisor] Too many restarts – giving up.")
            break

        # Very short uptime likely means a startup error – wait longer
        wait = delay if elapsed > 10 else delay * 3
        print(f"[Supervisor] Waiting {wait:.0f}s before restart…")
        time.sleep(wait)

    print("[Supervisor] All restart attempts exhausted.")


if __name__ == "__main__":
    args = _parse_args()
    run_supervised(args.delay, args.max_restarts)
