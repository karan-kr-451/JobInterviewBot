"""
test_crash_prevention.py - Comprehensive crash prevention tests.

Tests all identified crash scenarios to ensure fixes are working:
1. tqdm monitor thread safety
2. numpy GC during C-extension calls
3. requests.Session thread safety
4. Queue overflow handling
5. Thread death recovery
6. Graceful shutdown
"""

import sys
import os
import time
import threading
import queue
import gc
import numpy as np

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.crash_prevention import (
    initialize_crash_prevention,
    ThreadSafeWrapper,
    GCSafeContext,
    ResilientWorker,
    safe_queue_put,
    safe_queue_get,
)


def test_initialization():
    """Test that crash prevention initializes without errors."""
    print("\n" + "="*60)
    print("TEST: Initialization")
    print("="*60)
    
    try:
        initialize_crash_prevention()
        print("[OK] Initialization successful")
        return True
    except Exception as e:
        print(f"[FAIL] Initialization failed: {e}")
        return False


def test_tqdm_monitor():
    """Test that tqdm monitor is properly disabled."""
    print("\n" + "="*60)
    print("TEST: tqdm Monitor Disabling")
    print("="*60)
    
    try:
        import tqdm
        
        # Check monitor is disabled
        if tqdm.tqdm.monitor_interval != 0:
            print("[FAIL] Monitor interval not set to 0")
            return False
        
        # Check instance is None (if attribute exists)
        try:
            import tqdm._monitor as _tmon
            if hasattr(_tmon.TMonitor, '_instance'):
                if _tmon.TMonitor._instance is not None:
                    print("[FAIL] Monitor instance still exists")
                    return False
        except (ImportError, AttributeError):
            # Older tqdm versions don't have _instance - that's fine
            pass
        
        # Try to create progress bar (should not start monitor)
        for _ in tqdm.tqdm(range(10), disable=True):
            pass
        
        # Verify monitor still None (if attribute exists)
        try:
            import tqdm._monitor as _tmon
            if hasattr(_tmon.TMonitor, '_instance'):
                if _tmon.TMonitor._instance is not None:
                    print("[FAIL] Monitor was recreated")
                    return False
        except (ImportError, AttributeError):
            pass
        
        print("[OK] tqdm monitor properly disabled")
        return True
        
    except Exception as e:
        print(f"[FAIL] tqdm test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_thread_safe_wrapper():
    """Test ThreadSafeWrapper for thread-local storage."""
    print("\n" + "="*60)
    print("TEST: ThreadSafeWrapper")
    print("="*60)
    
    try:
        # Create wrapper for a simple counter
        counter = {"value": 0}
        
        def factory():
            return {"value": 0, "thread_id": threading.current_thread().ident}
        
        wrapper = ThreadSafeWrapper(factory)
        
        # Test from main thread
        obj1 = wrapper.get()
        obj1["value"] = 42
        
        # Test from another thread
        results = []
        def worker():
            obj2 = wrapper.get()
            obj2["value"] = 99
            results.append(obj2)
        
        t = threading.Thread(target=worker)
        t.start()
        t.join()
        
        # Verify each thread got its own instance
        obj1_again = wrapper.get()
        if obj1_again["value"] != 42:
            print(f"[FAIL] Main thread value changed: {obj1_again['value']}")
            return False
        
        if results[0]["value"] != 99:
            print(f"[FAIL] Worker thread value wrong: {results[0]['value']}")
            return False
        
        if obj1_again["thread_id"] == results[0]["thread_id"]:
            print("[FAIL] Same instance used in both threads")
            return False
        
        print("[OK] ThreadSafeWrapper working correctly")
        return True
        
    except Exception as e:
        print(f"[FAIL] ThreadSafeWrapper test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_gc_safe_context():
    """Test GCSafeContext disables GC during critical sections."""
    print("\n" + "="*60)
    print("TEST: GCSafeContext")
    print("="*60)
    
    try:
        # Verify GC is initially enabled
        if not gc.isenabled():
            gc.enable()
        
        # Test context manager
        with GCSafeContext():
            if gc.isenabled():
                print("[FAIL] GC not disabled inside context")
                return False
        
        # Verify GC is re-enabled after context
        if not gc.isenabled():
            print("[FAIL] GC not re-enabled after context")
            return False
        
        # Test with exception
        try:
            with GCSafeContext():
                raise ValueError("test exception")
        except ValueError:
            pass
        
        # Verify GC still re-enabled after exception
        if not gc.isenabled():
            print("[FAIL] GC not re-enabled after exception")
            return False
        
        print("[OK] GCSafeContext working correctly")
        return True
        
    except Exception as e:
        print(f"[FAIL] GCSafeContext test failed: {e}")
        return False


def test_resilient_worker():
    """Test ResilientWorker crash recovery."""
    print("\n" + "="*60)
    print("TEST: ResilientWorker")
    print("="*60)
    
    try:
        crash_count = [0]
        work_count = [0]
        
        def work_fn():
            for i in range(5):
                work_count[0] += 1
                if i == 2:
                    crash_count[0] += 1
                    raise RuntimeError("Simulated crash")
                time.sleep(0.1)
        
        worker = ResilientWorker(work_fn, name="test-worker", max_restarts=3)
        worker.start()
        
        # Wait for worker to finish
        time.sleep(2.0)
        
        # Verify worker recovered from crash
        if crash_count[0] == 0:
            print("[FAIL] No crash occurred (test setup issue)")
            return False
        
        if work_count[0] < 5:
            print(f"[FAIL] Worker didn't complete work: {work_count[0]}/5")
            return False
        
        print(f"[OK] ResilientWorker recovered from {crash_count[0]} crash(es)")
        return True
        
    except Exception as e:
        print(f"[FAIL] ResilientWorker test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_safe_queue_operations():
    """Test safe queue put/get with timeouts."""
    print("\n" + "="*60)
    print("TEST: Safe Queue Operations")
    print("="*60)
    
    try:
        q = queue.Queue(maxsize=2)
        
        # Test normal put
        if not safe_queue_put(q, "item1"):
            print("[FAIL] Failed to put item1")
            return False
        
        if not safe_queue_put(q, "item2"):
            print("[FAIL] Failed to put item2")
            return False
        
        # Test put on full queue (should drop)
        if safe_queue_put(q, "item3", timeout=0.5, drop_on_full=True):
            print("[FAIL] Put succeeded on full queue")
            return False
        
        # Test get
        item = safe_queue_get(q, timeout=0.5)
        if item != "item1":
            print(f"[FAIL] Got wrong item: {item}")
            return False
        
        # Test get with default
        q.get()  # empty the queue
        item = safe_queue_get(q, timeout=0.5, default="default")
        if item != "default":
            print(f"[FAIL] Default not returned: {item}")
            return False
        
        print("[OK] Safe queue operations working correctly")
        return True
        
    except Exception as e:
        print(f"[FAIL] Safe queue test failed: {e}")
        return False


def test_numpy_gc_safety():
    """Test that numpy operations don't crash with GC."""
    print("\n" + "="*60)
    print("TEST: Numpy GC Safety")
    print("="*60)
    
    try:
        # Create large arrays and force GC during operations
        for i in range(10):
            data = np.random.randn(16000).astype(np.float32)
            
            with GCSafeContext():
                # Simulate STFT-like operation
                result = np.fft.rfft(data)
                result = np.abs(result)
            
            # Force GC between iterations
            gc.collect()
        
        print("[OK] Numpy operations safe with GC")
        return True
        
    except Exception as e:
        print(f"[FAIL] Numpy GC test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_concurrent_requests():
    """Test thread-safe requests.Session usage."""
    print("\n" + "="*60)
    print("TEST: Concurrent Requests")
    print("="*60)
    
    try:
        import requests
        
        # Create thread-safe session wrapper
        def session_factory():
            return requests.Session()
        
        session_wrapper = ThreadSafeWrapper(session_factory)
        
        results = []
        errors = []
        
        def make_request(url):
            try:
                session = session_wrapper.get()
                # Don't actually make request, just verify we got a session
                if not isinstance(session, requests.Session):
                    errors.append("Not a Session instance")
                else:
                    results.append(threading.current_thread().ident)
            except Exception as e:
                errors.append(str(e))
        
        # Start multiple threads
        threads = []
        for i in range(5):
            t = threading.Thread(target=make_request, args=("http://example.com",))
            threads.append(t)
            t.start()
        
        # Wait for all threads
        for t in threads:
            t.join()
        
        if errors:
            print(f"[FAIL] Errors occurred: {errors}")
            return False
        
        if len(results) != 5:
            print(f"[FAIL] Wrong number of results: {len(results)}")
            return False
        
        # Verify each thread got its own session (different thread IDs)
        if len(set(results)) != 5:
            print("[FAIL] Threads shared sessions")
            return False
        
        print("[OK] Concurrent requests safe")
        return True
        
    except Exception as e:
        print(f"[FAIL] Concurrent requests test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """Run all crash prevention tests."""
    print("\n" + "="*70)
    print(" CRASH PREVENTION TEST SUITE")
    print("="*70)
    
    tests = [
        ("Initialization", test_initialization),
        ("tqdm Monitor", test_tqdm_monitor),
        ("ThreadSafeWrapper", test_thread_safe_wrapper),
        ("GCSafeContext", test_gc_safe_context),
        ("ResilientWorker", test_resilient_worker),
        ("Safe Queue Ops", test_safe_queue_operations),
        ("Numpy GC Safety", test_numpy_gc_safety),
        ("Concurrent Requests", test_concurrent_requests),
    ]
    
    results = []
    for name, test_fn in tests:
        try:
            passed = test_fn()
            results.append((name, passed))
        except Exception as e:
            print(f"\n[FAIL] {name} crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Summary
    print("\n" + "="*70)
    print(" TEST SUMMARY")
    print("="*70)
    
    passed = sum(1 for _, p in results if p)
    total = len(results)
    
    for name, p in results:
        status = "[OK] PASS" if p else "[FAIL] FAIL"
        print(f"{status:8} {name}")
    
    print("="*70)
    print(f"Result: {passed}/{total} tests passed")
    print("="*70)
    
    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
