"""
core.smart_gc - Smart garbage collection management for HTTP operations.

Provides periodic GC collection between HTTP requests to prevent memory buildup
while still protecting HTTP operations from GC-related crashes.
"""

import gc
import time
import threading
from contextlib import contextmanager

# Global state for smart GC
_request_counter = 0
_last_gc_time = time.time()
_counter_lock = threading.Lock()

# Configuration
GC_REQUEST_INTERVAL = 5  # Collect every 5 requests
GC_TIME_INTERVAL = 30    # Collect every 30 seconds


def should_collect_gc() -> bool:
    """
    Determine if GC collection should be triggered.
    Uses hybrid approach: request count OR time elapsed.
    """
    global _request_counter, _last_gc_time
    
    with _counter_lock:
        _request_counter += 1
        request_trigger = (_request_counter % GC_REQUEST_INTERVAL == 0)
    
    now = time.time()
    time_trigger = (now - _last_gc_time > GC_TIME_INTERVAL)
    
    if request_trigger or time_trigger:
        with _counter_lock:
            _last_gc_time = now
        return True
    return False


def smart_gc_collect():
    """
    NO-OP: GC is permanently disabled for the entire session.
    
    Previously performed gc.collect(generation=0), but this caused access
    violations with C-extension objects. Kept for API compatibility.
    """
    pass


@contextmanager
def smart_gc_protection():
    """
    Context manager kept for API compatibility.
    
    GC is permanently disabled at startup - this is now a simple passthrough.
    """
    yield


def get_gc_stats() -> dict:
    """Get current GC statistics for monitoring."""
    return {
        "enabled": gc.isenabled(),
        "request_count": _request_counter,
        "last_collection": time.strftime("%H:%M:%S", time.localtime(_last_gc_time)),
        "object_count": len(gc.get_objects()),
        "thresholds": gc.get_threshold(),
        "counts": gc.get_count(),
    }
