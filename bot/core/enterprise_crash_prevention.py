"""
core.enterprise_crash_prevention - Enterprise-grade crash prevention system.

Implements crash prevention strategies used by major tech companies:
- Google: Circuit breakers, graceful degradation
- Microsoft: Defensive programming, fail-fast
- Amazon: Bulkheads, timeout enforcement
- Netflix: Chaos engineering principles
"""

import sys
import time
import threading
import functools
import traceback
import gc
from typing import Callable, Any, Optional
from contextlib import contextmanager

# Import the global HTTP lock to prevent OpenSSL race conditions across ALL threads
from core.http_utils import _http_lock


# -- Circuit Breaker Pattern (Netflix/Google) ----------------------------------
class CircuitBreaker:
    """
    Circuit breaker pattern to prevent cascading failures.
    Used by Netflix, AWS, Google for resilient systems.
    """
    
    def __init__(self, failure_threshold: int = 5, timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failures = 0
        self.last_failure_time = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.lock = threading.Lock()
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection."""
        with self.lock:
            if self.state == "OPEN":
                if time.time() - self.last_failure_time > self.timeout:
                    self.state = "HALF_OPEN"
                    self.failures = 0
                else:
                    raise RuntimeError(f"Circuit breaker OPEN - service unavailable")
        
        try:
            result = func(*args, **kwargs)
            with self.lock:
                if self.state == "HALF_OPEN":
                    self.state = "CLOSED"
                self.failures = 0
            return result
        except Exception as e:
            with self.lock:
                self.failures += 1
                self.last_failure_time = time.time()
                if self.failures >= self.failure_threshold:
                    self.state = "OPEN"
                    print(f"[Circuit Breaker] OPEN - {self.failures} failures")
            raise


# -- Bulkhead Pattern (Amazon/Microsoft) ---------------------------------------
class ResourcePool:
    """
    Bulkhead pattern to isolate resources and prevent resource exhaustion.
    Used by Amazon, Microsoft for resource isolation.
    """
    
    def __init__(self, max_concurrent: int = 10):
        self.semaphore = threading.Semaphore(max_concurrent)
        self.active_count = 0
        self.lock = threading.Lock()
    
    @contextmanager
    def acquire(self, timeout: float = 30.0):
        """Acquire resource with timeout."""
        acquired = self.semaphore.acquire(timeout=timeout)
        if not acquired:
            raise RuntimeError("Resource pool exhausted - timeout")
        
        with self.lock:
            self.active_count += 1
        
        try:
            yield
        finally:
            with self.lock:
                self.active_count -= 1
            self.semaphore.release()


# -- Timeout Enforcement (Google/Amazon) ---------------------------------------
def with_timeout(timeout_seconds: float):
    """
    Decorator to enforce timeout on function execution.
    Used by Google, Amazon for preventing hung operations.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            result = [None]
            exception = [None]
            
            def target():
                try:
                    result[0] = func(*args, **kwargs)
                except Exception as e:
                    exception[0] = e
            
            thread = threading.Thread(target=target, daemon=True)
            thread.start()
            thread.join(timeout=timeout_seconds)
            
            if thread.is_alive():
                raise TimeoutError(f"{func.__name__} exceeded {timeout_seconds}s timeout")
            
            if exception[0]:
                raise exception[0]
            
            return result[0]
        return wrapper
    return decorator


# -- Retry with Exponential Backoff (AWS/Google) -------------------------------
def retry_with_backoff(max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 60.0):
    """
    Retry with exponential backoff and jitter.
    Used by AWS, Google Cloud for resilient API calls.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            import random
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries:
                        raise
                    
                    # Exponential backoff with jitter
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    jitter = random.uniform(0, delay * 0.1)
                    sleep_time = delay + jitter
                    
                    print(f"[Retry] {func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}), "
                          f"retrying in {sleep_time:.1f}s: {e}")
                    time.sleep(sleep_time)
            
            return None
        return wrapper
    return decorator


# -- Graceful Degradation (Google/Netflix) -------------------------------------
class FallbackChain:
    """
    Fallback chain for graceful degradation.
    Used by Google, Netflix for high availability.
    """
    
    def __init__(self, *functions: Callable):
        self.functions = functions
    
    def execute(self, *args, **kwargs) -> Any:
        """Execute functions in order until one succeeds."""
        last_error = None
        
        for i, func in enumerate(self.functions):
            try:
                result = func(*args, **kwargs)
                if i > 0:
                    print(f"[Fallback] Using fallback #{i + 1}: {func.__name__}")
                return result
            except Exception as e:
                last_error = e
                if i < len(self.functions) - 1:
                    print(f"[Fallback] {func.__name__} failed, trying next: {e}")
        
        raise RuntimeError(f"All fallbacks exhausted. Last error: {last_error}")


# -- Safe Execution Context (Microsoft) ----------------------------------------
@contextmanager
def safe_execution(operation_name: str, fallback_value: Any = None, 
                   log_errors: bool = True, raise_on_error: bool = False):
    """
    Safe execution context with automatic error handling.
    Used by Microsoft for defensive programming.
    """
    try:
        yield
    except KeyboardInterrupt:
        raise
    except Exception as e:
        if log_errors:
            print(f"[Safe Execution] {operation_name} failed: {e}")
            if hasattr(e, '__traceback__'):
                traceback.print_exc()
        
        if raise_on_error:
            raise
        
        return fallback_value


# -- Thread Safety Wrapper (Google/Microsoft) ----------------------------------
class ThreadSafeWrapper:
    """
    Thread-safe wrapper for non-thread-safe objects.
    Used by Google, Microsoft for concurrent access.
    """
    
    def __init__(self, factory: Callable):
        self.factory = factory
        self.local = threading.local()
    
    def get(self):
        """Get thread-local instance."""
        if not hasattr(self.local, 'instance'):
            self.local.instance = self.factory()
        return self.local.instance
    
    def reset(self):
        """Reset thread-local instance."""
        if hasattr(self.local, 'instance'):
            delattr(self.local, 'instance')


# -- Health Check System (AWS/Google) ------------------------------------------
class HealthChecker:
    """
    Health check system for monitoring component health.
    Used by AWS, Google Cloud for service monitoring.
    """
    
    def __init__(self):
        self.checks = {}
        self.lock = threading.Lock()
    
    def register(self, name: str, check_func: Optional[Callable[[], bool]] = None, 
                 interval: float = 60.0):
        """Register a health check or a ping-based component."""
        with self.lock:
            self.checks[name] = {
                'func': check_func,
                'interval': interval,
                'last_check': 0,
                'last_ping': time.time(),
                'status': 'HEALTHY',
                'last_error': None
            }
    
    def ping(self, name: str):
        """Record activity from a component (liveness probe)."""
        with self.lock:
            if name in self.checks:
                self.checks[name]['last_ping'] = time.time()
                self.checks[name]['status'] = 'HEALTHY'
    
    def check(self, name: str) -> bool:
        """Run health check for component."""
        with self.lock:
            if name not in self.checks:
                return False
            
            check = self.checks[name]
            now = time.time()
            
            # 1. If it's a ping-based component, check if it timed out
            if check['func'] is None:
                # If no ping for 3x the interval, it's unhealthy
                if now - check['last_ping'] > check['interval'] * 3:
                    check['status'] = 'STALLED'
                    return False
                return True

            # 2. Otherwise run explicit check function
            # Skip if checked recently
            if now - check['last_check'] < check['interval']:
                return check['status'] == 'HEALTHY'
            
            check['last_check'] = now
        
        try:
            result = check['func']()
            with self.lock:
                check['status'] = 'HEALTHY' if result else 'UNHEALTHY'
                check['last_error'] = None
            return result
        except Exception as e:
            with self.lock:
                check['status'] = 'UNHEALTHY'
                check['last_error'] = str(e)
            return False
    
    def get_status(self) -> dict:
        """Get status of all health checks."""
        with self.lock:
            return {
                name: {
                    'status': check['status'],
                    'last_check': check['last_check'],
                    'last_error': check['last_error']
                }
                for name, check in self.checks.items()
            }


# -- Memory Pressure Monitor (Google/Microsoft) --------------------------------
class MemoryPressureMonitor:
    """
    Monitor memory pressure and trigger GC when needed.
    Used by Google Chrome, Microsoft Edge for memory management.
    """
    
    def __init__(self, threshold_mb: int = 500):
        self.threshold_bytes = threshold_mb * 1024 * 1024
        self.last_check = 0
        self.check_interval = 10.0  # seconds
    
    def check_and_gc(self) -> bool:
        """Check memory pressure and log if high. GC is permanently disabled."""
        now = time.time()
        if now - self.last_check < self.check_interval:
            return False
        
        self.last_check = now
        
        try:
            import psutil
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            
            if memory_mb > self.threshold_bytes / 1024 / 1024:
                print(f"[Memory] High usage: {memory_mb:.0f}MB (GC disabled - relying on refcounting)")
                return True
        except ImportError:
            pass
        
        return False


# -- Background Monitoring (Google/AWS) ----------------------------------------
def _monitoring_thread():
    """Background thread to monitor system health and memory."""
    print("[Enterprise] Background monitoring started")
    
    from core.http_utils import _http_lock
    import gc
    
    while True:
        try:
            # Shield ALL monitoring operations with the global lock
            # to prevent C-extension collisions (psutil vs requests)
            with _http_lock:
                # Ensure GC stays disabled
                if gc.isenabled():
                    gc.disable()
                    
                # Check memory pressure
                memory_monitor.check_and_gc()
                
                # Run all registered health checks
                for name in list(health_checker.checks.keys()):
                    health_checker.check(name)
                
        except Exception as e:
            print(f"[Enterprise Monitor] Error: {e}")
            
        time.sleep(10.0)  # Check every 10 seconds


def start_background_monitoring():
    """Start the enterprise background monitoring thread."""
    t = threading.Thread(target=_monitoring_thread, daemon=True, name="enterprise-monitor")
    t.start()
    return t


# -- Global Instances ----------------------------------------------------------
# Create global instances for easy access
http_circuit_breaker = CircuitBreaker(failure_threshold=5, timeout=60.0)
http_resource_pool = ResourcePool(max_concurrent=20)
health_checker = HealthChecker()
memory_monitor = MemoryPressureMonitor(threshold_mb=500)


# -- Convenience Functions -----------------------------------------------------
def safe_http_call(func: Callable, *args, **kwargs) -> Any:
    """
    Execute HTTP call with circuit breaker, resource pool, and timeout.
    Enterprise-grade protection for HTTP operations.
    """
    # Use with_timeout to ensure the inner call doesn't hang the entire app
    # (requests.timeout sometimes fails on low-level socket hangs)
    @with_timeout(30.0)
    def protected_call():
        # CRITICAL: Use the global HTTP lock for the ENTIRE duration of the call
        # prevents OpenSSL/cryptography race conditions on Windows
        with _http_lock:
            # Shield from GC during the C-extension call
            if gc.isenabled():
                gc.disable()
                
            with http_resource_pool.acquire(timeout=10.0):
                return http_circuit_breaker.call(func, *args, **kwargs)
            
    try:
        return protected_call()
    except TimeoutError:
        print(f"[Safe HTTP] TIMEOUT - Circuit breaker might open soon")
        # Record failure manually if timeout occurred outside func
        with http_circuit_breaker.lock:
            http_circuit_breaker.failures += 1
            if http_circuit_breaker.failures >= http_circuit_breaker.failure_threshold:
                http_circuit_breaker.state = "OPEN"
        raise
    except Exception as e:
        # already handled by circuit breaker internal call
        raise


def safe_thread_operation(func: Callable, *args, **kwargs) -> Any:
    """
    Execute operation with full enterprise protection.
    Combines timeout, retry, and error handling.
    """
    @retry_with_backoff(max_retries=2, base_delay=1.0)
    @with_timeout(30.0)
    def protected_func():
        return func(*args, **kwargs)
    
    try:
        return protected_func()
    except Exception as e:
        print(f"[Safe Thread] Operation failed: {e}")
        return None


# -- Initialization ------------------------------------------------------------
def initialize_enterprise_crash_prevention():
    """Initialize enterprise crash prevention system."""
    print("=" * 60)
    print("Enterprise Crash Prevention System")
    print("=" * 60)
    print("[OK] Circuit breakers initialized")
    print("[OK] Resource pools configured")
    print("[OK] Health checks ready")
    
    # Start background thread
    start_background_monitoring()
    print("[OK] Memory and Health monitoring active (background)")
    print("=" * 60)


if __name__ == "__main__":
    initialize_enterprise_crash_prevention()
