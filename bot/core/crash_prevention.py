"""
crash_prevention.py - Comprehensive crash prevention and recovery system.

This module implements multiple layers of defense against the access violations
and silent crashes that plague multi-threaded Python applications on Windows.

ROOT CAUSES ADDRESSED:
1. tqdm monitor thread GC race
2. numpy.as_strided GC during C-extension calls
3. requests.Session thread-safety violations
4. ctypes callback GC (Win32 thunks freed while still in use)
5. Gemini SDK C-extension os._exit() calls
6. Queue overflow and blocking issues
7. Thread death without cleanup

DEFENSE LAYERS:
- Pre-import all lazy-loaded modules before threading starts
- Disable problematic background threads (tqdm monitor)
- Thread-local storage for non-thread-safe objects (requests.Session)
- GC control around C-extension calls
- Comprehensive exception handling with recovery
- Graceful degradation when components fail
- Proper cleanup on exit
"""

import sys
import gc
import threading
import time
import traceback
import atexit
from typing import Callable, Any

# -- Safe GC Management --------------------------------------------------------
_gc_lock = threading.Lock()
_question_counter = 0

def check_and_gc(force=False, threshold=2):
    """
    Track question count but DO NOT perform GC collection.
    
    CRITICAL: gc.collect() causes access violations even when called "between questions"
    because HTTP connections and C-level objects are still in memory.
    
    Solution: Rely entirely on Python's reference counting for cleanup.
    GC is disabled globally and never re-enabled or triggered.
    
    Usage:
        check_and_gc()  # tracks count but doesn't collect
    """
    global _question_counter
    
    with _gc_lock:
        _question_counter += 1
        if force or _question_counter >= threshold:
            # Just reset the counter, don't collect
            print(f"[crash_prevention] Question count: {_question_counter} (GC collection disabled for safety)")
            _question_counter = 0


# -- Module Pre-loading --------------------------------------------------------

def preload_modules():
    """
    Pre-import modules that use lazy loading or have GC-sensitive initialization.
    
    WHY: Many libraries (urllib3, huggingface_hub, scipy, torch, soundfile) lazy-load
    submodules on first use. If that first use happens inside a C-extension call or
    during GC, it can trigger access violations. Pre-loading ensures all imports happen
    in a safe context before threading starts.
    
    CRITICAL: Heavy C-extension libraries (scipy, torch, soundfile, sounddevice) must
    be imported with GC disabled due to Windows symlink resolution and C-level
    initialization race conditions.
    """
    import gc
    
    # Standard libraries (safe to import normally)
    modules_to_load = [
        # urllib3 and requests (used by Gemini, Groq, Telegram)
        ("urllib3", ["response", "connection", "connectionpool", "poolmanager"]),
        ("urllib3.util", ["retry", "timeout"]),
        ("requests", ["adapters", "sessions"]),
        
        # huggingface_hub (used by faster-whisper)
        ("huggingface_hub", ["_space_api", "_jobs_api", "hf_api", "_snapshot_download"]),
        
        # numpy (used everywhere)
        ("numpy", ["core", "lib"]),
    ]
    
    # Google AI modules (must be pre-imported with GC disabled due to pyasn1)
    # WHY: pyasn1 module initialization triggers GC-sensitive operations
    # that crash when GC runs during Win32 overlay hook initialization
    google_modules = [
        "pyasn1",
        "pyasn1.type.base",
        "pyasn1.type.namedtype",
        "pyasn1_modules.rfc2459",
        "google.auth.crypt._python_rsa",
        "google.auth.crypt.rsa",
        "google.auth.crypt",
        "google.auth._service_account_info",
        "google.oauth2.service_account",
        "google.auth.transport.grpc",
        "google.api_core.grpc_helpers",
        "google.api_core.gapic_v1.method",
        "google.api_core.gapic_v1",
        "google.ai.generativelanguage_v1beta",
    ]
    
    gc_was_enabled_google = gc.isenabled()
    if gc_was_enabled_google:
        gc.disable()
    
    try:
        for module_name in google_modules:
            try:
                __import__(module_name)
            except ImportError:
                # Module not installed - that's OK
                pass
            except Exception:
                # Other errors - continue anyway
                pass
    finally:
        # CRITICAL: Do NOT re-enable GC - it must stay disabled for entire session
        pass
    
    for base_module, submodules in modules_to_load:
        try:
            __import__(base_module)
            for sub in submodules:
                try:
                    __import__(f"{base_module}.{sub}")
                except Exception:
                    pass
        except Exception:
            pass
    
    # CRITICAL: Heavy C-extension libraries must be imported with GC disabled
    # WHY: These libraries trigger Windows symlink resolution and C-level
    # initialization which can crash if GC runs during the process
    
    heavy_modules = [
        ("scipy", ["scipy.signal"]),           # Used in audio/filters.py
        ("torch", []),                          # Used in audio/vad.py (Silero VAD)
        ("soundfile", []),                      # Used in transcription/groq_whisper.py
        ("sounddevice", []),                    # Used in audio/capture.py
        # NOTE: faster_whisper removed - not used (using Groq Whisper API instead)
        # It was causing 60s+ hangs during import due to PyAV issues
    ]
    
    gc_was_enabled = gc.isenabled()
    if gc_was_enabled:
        gc.disable()
    
    try:
        for base_module, submodules in heavy_modules:
            try:
                __import__(base_module)
                for sub in submodules:
                    if sub:
                        try:
                            __import__(sub)
                        except Exception:
                            pass
            except ImportError:
                # Module not installed - that's OK, it might not be needed
                pass
            except Exception as e:
                print(f"  [WARN] {base_module} pre-import failed: {e}")
    
    finally:
        # CRITICAL: Do NOT re-enable GC - it must stay disabled for entire session
        pass


# -- tqdm Monitor Disabler -----------------------------------------------------

def disable_tqdm_monitor():
    """
    Completely disable tqdm's background monitor thread.
    
    ROOT CAUSE: tqdm creates a daemon thread that holds weak references and
    can trigger GC during C-extension calls -> access violation.
    
    FIX: Disable monitor, stop existing instance, monkey-patch to prevent restart.
    """
    try:
        import tqdm
        import tqdm.std
        
        # Disable monitor interval
        tqdm.tqdm.monitor_interval = 0
        tqdm.std.TRLock = None
        
        # Stop existing monitor instance
        try:
            import tqdm._monitor as _tmon
            inst = getattr(_tmon.TMonitor, "_instance", None)
            if inst is not None:
                if hasattr(inst, "exit_event"):
                    inst.exit_event.set()
                if hasattr(inst, "join"):
                    try:
                        inst.join(timeout=0.5)
                    except Exception:
                        pass
                _tmon.TMonitor._instance = None
        except Exception:
            pass
        
        # Monkey-patch to prevent re-creation
        try:
            import tqdm._monitor as _tmon
            _tmon.TMonitor.__init__ = lambda self, *args, **kwargs: None
        except Exception:
            pass
            
        return True
    except Exception as e:
        print(f"[crash_prevention] tqdm disable failed: {e}")
        return False


# -- Thread-Safe Wrapper -------------------------------------------------------

class ThreadSafeWrapper:
    """
    Wraps a non-thread-safe object with thread-local storage.
    
    Each thread gets its own instance, preventing concurrent access.
    Used for requests.Session, file handles, etc.
    """
    
    def __init__(self, factory: Callable[[], Any]):
        self._factory = factory
        self._local = threading.local()
    
    def get(self) -> Any:
        """Get this thread's instance, creating it if needed."""
        if not hasattr(self._local, "instance"):
            self._local.instance = self._factory()
        return self._local.instance
    
    def cleanup(self):
        """Clean up this thread's instance."""
        if hasattr(self._local, "instance"):
            try:
                inst = self._local.instance
                if hasattr(inst, "close"):
                    inst.close()
            except Exception:
                pass
            delattr(self._local, "instance")


# -- GC-Safe Context Manager ---------------------------------------------------

class GCSafeContext:
    """
    Context manager that ensures GC stays disabled.
    
    Usage:
        with GCSafeContext():
            result = c_extension_function(data)
    
    CRITICAL: Since GC is disabled permanently for the entire session,
    this context manager is now a no-op. It exists for API compatibility
    but doesn't actually toggle GC anymore.
    """
    
    def __enter__(self):
        # GC is already disabled permanently - do nothing
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # CRITICAL: Do NOT re-enable GC here!
        # GC must stay disabled for the entire session
        return False  # don't suppress exceptions


# -- Resilient Worker ----------------------------------------------------------

class ResilientWorker:
    """
    Worker thread that automatically recovers from crashes.
    
    Features:
    - Catches ALL exceptions (including SystemExit, KeyboardInterrupt)
    - Logs crashes to file
    - Restarts automatically with exponential backoff
    - Graceful shutdown on stop signal
    
    Usage:
        def work_fn():
            while True:
                item = queue.get()
                process(item)
        
        worker = ResilientWorker(work_fn, name="my-worker")
        worker.start()
        # ... later ...
        worker.stop()
    """
    
    def __init__(self, work_fn: Callable, name: str = "worker",
                 max_restarts: int = 999, crash_log: str = "crash.log"):
        self._work_fn = work_fn
        self._name = name
        self._max_restarts = max_restarts
        self._crash_log = crash_log
        self._stop_event = threading.Event()
        self._thread = None
    
    def start(self):
        """Start the worker thread."""
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name=self._name
        )
        self._thread.start()
    
    def stop(self, timeout: float = 5.0):
        """Stop the worker and wait for it to exit."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout)
    
    def is_alive(self) -> bool:
        """Check if worker thread is running."""
        return self._thread and self._thread.is_alive()
    
    def _run(self):
        """Main worker loop with crash recovery."""
        restarts = 0
        backoff = 1.0
        
        while not self._stop_event.is_set() and restarts < self._max_restarts:
            try:
                self._work_fn()
                # Work function returned normally (shutdown signal)
                break
                
            except KeyboardInterrupt:
                print(f"[{self._name}] KeyboardInterrupt - exiting")
                break
                
            except BaseException as e:
                restarts += 1
                msg = (
                    f"\n{'!'*60}\n"
                    f"[{self._name}] CRASH #{restarts} at {time.strftime('%H:%M:%S')}\n"
                    f"Exception: {type(e).__name__}: {e}\n"
                    f"{traceback.format_exc()}"
                    f"{'!'*60}\n"
                )
                print(msg, file=sys.stderr)
                
                try:
                    with open(self._crash_log, "a", encoding="utf-8") as f:
                        f.write(msg)
                except Exception:
                    pass
                
                if restarts >= self._max_restarts:
                    print(f"[{self._name}] Max restarts reached - giving up")
                    break
                
                # Exponential backoff
                print(f"[{self._name}] Restarting in {backoff:.1f}s...")
                time.sleep(backoff)
                backoff = min(backoff * 1.5, 30.0)


# -- Safe Queue Operations -----------------------------------------------------

def safe_queue_put(q, item, timeout: float = 5.0, drop_on_full: bool = True) -> bool:
    """
    Put item in queue with timeout and optional drop-on-full.
    
    Returns True if item was queued, False if dropped.
    Prevents infinite blocking when queues fill up.
    """
    try:
        q.put(item, block=True, timeout=timeout)
        return True
    except Exception:
        if drop_on_full:
            return False
        raise


def safe_queue_get(q, timeout: float = 2.0, default=None):
    """
    Get item from queue with timeout and default value.
    
    Returns item or default if queue is empty.
    Prevents infinite blocking on empty queues.
    """
    try:
        return q.get(timeout=timeout)
    except Exception:
        return default


# -- Initialization ------------------------------------------------------------

def initialize_crash_prevention():
    """
    Initialize all crash prevention measures.
    
    Call this ONCE at the start of main(), before any threading starts.
    
    CRITICAL: GC is disabled permanently after this function returns.
    
    WHY: gc.disable()/gc.enable() is PROCESS-GLOBAL, not thread-local.
    In a multi-threaded app with 5+ threads doing HTTP calls and C-extension
    work simultaneously, whenever ANY thread re-enables GC in its finally
    block, it re-enables GC for ALL threads - including ones mid-C-extension
    call. This causes access violations when GC frees objects that C code
    still holds pointers to.
    
    The only reliable fix is to disable GC once and leave it disabled.
    Python uses reference counting as its primary memory management; GC only
    handles reference cycles. For short-lived applications like this, cyclic
    garbage is negligible.
    """
    print("[crash_prevention] Initializing...")
    
    # Pre-load modules (GC is temporarily toggled inside preload_modules)
    preload_modules()
    print("  [OK] Modules pre-loaded")
    
    # Disable tqdm monitor
    if disable_tqdm_monitor():
        print("  [OK] tqdm monitor disabled")
    
    # -- PERMANENT GC DISABLE ----------------------------------------------
    # This is the core crash fix. GC stays disabled for the entire process
    # lifetime. Reference counting still frees non-cyclic objects normally.
    gc.disable()
    gc.collect()  # One final collection while it's still safe
    print("  [OK] GC disabled permanently (reference counting still active)")
    
    # Set up atexit cleanup - use os._exit() to prevent GC during finalization
    # WHY: Python's interpreter shutdown re-enables GC to collect cyclic garbage,
    # but at that point C-extension objects (PortAudio, Win32 overlay, urllib3)
    # are partially torn down. GC walks into freed memory -> access violation.
    # os._exit(0) bypasses finalization entirely, which is safe for this app.
    def _cleanup():
        print("[crash_prevention] Cleanup on exit")
        # Give threads a moment to finish current operations
        time.sleep(0.3)
        # CRITICAL: Force-exit to prevent Python's finalizer from re-enabling GC
        # This prevents the "Garbage-collecting <no Python frame>" access violation
        import os
        os._exit(0)
    
    atexit.register(_cleanup)
    
    print("[crash_prevention] Ready")


# -- Export --------------------------------------------------------------------

__all__ = [
    "initialize_crash_prevention",
    "ThreadSafeWrapper",
    "GCSafeContext",
    "ResilientWorker",
    "safe_queue_put",
    "safe_queue_get",
    "check_and_gc",
]
