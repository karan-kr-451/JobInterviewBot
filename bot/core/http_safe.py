"""
core.http_safe - Thread-safe HTTP operations with GC protection.

WHY: Python's garbage collector causes access violations when it runs
during HTTP response streaming in C-level buffers (requests/urllib3).

FIX: GC is now disabled PERMANENTLY at startup by crash_prevention.py.
These wrappers are kept for backward compatibility but are now no-ops.
"""

from contextlib import contextmanager
from typing import Callable, Any


@contextmanager
def gc_safe_http():
    """
    Context manager for HTTP operations.
    
    Previously disabled/re-enabled GC around HTTP calls, but this caused
    race conditions in multi-threaded code (gc.disable is process-global,
    not thread-local). GC is now permanently disabled at startup.
    
    Kept for backward compatibility - callers don't need to change.
    """
    yield


def safe_http_call(func: Callable, *args, **kwargs) -> Any:
    """
    Execute an HTTP function. Previously wrapped with GC protection,
    now a passthrough since GC is permanently disabled at startup.
    """
    return func(*args, **kwargs)
