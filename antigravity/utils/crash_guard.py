"""
utils/crash_guard.py - GC-safe HTTP context manager and safe_execution wrapper.

ROOT CAUSE of crashes in Python audio apps:
  tqdm / huggingface_hub monitor threads hold weak references that can
  trigger Python's garbage collector during C-extension calls (urllib3,
  PortAudio callbacks).  The _gc_disabled context manager disables the
  cyclic GC for the duration of HTTP response streaming, eliminating
  the access-violation crash vector.

Usage:
    from utils.crash_guard import gc_safe_http, safe_execution

    with gc_safe_http():
        resp = session.post(url, stream=True)
        for line in resp.iter_lines(): ...

    with safe_execution("API call"):
        result = some_api()
"""

from __future__ import annotations

import contextlib
import gc
import threading
import time
import traceback
from typing import Any, Optional

# ── Global HTTP lock: ensures only one GC-protected HTTP call at a time ────────
# This prevents multiple threads from racing to disable/enable GC simultaneously.
_http_lock: threading.Lock = threading.Lock()


@contextlib.contextmanager
def gc_safe_http():
    """
    Context manager that disables Python's cyclic GC while holding
    _http_lock to protect C-level HTTP streaming.

    Acquires the lock, disables GC, yields, then re-enables GC and releases.
    """
    with _http_lock:
        was_enabled = gc.isenabled()
        if was_enabled:
            gc.disable()
        try:
            yield
        finally:
            if was_enabled:
                gc.enable()


@contextlib.contextmanager
def smart_gc_protection():
    """
    Lighter version: tries to acquire the lock with a timeout.
    Falls back to running without GC protection if lock is contested.
    This prevents Telegram from blocking audio HTTP calls.
    """
    acquired = _http_lock.acquire(blocking=True, timeout=3.0)
    was_enabled = gc.isenabled()
    if acquired and was_enabled:
        gc.disable()
    try:
        yield
    finally:
        if acquired:
            if was_enabled:
                gc.enable()
            _http_lock.release()


@contextlib.contextmanager
def safe_execution(label: str = "", fallback_value: Any = None):
    """
    Context manager that catches all exceptions, logs them, and swallows them.
    Use this for non-critical sections where failure should not crash the app.

    Example:
        with safe_execution("Telegram send"):
            notifier.send_message("Started")
    """
    try:
        yield
    except Exception as exc:
        tb = traceback.format_exc()
        tag = f"[{label}] " if label else ""
        print(f"{tag}Non-fatal exception: {type(exc).__name__}: {exc}")
        try:
            from core.logger import log_crash
            log_crash(f"{label} – non-fatal exception", tb)
        except Exception:
            print(tb)


def create_fresh_session(extra_headers: dict | None = None):
    """
    Create a new requests.Session with safety defaults.
    Using fresh sessions avoids connection-pool thread-safety issues.
    """
    import requests
    s = requests.Session()
    s.trust_env = False   # Disable .netrc / system proxy env lookup (not thread-safe)
    if extra_headers:
        s.headers.update(extra_headers)
    return s


def close_response_safely(resp) -> None:
    """Close a requests.Response without raising."""
    if resp is None:
        return
    try:
        resp.close()
    except Exception:
        pass


def disable_tqdm_monitor() -> None:
    """
    Disable tqdm's background GC monitor thread.
    Call once at startup before any imports that use tqdm.

    ROOT CAUSE: tqdm's TMonitor holds weak refs that trigger GC during
    C-extension calls → access violation.
    """
    try:
        import tqdm
        import tqdm.std
        tqdm.tqdm.monitor_interval = 0
        tqdm.std.TRLock = None
        try:
            import tqdm._monitor as _tmon
            inst = getattr(_tmon.TMonitor, "_instance", None)
            if inst is not None:
                if hasattr(inst, "exit_event"):
                    inst.exit_event.set()
                try:
                    inst.join(timeout=0.5)
                except Exception:
                    pass
                _tmon.TMonitor._instance = None
            # Monkey-patch to prevent re-creation
            _tmon.TMonitor.__init__ = lambda self, *a, **kw: None
        except Exception:
            pass
    except Exception:
        pass
