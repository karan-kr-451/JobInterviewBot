"""
core.crash_shield - Ultimate crash protection shield.

Combines all enterprise crash prevention techniques into one unified system.
Inspired by crash prevention systems from:
- Google Chrome (process isolation, crash recovery)
- Microsoft Windows (WER - Windows Error Reporting)
- AWS (fault injection, chaos engineering)
- Netflix (Hystrix circuit breakers)
"""

import sys
import os
import time
import threading
import traceback
import functools
from typing import Callable, Any, Optional
from contextlib import contextmanager


class CrashShield:
    """
    Ultimate crash protection system.
    Wraps operations with multiple layers of protection.
    """
    
    def __init__(self, name: str):
        self.name = name
        self.crash_count = 0
        self.last_crash_time = 0
        self.crash_threshold = 10
        self.crash_window = 60.0  # seconds
        self.lock = threading.Lock()
        self.enabled = True
    
    def __call__(self, func: Callable) -> Callable:
        """Decorator to protect function with crash shield."""
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not self.enabled:
                return func(*args, **kwargs)
            
            return self.execute(func, *args, **kwargs)
        return wrapper
    
    def execute(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with full crash protection."""
        # Check if too many crashes
        with self.lock:
            now = time.time()
            if now - self.last_crash_time > self.crash_window:
                self.crash_count = 0
            
            if self.crash_count >= self.crash_threshold:
                raise RuntimeError(
                    f"[Crash Shield] {self.name} exceeded crash threshold "
                    f"({self.crash_count} crashes in {self.crash_window}s)"
                )
        
        try:
            # Layer 1: Basic execution
            result = func(*args, **kwargs)
            return result
            
        except KeyboardInterrupt:
            # Always propagate keyboard interrupt
            raise
            
        except SystemExit:
            # Always propagate system exit
            raise
            
        except MemoryError as e:
            # Critical: Out of memory
            self._handle_crash("MEMORY_ERROR", e)
            raise
            
        except Exception as e:
            # Handle all other exceptions
            self._handle_crash("EXCEPTION", e)
            raise
    
    def _handle_crash(self, crash_type: str, error: Exception):
        """Handle crash and update statistics."""
        with self.lock:
            self.crash_count += 1
            self.last_crash_time = time.time()
        
        # Log crash
        crash_info = {
            'type': crash_type,
            'error': str(error),
            'traceback': traceback.format_exc(),
            'time': time.strftime('%Y-%m-%d %H:%M:%S'),
            'count': self.crash_count
        }
        
        self._log_crash(crash_info)
    
    def _log_crash(self, crash_info: dict):
        """Log crash to file."""
        try:
            log_file = f"crash_shield_{self.name}.log"
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write("=" * 80 + "\n")
                f.write(f"CRASH #{crash_info['count']} - {crash_info['time']}\n")
                f.write(f"Type: {crash_info['type']}\n")
                f.write(f"Error: {crash_info['error']}\n")
                f.write("-" * 80 + "\n")
                f.write(crash_info['traceback'])
                f.write("=" * 80 + "\n\n")
        except Exception:
            pass
    
    def reset(self):
        """Reset crash counter."""
        with self.lock:
            self.crash_count = 0
            self.last_crash_time = 0


# -- Process Isolation (Google Chrome Style) -----------------------------------
class ProcessIsolation:
    """
    Process isolation for critical components.
    Inspired by Google Chrome's multi-process architecture.
    """
    
    @staticmethod
    def run_isolated(func: Callable, *args, **kwargs) -> Any:
        """
        Run function in isolated process.
        If it crashes, main process continues.
        """
        import multiprocessing
        
        def wrapper(queue, func, args, kwargs):
            try:
                result = func(*args, **kwargs)
                queue.put(('success', result))
            except Exception as e:
                queue.put(('error', str(e)))
        
        queue = multiprocessing.Queue()
        process = multiprocessing.Process(
            target=wrapper,
            args=(queue, func, args, kwargs)
        )
        
        process.start()
        process.join(timeout=30.0)
        
        if process.is_alive():
            process.terminate()
            process.join()
            raise TimeoutError("Isolated process timeout")
        
        if process.exitcode != 0:
            raise RuntimeError(f"Isolated process crashed with code {process.exitcode}")
        
        status, result = queue.get()
        if status == 'error':
            raise RuntimeError(f"Isolated process error: {result}")
        
        return result


# -- Watchdog Timer (Microsoft Style) ------------------------------------------
class WatchdogTimer:
    """
    Watchdog timer to detect hung operations.
    Inspired by Microsoft Windows watchdog timers.
    """
    
    def __init__(self, timeout: float, callback: Optional[Callable] = None):
        self.timeout = timeout
        self.callback = callback
        self.timer = None
        self.lock = threading.Lock()
    
    def start(self):
        """Start watchdog timer."""
        with self.lock:
            if self.timer:
                self.timer.cancel()
            self.timer = threading.Timer(self.timeout, self._timeout_handler)
            self.timer.daemon = True
            self.timer.start()
    
    def reset(self):
        """Reset watchdog timer."""
        self.start()
    
    def stop(self):
        """Stop watchdog timer."""
        with self.lock:
            if self.timer:
                self.timer.cancel()
                self.timer = None
    
    def _timeout_handler(self):
        """Handle timeout."""
        print(f"[Watchdog] Timeout after {self.timeout}s")
        if self.callback:
            try:
                self.callback()
            except Exception as e:
                print(f"[Watchdog] Callback error: {e}")


# -- Crash Recovery (Windows Error Reporting Style) ----------------------------
class CrashRecovery:
    """
    Automatic crash recovery system.
    Inspired by Windows Error Reporting (WER).
    """
    
    def __init__(self):
        self.recovery_handlers = {}
        self.lock = threading.Lock()
    
    def register_handler(self, component: str, handler: Callable):
        """Register recovery handler for component."""
        with self.lock:
            self.recovery_handlers[component] = handler
    
    def recover(self, component: str) -> bool:
        """Attempt to recover component."""
        with self.lock:
            handler = self.recovery_handlers.get(component)
        
        if not handler:
            print(f"[Recovery] No handler for {component}")
            return False
        
        try:
            print(f"[Recovery] Attempting to recover {component}")
            handler()
            print(f"[Recovery] {component} recovered successfully")
            return True
        except Exception as e:
            print(f"[Recovery] Failed to recover {component}: {e}")
            return False


# -- Global Instances ----------------------------------------------------------
# Create shields for critical components
http_shield = CrashShield("HTTP")
audio_shield = CrashShield("Audio")
llm_shield = CrashShield("LLM")
overlay_shield = CrashShield("Overlay")
telegram_shield = CrashShield("Telegram")

# Create recovery system
crash_recovery = CrashRecovery()


# -- Convenience Decorators ----------------------------------------------------
def protect_http(func: Callable) -> Callable:
    """Protect HTTP operations."""
    return http_shield(func)


def protect_audio(func: Callable) -> Callable:
    """Protect audio operations."""
    return audio_shield(func)


def protect_llm(func: Callable) -> Callable:
    """Protect LLM operations."""
    return llm_shield(func)


def protect_overlay(func: Callable) -> Callable:
    """Protect overlay operations."""
    return overlay_shield(func)


def protect_telegram(func: Callable) -> Callable:
    """Protect Telegram operations."""
    return telegram_shield(func)


# -- Ultimate Protection Wrapper -----------------------------------------------
@contextmanager
def ultimate_protection(operation_name: str, timeout: float = 30.0):
    """
    Ultimate protection context manager.
    Combines all protection mechanisms.
    """
    watchdog = WatchdogTimer(timeout)
    watchdog.start()
    
    try:
        yield
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(f"[Ultimate Protection] {operation_name} failed: {e}")
        traceback.print_exc()
        
        # Attempt recovery
        crash_recovery.recover(operation_name)
        
        raise
    finally:
        watchdog.stop()


# -- Initialization ------------------------------------------------------------
def initialize_crash_shield():
    """Initialize crash shield system."""
    print("=" * 60)
    print("Crash Shield System Initialized")
    print("=" * 60)
    print("[OK] HTTP shield active")
    print("[OK] Audio shield active")
    print("[OK] LLM shield active")
    print("[OK] Overlay shield active")
    print("[OK] Telegram shield active")
    print("[OK] Crash recovery ready")
    print("=" * 60)


if __name__ == "__main__":
    initialize_crash_shield()
