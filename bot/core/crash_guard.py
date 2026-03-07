"""
core.crash_guard - Crash protection setup.

Installs faulthandler, sys.excepthook, and threading.excepthook to ensure
crashes are logged and the process doesn't silently die.
"""

import os
import sys
import ctypes
import faulthandler
import threading
import time


def install_crash_guard():
    """Install all crash protection layers."""
    # -- faulthandler ------------------------------------------------------
    try:
        _fh = open("crash.log", "a", encoding="utf-8")
        faulthandler.enable(file=_fh, all_threads=True)
        print("[OK] faulthandler -> crash.log")
    except Exception as e:
        try:
            faulthandler.enable(all_threads=True)
            print(f"   faulthandler (stderr only): {e}")
        except Exception:
            pass

    # -- sys.excepthook ----------------------------------------------------
    _original_excepthook = sys.excepthook

    def _excepthook(exc_type, exc_value, exc_tb):
        import traceback
        msg = (
            f"\n{'!'*60}\n"
            f"UNHANDLED {exc_type.__name__}: {exc_value}\n"
            f"{''.join(traceback.format_tb(exc_tb))}"
            f"{'!'*60}\n"
        )
        print(msg)
        try:
            with open("crash.log", "a", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}]\n{msg}\n")
        except Exception:
            pass
        _original_excepthook(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook

    # -- threading.excepthook ----------------------------------------------
    def _thread_excepthook(args):
        import traceback
        msg = (
            f"\n{'!'*60}\n"
            f"Thread '{args.thread.name if args.thread else '?'}' crashed:\n"
            f"{args.exc_type.__name__}: {args.exc_value}\n"
            f"{''.join(traceback.format_tb(args.exc_traceback))}"
            f"{'!'*60}\n"
        )
        print(msg)
        try:
            with open("crash.log", "a", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}]\n{msg}\n")
        except Exception:
            pass

    threading.excepthook = _thread_excepthook


def install_traced_exit():
    """Replace os._exit with a traced version that writes a stack trace before exiting."""
    _original_exit = os._exit

    def _traced_exit(code):
        import traceback
        msg = (
            f"\n{'!'*60}\n"
            f"os._exit({code}) called at {time.strftime('%H:%M:%S')}\n"
            f"{''.join(traceback.format_stack())}"
            f"{'!'*60}\n"
        )
        print(msg)
        try:
            with open("crash.log", "a", encoding="utf-8") as f:
                f.write(msg)
        except Exception:
            pass
        _original_exit(code)

    os._exit = _traced_exit
