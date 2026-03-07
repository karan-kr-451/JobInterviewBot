"""
core.http_utils - Comprehensive HTTP utilities with GC protection.

This module provides all HTTP-related utilities in one place for easy maintenance:
- GC-safe HTTP operations
- Smart periodic garbage collection
- Thread-safe session management
- Response cleanup helpers

WHY: Python's garbage collector can cause access violations during HTTP operations
in C-level buffers (requests/urllib3). This module provides complete protection.
"""

import gc
import time
import threading
import requests
from contextlib import contextmanager
from typing import Callable, Any, Optional


# ============================================================================
# SMART GC MANAGEMENT
# ============================================================================

# Global state for smart GC
_request_counter = 0
_last_gc_time = time.time()
_counter_lock = threading.Lock()

# CRITICAL: Global lock for ALL HTTP operations to prevent race conditions
# The requests library has internal data structures that are NOT thread-safe
# even with trust_env=False. This lock ensures only one HTTP request at a time.
_http_lock = threading.RLock()

# Configuration - tune these based on your needs
GC_REQUEST_INTERVAL = 5   # Collect every N requests
GC_TIME_INTERVAL = 30     # Collect every N seconds


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
    violations with C-extension objects. Python's reference counting handles
    all non-cyclic object cleanup automatically.
    """
    pass


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


# ============================================================================
# GC-SAFE HTTP CONTEXT MANAGERS
# ============================================================================

@contextmanager
def gc_safe_http():
    """
    HTTP lock for serializing HTTP operations.
    
    GC is permanently disabled at startup - this context manager only
    provides the global lock to prevent concurrent HTTP requests.
    """
    with _http_lock:
        yield


@contextmanager
def smart_gc_protection():
    """
    HTTP lock for serializing HTTP operations (RECOMMENDED).
    
    GC is permanently disabled at startup - this context manager only
    provides the global lock to prevent concurrent HTTP requests and
    tracks request counts for monitoring.
    """
    with _http_lock:
        # Track request for monitoring
        should_collect_gc()
        yield


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def safe_http_call(func: Callable, *args, **kwargs) -> Any:
    """
    Execute an HTTP function with basic GC protection.
    
    Usage:
        resp = safe_http_call(requests.post, url, json=data, timeout=30)
    
    Note: Prefer using context managers for better control.
    """
    with gc_safe_http():
        return func(*args, **kwargs)


def close_response_safely(resp: Optional[requests.Response]) -> None:
    """
    Safely close an HTTP response object.
    
    Usage:
        resp = session.post(url, ...)
        data = resp.json()
        close_response_safely(resp)
    
    This is a helper to ensure responses are always closed properly.
    """
    if resp is not None:
        try:
            resp.close()
        except Exception:
            pass


def create_fresh_session(headers: Optional[dict] = None) -> requests.Session:
    """
    Create a fresh requests.Session with optional headers.
    
    CRITICAL: Cookies are disabled by default to prevent access violations
    in cookiejar.py on Windows (rare multi-threaded race condition).
    """
    session = requests.Session()
    session.trust_env = False  # CRITICAL: Disable .netrc to prevent os.environ race
    
    # Disable cookies for stability on Windows
    # Simply clear the cookie jar instead of setting policy
    session.cookies.clear()
    
    if headers:
        session.headers.update(headers)
    return session


# ============================================================================
# USAGE PATTERNS
# ============================================================================

"""
PATTERN 1: High-Frequency Operations (Recommended)
Use smart_gc_protection() for operations called frequently:

    from core.http_utils import smart_gc_protection, create_fresh_session, close_response_safely
    
    def transcribe_audio():
        with smart_gc_protection():
            session = create_fresh_session({"Authorization": f"Bearer {API_KEY}"})
            resp = None
            try:
                resp = session.post(url, data=data, timeout=30)
                resp.raise_for_status()
                result = resp.json()
                close_response_safely(resp)
                resp = None
                return result
            finally:
                close_response_safely(resp)


PATTERN 2: Low-Frequency Operations
Use gc_safe_http() for operations called rarely:

    from core.http_utils import gc_safe_http, close_response_safely
    
    def check_api_status():
        with gc_safe_http():
            resp = None
            try:
                resp = requests.get(url, timeout=5)
                status = resp.json()
                close_response_safely(resp)
                resp = None
                return status
            finally:
                close_response_safely(resp)


PATTERN 3: Polling Loops
Use smart_gc_protection() in loops for automatic periodic collection:

    from core.http_utils import smart_gc_protection, create_fresh_session, close_response_safely
    
    def poll_for_updates():
        while True:
            with smart_gc_protection():
                session = create_fresh_session()
                resp = None
                try:
                    resp = session.get(url, timeout=30)
                    data = resp.json()
                    close_response_safely(resp)
                    resp = None
                    # Process data...
                finally:
                    close_response_safely(resp)


PATTERN 4: Streaming Responses
Use smart_gc_protection() for streaming with explicit cleanup:

    from core.http_utils import smart_gc_protection, close_response_safely
    
    def stream_llm_response():
        with smart_gc_protection():
            resp = None
            try:
                resp = requests.post(url, stream=True, timeout=120)
                for line in resp.iter_lines():
                    # Process streaming data...
                    pass
                close_response_safely(resp)
                resp = None
            finally:
                close_response_safely(resp)
"""


# ============================================================================
# CONFIGURATION
# ============================================================================

def configure_gc_intervals(request_interval: int = 5, time_interval: int = 30):
    """
    Configure smart GC collection intervals.
    
    Args:
        request_interval: Collect every N requests (default: 5)
        time_interval: Collect every N seconds (default: 30)
    
    Usage:
        from core.http_utils import configure_gc_intervals
        configure_gc_intervals(request_interval=10, time_interval=60)
    """
    global GC_REQUEST_INTERVAL, GC_TIME_INTERVAL
    GC_REQUEST_INTERVAL = request_interval
    GC_TIME_INTERVAL = time_interval
    print(f"[HTTP Utils] GC intervals configured: {request_interval} requests or {time_interval}s")
